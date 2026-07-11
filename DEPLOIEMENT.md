# Deploiement Loko

## Infos serveur

- **URL** : https://loko.wezon.fr
- **VPS** : `38.143.19.38` (Ubuntu 24.04)
- **Utilisateur** : `root`
- **Repertoire** : `/opt/loko/`
- **Container** : `loko-loko-1` (port 8001 -> 8000)
- **Reverse proxy** : Caddy (TLS auto Let's Encrypt)
- **DNS** : Cloudflare, enregistrement A `loko` -> `38.143.19.38` (proxied)
- **Registry** : `ghcr.io/henribesnard/loko` (GitHub Container Registry)
- **Admin token** : variable `loko_Admin_token` dans `.env` local

## Architecture

```
Navigateur
  -> Cloudflare (DNS + proxy + TLS client)
    -> Caddy (VPS :443, TLS origin, reverse proxy)
      -> Docker loko (localhost:8001 -> :8000)
        -> Uvicorn / FastAPI
```

## Versioning

La version est gérée dans `pyproject.toml` et propagée automatiquement :
- **Source** : `pyproject.toml` → `version = "X.Y.Z"`
- **Git tags** : `vX.Y.Z` (déclenche le déploiement automatique)
- **Images Docker** : `ghcr.io/henribesnard/loko:X.Y.Z` + `:latest`
- **Vérification** : `curl https://loko.wezon.fr/health` → retourne `{"version": "X.Y.Z"}`

### Historique des versions

```bash
# Voir toutes les versions disponibles
git tag -l "v*.*.*" --sort=-version:refname

# Depuis le VPS
./tools/deploy_version.sh --list
```

## Deploiement automatise (GitHub Actions)

### Workflow

Le deploiement est automatise via GitHub Actions (`.github/workflows/deploy.yml`).

**Declenchement** : Creation d'un tag de version (ex: `v0.3.9`)

```bash
# 1. Mettre a jour la version dans pyproject.toml
# version = "0.4.0"

# 2. Commit et push
git add pyproject.toml
git commit -m "chore: bump version to 0.4.0"
git push origin main

# 3. Creer et pousser le tag
git tag v0.4.0
git push origin v0.4.0

# GitHub Actions deploie automatiquement
```

**Etapes du workflow** :
1. Build de l'image Docker → push vers GHCR (`ghcr.io/henribesnard/loko:0.4.0` + `:latest`)
2. Connexion SSH au VPS
3. Checkout du tag git (`git checkout v0.4.0`)
4. Backup automatique (via `./tools/backup_loko.sh`)
5. Pull de l'image pre-built depuis GHCR (via `docker-compose.prod.yml`)
6. Deploiement (`docker compose up -d`)
7. Smoke test (health check + verification version)
8. **Rollback automatique** si le smoke test echoue
9. Creation d'une GitHub Release

### Configuration requise (une seule fois)

#### 1. Cle SSH de deploiement

La cle SSH de deploiement est stockee localement dans `~/.ssh/loko_deploy` (deja generee).

**Ajout de la cle publique au VPS** :
```bash
# La cle publique est deja ajoutee dans /root/.ssh/authorized_keys
# Pour verifier :
ssh -i ~/.ssh/loko_deploy root@38.143.19.38 "cat ~/.ssh/authorized_keys | grep github-actions-deploy"
```

#### 2. Secrets GitHub

Les secrets suivants sont configures dans GitHub (Settings → Secrets and variables → Actions) :

- `DEPLOY_SSH_KEY` : Contenu de `~/.ssh/loko_deploy` (cle privee)
- `VPS_HOST` : `38.143.19.38`
- `VPS_USER` : `root`

**Verification** :
```bash
gh secret list
```

**Modification** (si necessaire) :
```bash
cat ~/.ssh/loko_deploy | gh secret set DEPLOY_SSH_KEY
echo "38.143.19.38" | gh secret set VPS_HOST
echo "root" | gh secret set VPS_USER
```

### Surveillance du deploiement

```bash
# Lister les deploiements recents
gh run list --workflow=deploy.yml --limit=5

# Surveiller un deploiement en cours
gh run watch <run-id>

# Voir les logs d'un deploiement
gh run view <run-id> --log
```

## Rollback

### Methode rapide (script)

Depuis le VPS, utiliser le script de rollback :

```bash
ssh root@38.143.19.38
cd /opt/loko

# Rollback automatique vers la version precedente
./tools/rollback_loko.sh

# Rollback vers une version specifique
./tools/rollback_loko.sh 0.3.8

# Voir les versions disponibles et la version courante
./tools/rollback_loko.sh --list
```

Le script :
1. Detecte la version courante (via `/health`)
2. Cree un backup avant le rollback
3. Pull l'image Docker de la version cible depuis GHCR
4. Deploie et verifie la sante
5. Rollback automatique si la version cible echoue aussi
6. Log toutes les operations dans `.deploy_history`

### Methode manuelle

Si les scripts ne fonctionnent pas :

```bash
ssh root@38.143.19.38
cd /opt/loko

# 1. Voir les versions disponibles
git tag -l "v*.*.*" --sort=-version:refname | head -10

# 2. Checkout de la version cible
git fetch --tags --force
git checkout v0.3.8

# 3. Deployer avec l'image GHCR
export LOKO_VERSION=0.3.8
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 4. Verifier
curl http://localhost:8001/health
# Doit retourner: {"status":"ok","service":"loko-bot","version":"0.3.8"}
```

### Deployer une version specifique (sans rollback)

```bash
ssh root@38.143.19.38
cd /opt/loko

# Deployer n'importe quelle version
./tools/deploy_version.sh 0.3.7

# Sans backup (plus rapide)
./tools/deploy_version.sh 0.3.7 --no-backup
```

### Historique des deployments

Le fichier `/opt/loko/.deploy_history` trace tous les deploiements et rollbacks :

```bash
cat /opt/loko/.deploy_history
# 2026-07-11 14:30:00 | DEPLOYED | v0.4.0 (was: v0.3.9)
# 2026-07-11 15:00:00 | FAILED+ROLLBACK | v0.4.1 (was: v0.4.0)
```

## Mise a jour manuelle (si GitHub Actions ne fonctionne pas)

```bash
ssh root@38.143.19.38
cd /opt/loko
git pull origin main
docker compose up -d --build
```

Verification :

```bash
docker ps --filter name=loko
curl http://localhost:8001/health
```

## Commandes utiles

```bash
# Version en production
curl -s https://loko.wezon.fr/health | python3 -c "import sys,json; print(json.load(sys.stdin)['version'])"

# Logs applicatifs
docker logs loko-loko-1 --tail 100 -f

# Logs Caddy
tail -f /var/log/caddy/loko.log

# Redemarrer le container
cd /opt/loko && docker compose restart

# Redemarrer Caddy (apres modif Caddyfile)
systemctl reload caddy

# Arreter Loko
cd /opt/loko && docker compose down

# Arreter + supprimer les donnees
cd /opt/loko && docker compose down -v

# Historique des deploiements
cat /opt/loko/.deploy_history
```

## Configuration VPS

Le fichier `/opt/loko/.env` sur le VPS contient :

```env
# Admin token pour acces a /api/docs et endpoints admin
LOKO_ADMIN_TOKEN=<valeur de loko_Admin_token du .env local>

# CORS origins (important pour securite)
LOKO_CORS_ORIGINS=https://loko.wezon.fr

# Mode serveur (important pour activer les protections de securite)
LOKO_MODE=server

# API Keys (si necessaire)
DEEPSEEK_API_KEY=<si utilise>
COHERE_API_KEY=<si utilise>
```

**Variables importantes** :
- `LOKO_ADMIN_TOKEN` : Token d'administration (doit correspondre a `loko_Admin_token` dans `.env` local)
- `LOKO_MODE=server` : Active les protections de securite (protection /api/docs, etc.)
- `LOKO_CORS_ORIGINS` : Liste des origines autorisees pour CORS

Pour modifier le token : mettre a jour les deux `.env` (local et VPS) puis `docker compose up -d`.

## Caddy

Bloc dans `/etc/caddy/Caddyfile` :

```caddyfile
loko.wezon.fr {
    log {
        output file /var/log/caddy/loko.log
    }
    reverse_proxy localhost:8001 {
        header_up Host {host}
        header_up X-Real-IP {remote}
    }
}
```

Apres modification du Caddyfile :
```bash
systemctl reload caddy
```

## Troubleshooting

### Le deploiement GitHub Actions echoue

**1. Erreur de connexion SSH**
```bash
# Verifier que la cle SSH fonctionne
ssh -i ~/.ssh/loko_deploy root@38.143.19.38 "echo 'SSH OK'"

# Verifier les secrets GitHub
gh secret list
```

**2. Erreur "git fetch --tags" (conflit de tags)**
- Resolu dans le workflow avec `git fetch --tags --force`
- Si ca persiste, supprimer les tags locaux sur le VPS :
```bash
ssh root@38.143.19.38 "cd /opt/loko && git tag -d v0.3.9"
```

**3. Smoke test echoue**
```bash
# Verifier que l'application repond
ssh root@38.143.19.38 "curl -f http://localhost:8001/health"

# Verifier les logs
ssh root@38.143.19.38 "cd /opt/loko && docker compose logs --tail=50"
```

**4. Mauvaise version deployee**
```bash
# Verifier la version via health endpoint
curl -s https://loko.wezon.fr/health

# Verifier le tag git sur le VPS
ssh root@38.143.19.38 "cd /opt/loko && git describe --tags"

# Verifier l'image Docker
ssh root@38.143.19.38 "docker inspect loko-loko-1 --format '{{.Config.Image}}'"
```

### L'application ne repond pas

```bash
# Verifier que le container tourne
ssh root@38.143.19.38 "docker ps --filter name=loko"

# Verifier les logs
ssh root@38.143.19.38 "cd /opt/loko && docker compose logs --tail=100"

# Redemarrer le container
ssh root@38.143.19.38 "cd /opt/loko && docker compose restart"

# Verifier Caddy
ssh root@38.143.19.38 "systemctl status caddy"
ssh root@38.143.19.38 "tail -50 /var/log/caddy/loko.log"
```

### Erreur 502 Bad Gateway

```bash
# Caddy ne peut pas joindre le container
# Verifier que le container ecoute sur le bon port
ssh root@38.143.19.38 "ss -tlnp | grep 8001"

# Verifier la configuration Caddy
ssh root@38.143.19.38 "cat /etc/caddy/Caddyfile | grep -A 5 loko.wezon.fr"
```

### Acces a /api/docs refuse

```bash
# En mode server, /api/docs necessite le token admin
# Acces avec token :
curl -H "Authorization: Bearer $LOKO_ADMIN_TOKEN" https://loko.wezon.fr/api/docs

# Ou via query param (navigateur) :
open "https://loko.wezon.fr/api/docs?token=$LOKO_ADMIN_TOKEN"

# Verifier que le token est configure sur le VPS
ssh root@38.143.19.38 "cd /opt/loko && grep LOKO_ADMIN_TOKEN .env"
```

## Checklist pre-deploiement

- [ ] Version mise a jour dans `pyproject.toml`
- [ ] Tous les tests passent : `python -m pytest`
- [ ] Build TypeScript reussit : `cd desktop && npm run build`
- [ ] Pas de secrets commite : verifier Secret Guard
- [ ] Git status propre ou changements stages
- [ ] Tag de version cree et pousse

## Checklist post-deploiement

- [ ] Health check repond : `curl https://loko.wezon.fr/health`
- [ ] Version correcte : `curl -s https://loko.wezon.fr/health | python3 -c "import sys,json; print(json.load(sys.stdin)['version'])"`
- [ ] Application accessible : `open https://loko.wezon.fr`
- [ ] Logs sans erreur : `ssh root@38.143.19.38 "cd /opt/loko && docker compose logs --tail=20"`
- [ ] GitHub Release creee (si workflow reussi)
