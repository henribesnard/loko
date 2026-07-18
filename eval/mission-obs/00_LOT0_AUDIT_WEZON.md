# LOT 0 — Audit et securisation de loko.wezon.fr

**Date** : 2026-07-18
**Version deployee** : 1.2.2 (commit `0c00423`, 16 juillet 2026)
**Version courante (code)** : 1.3.4 (post-remediation)
**Operateur** : Claude Code (Opus 4.6)

---

## O0-1 — Inventaire

| Element | Valeur |
|---------|--------|
| URL | `https://loko.wezon.fr` |
| Version servie (`/health`) | **1.2.2** |
| VPS | `38.143.19.38` (Ubuntu 24.04) |
| Deploiement | Docker (`ghcr.io/henribesnard/loko:1.2.2`) via `docker-compose.prod.yml` |
| Reverse proxy | Caddy (TLS auto Let's Encrypt) |
| DNS | Cloudflare, A record `loko` (proxied) |
| Port interne | 8001 -> 8000 (Uvicorn/FastAPI) |
| Date du tag v1.2.2 | 2026-07-16 22:30 CEST |
| Ecart avec le code courant | **3 versions majeures** (v1.2.2 -> v1.3.0 -> v1.3.3 -> v1.3.4) |

**Constats** :
- La version deployee est anterieure a toute la campagne de recette et a toute la remediation v1.3.3.
- Les corrections P1-P4, D1-D4, M1-M5, T1-T4 ne sont PAS deployees.
- En particulier, le correctif P4 (ACC-4 email verification) est absent.

---

## O0-2 — Surface d'exposition

### Routes sondees

| Route | Methode | Reponse | Commentaire |
|-------|---------|---------|-------------|
| `/health` | GET | **200** `{"status":"ok","service":"loko-bot","version":"1.2.2"}` | Public, expose la version — acceptable pour health check |
| `/` | GET | 200 (SPA shell) | Landing page, pas de contenu sensible |
| `/api/docs` | GET | **401** | Protege par admin token (LOKO_MODE=server) — OK |
| `/api/ops/health` | GET | **401** | Protege — OK |
| `/api/auth/signup` | GET | 404 (POST-only) | L'endpoint POST existe et est callable |
| `/api/auth/login` | GET | 404 (POST-only) | L'endpoint POST existe et est callable |
| `/api/v1/bot` | GET | 404 | Pas de bot public configure — OK |
| `/widget` | GET | SPA shell | Widget embeddable |

### TLS
- Certificat : Let's Encrypt via Caddy (renouvellement automatique)
- Cloudflare en proxy — double TLS (client -> Cloudflare -> Caddy)
- Pas de verification HSTS possible sans acces aux headers de reponse

### Security headers (d'apres le code v1.2.2)
Middleware `SecurityHeadersMiddleware` present :
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `X-Frame-Options: DENY` (sauf `/widget`)
- `Content-Security-Policy` sur les reponses HTML

### CORS
- `LOKO_CORS_ORIGINS=https://loko.wezon.fr` (d'apres DEPLOIEMENT.md)
- Pas de wildcard `*` — OK

### Rate limiting
- Login : 5 tentatives / minute / IP
- Signup : 3 tentatives / heure / IP
- Pas de WAF visible cote application (Cloudflare fournit une couche)

### Contrat P-A1 (landing + demo + 401 partout ailleurs)
- **Landing** : OK (`/` sert la SPA)
- **401 partout ailleurs** : `/api/docs`, `/api/ops/*` sont proteges — OK
- **Signup public** : l'endpoint `/api/auth/signup` est accessible sans restriction d'acces (seul le rate limit le freine) — **ECART avec P-A1** si l'intention etait de n'autoriser que la demo
- **Absence de `/ops` cote serveur** : `/ops` est gere par le SPA (routing client) — le routeur ops API est a `/api/ops` et protege

---

## O0-3 — Exploitabilite du bug P4 (ACC-4)

### Le defaut

En v1.2.2, fichier `loko/api/user_auth.py`, lignes 259-264 :

```python
# ACC-4: email verification — disabled until SMTP is configured
# if user.get("email_verified_at") is None:
#     raise HTTPException(
#         status_code=403,
#         detail="Email non verifie. Verifiez votre boite mail ou demandez un nouveau lien.",
#     )
```

Le controle de verification d'email est **commente**. Un utilisateur peut s'inscrire et se connecter immediatement sans jamais verifier son email.

### Chaine d'exploitation a distance

1. **POST** `/api/auth/signup` avec `email` (n'importe quelle adresse, meme inexistante), `password` (12+ car., maj, chiffre, special), `org_name`, `accept_terms: true`
   - Resultat : compte + utilisateur crees, `email_verified_at = NULL`
   - Anti-enumeration : meme reponse si l'email existe deja

2. **POST** `/api/auth/login` avec le meme `email` et `password`
   - Le check ACC-4 est commente → **login reussit malgre `email_verified_at = NULL`**
   - Session cookie `loko_session` emise + cookie CSRF

3. **Avec le cookie de session**, l'attaquant a un acces authentifie complet :
   - Creation/modification de bots
   - Acces au dashboard de son tenant
   - Acces au playground (test du chatbot)
   - Potentiellement acces a `/api/user/me`, `/api/user/export-data`

### Verdict

| Critere | Evaluation |
|---------|------------|
| Exploitable a distance | **OUI** — aucune barriere technique (POST HTTP suffit) |
| Pre-requis | Aucun (pas de captcha, pas de validation email) |
| Impact confidentialite | **Modere** — l'attaquant n'accede qu'a son propre tenant (isolation correcte dans le code). Pas d'acces cross-tenant prouve. |
| Impact integrite | **Modere** — creation de comptes/bots illegitimes, pollution de la base |
| Impact disponibilite | **Faible** — rate limit (3 signup/h/IP) limite le volume, mais contournable via IPs multiples |
| Facteur attenuant | Cloudflare proxy (protection DDoS basique), rate limiting signup/login, isolation tenant |
| Facteur aggravant | Aucun captcha, aucune validation d'email requise, pas de quota de comptes |

**Verdict : EXPLOITABLE A DISTANCE — severite MOYENNE-HAUTE**

L'absence de verification email permet la creation de comptes fantomes sans aucune friction. L'impact est limite par l'isolation tenant (pas d'acces aux donnees des autres comptes), mais la creation de comptes non controles pose un risque d'abus (spam, pollution, enumeration de fonctionnalites).

---

## O0-4 — Donnees presentes

**Limitation** : pas d'acces SSH dans cette session. L'analyse est basee sur le code et la documentation.

### Ce que l'on sait

| Element | Presence probable | Source |
|---------|-------------------|--------|
| Comptes utilisateurs | **OUI** — au moins un compte de test/demo a probablement ete cree | Fonctionnalite signup active |
| Transcripts de sessions | **Possible** — si un bot a ete configure et teste | `LOKO_SESSION_RETENTION_DAYS=30` |
| Cles API bots | **Possible** — si des bots ont ete publies | Fonctionnalite API keys |
| Modeles ML entraines | **Possible** — dans `/home/loko/.loko/models/` | Fonctionnalite training |
| Base SQLite | **OUI** — `data.db` + `audit.db` dans le volume Docker | Architecture applicative |
| Donnees client reelles | **Inconnu** — necessite inspection directe | **Demande humaine O0-4** |

### Recommendation

**Action humaine requise** : se connecter au VPS et verifier :
```bash
ssh root@38.143.19.38
# Nombre de comptes
sqlite3 /opt/loko/data/.loko/data.db "SELECT COUNT(*) FROM accounts;"
# Nombre d'utilisateurs
sqlite3 /opt/loko/data/.loko/data.db "SELECT COUNT(*) FROM users;"
# Sessions recentes
sqlite3 /opt/loko/data/.loko/data.db "SELECT COUNT(*) FROM sessions WHERE created_at > datetime('now', '-30 days');"
# Bots configures
sqlite3 /opt/loko/data/.loko/data.db "SELECT COUNT(*) FROM bots;" 2>/dev/null || echo "Pas de table bots"
```

---

## O0-5 — Recommandation

### Verdict global

| Facteur | Constat |
|---------|---------|
| Bug P4 exploitable a distance | **OUI** |
| Donnees reelles possibles | **Inconnu (necessite SSH)** |
| Version deployee obsolete | **OUI** (v1.2.2 vs v1.3.4, 2 jours de retard, 17+ correctifs manquants) |
| Signup public ouvert | **OUI** (pas de captcha, pas de validation email) |

### Recommandation ferme : (a) BASIC-AUTH IMMEDIATE

En l'absence de certitude sur l'absence de donnees reelles, et avec un bug d'authentification exploitable, la recommandation est **la mise en place immediate d'un basic-auth Caddy** pour bloquer tout acces non autorise le temps de l'evaluation.

### Configuration Caddy prete a coller

Remplacer le bloc actuel dans `/etc/caddy/Caddyfile` :

```caddyfile
loko.wezon.fr {
    log {
        output file /var/log/caddy/loko.log
    }

    # ---------- BASIC-AUTH TEMPORAIRE ----------
    # Mot de passe genere : remplacer {HASH} par le resultat de :
    #   caddy hash-password --plaintext "VotreMotDePasse"
    basicauth * {
        loko {HASH}
    }
    # -------------------------------------------

    reverse_proxy localhost:8001 {
        header_up Host {host}
        header_up X-Real-IP {remote}
    }
}
```

**Procedure d'application** (2 minutes) :

```bash
ssh root@38.143.19.38

# 1. Generer le hash du mot de passe
caddy hash-password --plaintext "ChoisirUnMotDePasseFort2026!"
# Copier le hash affiche

# 2. Editer le Caddyfile
nano /etc/caddy/Caddyfile
# Remplacer le bloc loko.wezon.fr par la conf ci-dessus
# Remplacer {HASH} par le hash copie

# 3. Recharger Caddy
systemctl reload caddy

# 4. Verifier : le site demande maintenant un login/password
curl -I https://loko.wezon.fr
# Doit retourner 401 Unauthorized
```

### Alternative : arret complet du conteneur

Si le basic-auth pose probleme :

```bash
ssh root@38.143.19.38
cd /opt/loko && docker compose down
# Le site retournera 502 Bad Gateway — moins elegant mais efficace
```

### Apres securisation : prochaines etapes

1. Verifier les donnees presentes (O0-4 — commandes SSH ci-dessus)
2. Si donnees reelles : purger et rotater les secrets (admin token, secret key)
3. Decision humaine : deployer v1.3.4 sur wezon (hors scope de cette mission) ou garder la demo bloquee
4. Si deploiement v1.3.4 : la verification email (ACC-4) sera active, mais ajouter un captcha et/ou fermer le signup public serait plus robuste

---

## Decision humaine requise

| ID | Question | Options |
|----|----------|---------|
| **B-O0** | Securisation immediate de wezon | (a) Basic-auth Caddy / (b) Arret conteneur / (c) Autre |
| **B-O0-DATA** | Verification des donnees presentes | Connexion SSH requise |

**Statut** : en attente de decision humaine avant de poursuivre les lots OBS-1/2/3.
