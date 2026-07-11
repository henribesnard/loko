# Déploiement Loko

## Infos serveur

- **URL** : https://loko.wezon.fr
- **VPS** : `38.143.19.38` (Ubuntu 24.04)
- **Utilisateur** : `root`
- **Répertoire** : `/opt/loko/`
- **Container** : `loko-loko-1` (port 8001 -> 8000)
- **Reverse proxy** : Caddy (TLS auto Let's Encrypt)
- **DNS** : Cloudflare, enregistrement A `loko` -> `38.143.19.38` (proxied)
- **Admin token** : variable `loko_Admin_token` dans `.env` local

## Architecture

```
Navigateur
  -> Cloudflare (DNS + proxy + TLS client)
    -> Caddy (VPS :443, TLS origin, reverse proxy)
      -> Docker loko (localhost:8001 -> :8000)
        -> Uvicorn / FastAPI
```

## Déploiement automatisé (GitHub Actions)

### Workflow

Le déploiement est automatisé via GitHub Actions (`.github/workflows/deploy.yml`).

**Déclenchement** : Création d'un tag de version (ex: `v0.3.9`)

```bash
# 1. Mettre à jour la version dans pyproject.toml
# version = "0.3.9"

# 2. Commit et push
git add pyproject.toml
git commit -m "chore: bump version to 0.3.9"
git push origin main

# 3. Créer et pousser le tag
git tag v0.3.9
git push origin v0.3.9

# ✅ GitHub Actions déploie automatiquement
```

**Étapes du workflow** :
1. Build de l'image Docker → push vers GitHub Container Registry
2. Connexion SSH au VPS
3. Pull du nouveau code (`git fetch --tags --force && git checkout v0.3.9`)
4. Pull de la nouvelle image Docker
5. Backup automatique (via `./tools/backup_loko.sh`)
6. Déploiement (`docker compose up -d --no-deps --build`)
7. Smoke test (health check sur `localhost:8001/health`)
8. Rollback automatique si échec
9. Création d'une GitHub Release

### Configuration requise (une seule fois)

#### 1. Clé SSH de déploiement

La clé SSH de déploiement est stockée localement dans `~/.ssh/loko_deploy` (déjà générée).

**Ajout de la clé publique au VPS** :
```bash
# La clé publique est déjà ajoutée dans /root/.ssh/authorized_keys
# Pour vérifier :
ssh -i ~/.ssh/loko_deploy root@38.143.19.38 "cat ~/.ssh/authorized_keys | grep github-actions-deploy"
```

#### 2. Secrets GitHub

Les secrets suivants sont configurés dans GitHub (Settings → Secrets and variables → Actions) :

- `DEPLOY_SSH_KEY` : Contenu de `~/.ssh/loko_deploy` (clé privée)
- `VPS_HOST` : `38.143.19.38`
- `VPS_USER` : `root`

**Vérification** :
```bash
gh secret list
```

**Modification** (si nécessaire) :
```bash
cat ~/.ssh/loko_deploy | gh secret set DEPLOY_SSH_KEY
echo "38.143.19.38" | gh secret set VPS_HOST
echo "root" | gh secret set VPS_USER
```

### Surveillance du déploiement

```bash
# Lister les déploiements récents
gh run list --workflow=deploy.yml --limit=5

# Surveiller un déploiement en cours
gh run watch <run-id>

# Voir les logs d'un déploiement
gh run view <run-id> --log
```

### Rollback manuel

Si le déploiement automatique échoue ou si vous devez revenir en arrière :

```bash
ssh root@38.143.19.38
cd /opt/loko

# Lister les tags disponibles
git tag | sort -V | tail -5

# Revenir à une version précédente
git fetch --tags --force
git checkout v0.3.8
docker compose pull
docker compose up -d --build

# Vérifier
curl http://localhost:8001/health
```

## Mise à jour manuelle (si GitHub Actions ne fonctionne pas)

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
```

## Configuration VPS

Le fichier `/opt/loko/.env` sur le VPS contient :

```env
# Admin token pour accès à /api/docs et endpoints admin
LOKO_ADMIN_TOKEN=<valeur de loko_Admin_token du .env local>

# CORS origins (important pour sécurité)
LOKO_CORS_ORIGINS=https://loko.wezon.fr

# Mode serveur (important pour activer les protections de sécurité)
LOKO_MODE=server

# API Keys (si nécessaire)
DEEPSEEK_API_KEY=<si utilisé>
COHERE_API_KEY=<si utilisé>
```

**Variables importantes** :
- `LOKO_ADMIN_TOKEN` : Token d'administration (doit correspondre à `loko_Admin_token` dans `.env` local)
- `LOKO_MODE=server` : Active les protections de sécurité (protection /api/docs, etc.)
- `LOKO_CORS_ORIGINS` : Liste des origines autorisées pour CORS

Pour modifier le token : mettre à jour les deux `.env` (local et VPS) puis `docker compose up -d`.

## Rollback

```bash
cd /opt/loko
git log --oneline -5
git checkout <commit>
docker compose up -d --build
```

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

Après modification du Caddyfile :
```bash
systemctl reload caddy
```

## Troubleshooting

### Le déploiement GitHub Actions échoue

**1. Erreur de connexion SSH**
```bash
# Vérifier que la clé SSH fonctionne
ssh -i ~/.ssh/loko_deploy root@38.143.19.38 "echo 'SSH OK'"

# Vérifier les secrets GitHub
gh secret list
```

**2. Erreur "git fetch --tags" (conflit de tags)**
- Résolu dans le workflow avec `git fetch --tags --force`
- Si ça persiste, supprimer les tags locaux sur le VPS :
```bash
ssh root@38.143.19.38 "cd /opt/loko && git tag -d v0.3.9"
```

**3. Smoke test échoue**
```bash
# Vérifier que l'application répond
ssh root@38.143.19.38 "curl -f http://localhost:8001/health"

# Vérifier les logs
ssh root@38.143.19.38 "cd /opt/loko && docker compose logs --tail=50"
```

### L'application ne répond pas

```bash
# Vérifier que le container tourne
ssh root@38.143.19.38 "docker ps --filter name=loko"

# Vérifier les logs
ssh root@38.143.19.38 "cd /opt/loko && docker compose logs --tail=100"

# Redémarrer le container
ssh root@38.143.19.38 "cd /opt/loko && docker compose restart"

# Vérifier Caddy
ssh root@38.143.19.38 "systemctl status caddy"
ssh root@38.143.19.38 "tail -50 /var/log/caddy/loko.log"
```

### Erreur 502 Bad Gateway

```bash
# Caddy ne peut pas joindre le container
# Vérifier que le container écoute sur le bon port
ssh root@38.143.19.38 "ss -tlnp | grep 8001"

# Vérifier la configuration Caddy
ssh root@38.143.19.38 "cat /etc/caddy/Caddyfile | grep -A 5 loko.wezon.fr"
```

### Accès à /api/docs refusé

```bash
# En mode server, /api/docs nécessite le token admin
# Accès avec token :
curl -H "Authorization: Bearer $LOKO_ADMIN_TOKEN" https://loko.wezon.fr/api/docs

# Ou via query param (navigateur) :
open "https://loko.wezon.fr/api/docs?token=$LOKO_ADMIN_TOKEN"

# Vérifier que le token est configuré sur le VPS
ssh root@38.143.19.38 "cd /opt/loko && grep LOKO_ADMIN_TOKEN .env"
```

## Checklist pré-déploiement

- [ ] Version mise à jour dans `pyproject.toml`
- [ ] Tous les tests passent : `python -m pytest`
- [ ] Build TypeScript réussit : `cd desktop && npm run build`
- [ ] Pas de secrets committé : vérifier Secret Guard
- [ ] Git status propre ou changements stagés
- [ ] Tag de version créé et poussé

## Checklist post-déploiement

- [ ] Health check répond : `curl https://loko.wezon.fr/health`
- [ ] Application accessible : `open https://loko.wezon.fr`
- [ ] Logs sans erreur : `ssh root@38.143.19.38 "cd /opt/loko && docker compose logs --tail=20"`
- [ ] Version correcte déployée : `ssh root@38.143.19.38 "cd /opt/loko && git describe --tags"`
- [ ] GitHub Release créée (si workflow réussi)
