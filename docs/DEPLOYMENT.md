# Déploiement LOKO (C3)

**Reference**: PLAN_AMELIORATION_COMPLET_LOKO_2026-07-10.md

## Processus de déploiement automatisé

### Workflow

Le déploiement est déclenché automatiquement sur **tag de version** :

```bash
# 1. Finaliser les changements sur main
git checkout main
git pull

# 2. Mettre à jour la version dans pyproject.toml
# version = "0.3.8"

# 3. Créer et pousser le tag
git tag v0.3.8
git push origin v0.3.8

# ✅ GitHub Actions déploie automatiquement
```

### Étapes automatiques

Le workflow [.github/workflows/deploy.yml](.github/workflows/deploy.yml) exécute :

1. **Build Docker image**
   - Build multi-stage
   - Push vers GitHub Container Registry
   - Tags: `v0.3.8` + `latest`

2. **Déploiement VPS**
   - SSH vers VPS
   - `git checkout v0.3.8`
   - `docker compose pull`
   - **Backup automatique** avant deploy
   - `docker compose up -d --no-deps`

3. **Smoke test**
   - Attend 10s
   - Vérifie `/health` pendant 60s max
   - Si échec → rollback automatique

4. **Rollback automatique** (si échec)
   - Retour au tag précédent
   - Redéploiement version stable

5. **GitHub Release**
   - Création release automatique
   - Notes de version

### Configuration requise

**Secrets GitHub** (Settings → Secrets and variables → Actions):

```
DEPLOY_SSH_KEY    : Clé SSH privée pour déploiement
VPS_HOST          : 38.143.19.38 (ou loko.wezon.fr)
VPS_USER          : ubuntu (ou autre user)
```

**Setup SSH sur VPS**:

```bash
# Sur votre machine locale
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/loko_deploy
# → Copier la clé privée dans DEPLOY_SSH_KEY

# Sur le VPS
ssh ubuntu@38.143.19.38
mkdir -p ~/.ssh
nano ~/.ssh/authorized_keys
# → Coller la clé publique (loko_deploy.pub)

# Tester
ssh -i ~/.ssh/loko_deploy ubuntu@38.143.19.38
```

## Déploiement manuel (fallback)

Si le workflow échoue, déploiement manuel possible :

```bash
# SSH vers VPS
ssh ubuntu@38.143.19.38

cd /opt/loko

# Backup
./tools/backup_loko.sh

# Pull code
git fetch --tags
git checkout v0.3.8

# Deploy
docker compose pull
docker compose up -d

# Verify
curl http://localhost:8000/health
curl https://loko.wezon.fr/health
```

## Rollback manuel

```bash
ssh ubuntu@38.143.19.38
cd /opt/loko

# Trouver version précédente
git tag | sort -V | tail -n 2

# Rollback
git checkout v0.3.7
docker compose up -d

# Verify
curl http://localhost:8000/health
```

## Vérifications post-déploiement

### 1. Health checks

```bash
# Basic health
curl https://loko.wezon.fr/health

# Detailed health (admin token requis)
curl -H "Authorization: Bearer $LOKO_ADMIN_TOKEN" \
  https://loko.wezon.fr/health/detailed
```

### 2. Logs

```bash
# Logs récents
docker compose logs loko --tail=100 --follow

# Erreurs
docker compose logs loko | grep ERROR
```

### 3. Métriques

```bash
# Prometheus metrics (admin token requis)
curl -H "Authorization: Bearer $LOKO_ADMIN_TOKEN" \
  http://localhost:8000/metrics
```

### 4. Tests fonctionnels

```bash
# API publique
curl https://loko.wezon.fr/api/v1/health

# Liste bots (admin)
curl -H "Authorization: Bearer $LOKO_ADMIN_TOKEN" \
  https://loko.wezon.fr/api/bot

# Test bot (avec API key)
curl -X POST https://loko.wezon.fr/api/v1/bot/demo/session \
  -H "Authorization: Bearer $BOT_API_KEY"
```

## Monitoring post-déploiement

### UptimeRobot

Vérifie automatiquement après deploy :
- Monitor existant détecte uptime
- Alerte si down > 10 min

### Prometheus/AlertManager

Surveille :
- Taux d'erreur
- Latence P95
- Backup age

Si dégradation détectée → alerte automatique

## Checklist déploiement

**Avant**:
- [ ] Tests verts (CI)
- [ ] Version bumped dans pyproject.toml
- [ ] CHANGELOG mis à jour
- [ ] Backup récent disponible (< 24h)

**Pendant**:
- [ ] Tag créé et poussé
- [ ] Workflow GitHub Actions vert
- [ ] Smoke test health check passé

**Après**:
- [ ] Health check manuel
- [ ] Logs sans erreurs
- [ ] Tests fonctionnels OK
- [ ] Monitoring stable (15 min)
- [ ] GitHub Release créée

## Troubleshooting

### Build Docker échoue

```bash
# Localement
docker build -t loko:test .

# Si succès local mais échec CI → cache
# → Invalider cache GitHub Actions
```

### Smoke test échoue

```bash
# Vérifier logs
ssh ubuntu@38.143.19.38
cd /opt/loko
docker compose logs loko --tail=50

# Vérifier containers
docker compose ps

# Redémarrer si nécessaire
docker compose restart loko
```

### Rollback automatique échoué

```bash
# Rollback manuel immédiat
ssh ubuntu@38.143.19.38
cd /opt/loko

# Version stable connue
git checkout v0.3.7
docker compose up -d
```

## Documentation API (C3)

La documentation OpenAPI est exposée à `/api/docs` (Swagger UI).

### Configuration

Dans `loko/main.py`, FastAPI expose automatiquement :

```python
app = FastAPI(
    title="LOKO API",
    description="Deterministic chatbot platform",
    version="0.3.8",
    docs_url="/api/docs",      # Swagger UI
    redoc_url="/api/redoc",    # ReDoc
    openapi_url="/api/openapi.json",
)
```

### Accès

**En mode server** (production) :
- `/api/docs` : **Protégé par admin token** (recommandé)
- `/api/redoc` : Documentation alternative
- `/api/openapi.json` : Schéma OpenAPI brut

**Protection** (à ajouter dans auth.py) :

```python
from fastapi import Request, HTTPException

@app.middleware("http")
async def protect_docs(request: Request, call_next):
    if request.url.path in ["/api/docs", "/api/redoc", "/api/openapi.json"]:
        # Require admin token
        auth_header = request.headers.get("Authorization")
        if not auth_header or not verify_admin_token(auth_header):
            raise HTTPException(401, "Unauthorized")

    return await call_next(request)
```

### Usage

```bash
# Accès avec admin token
open "https://loko.wezon.fr/api/docs?token=$LOKO_ADMIN_TOKEN"

# Ou via curl
curl -H "Authorization: Bearer $LOKO_ADMIN_TOKEN" \
  https://loko.wezon.fr/api/openapi.json > openapi.json
```

### Documentation publique (décision produit)

**Actuellement** : Docs protégées par admin token (internal only)

**Option future** : Docs publiques anonymes
- Décision à prendre à E7
- Si oui : créer version publique épurée (sans endpoints admin)
- Si non : garder protection admin token

## Historique versions

| Version | Date | Changements principaux |
|---------|------|------------------------|
| v0.3.7 | 2026-07-09 | Scrub client mentions, CI guard |
| v0.3.8 | 2026-07-10 | Improvement plan waves 0-2 |

## Runbook E8

Procédure complète de mise en service (E8) :

1. **Déploiement** (ce document)
2. **Vérification E8-2** : Test restauration backup → bot identique
3. **Vérification E8-3** : Incident simulé (suppression modèle) → alerte < 5 min
4. **Documentation** : Runbook complet pour l'équipe ops

---

**Document établi le** : 10 juillet 2026
**Référence** : PLAN_AMELIORATION_COMPLET_LOKO_2026-07-10.md (C3)
