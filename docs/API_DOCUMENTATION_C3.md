# C3: Documentation API (Swagger/OpenAPI)

**Reference**: PLAN_AMELIORATION_COMPLET_LOKO_2026-07-10.md

## Endpoints disponibles

La documentation API OpenAPI est exposée à trois endpoints :

- **`/api/docs`** : Interface Swagger UI (interactive)
- **`/api/redoc`** : Documentation ReDoc (alternative)
- **`/api/openapi.json`** : Schéma OpenAPI brut (JSON)

## Protection par admin token

### Mode server (production)

En mode server, tous les endpoints de documentation sont **protégés par admin token**.

**Accès requis** :
```bash
# Variable d'environnement requise
LOKO_ADMIN_TOKEN=your_secure_token_here
```

**Méthodes d'authentification** :

1. **Header Authorization** (API/curl) :
```bash
curl -H "Authorization: Bearer $LOKO_ADMIN_TOKEN" \
  https://loko.wezon.fr/api/openapi.json
```

2. **Query parameter** (navigateur) :
```
https://loko.wezon.fr/api/docs?token=YOUR_ADMIN_TOKEN
```

Cette méthode permet d'ouvrir Swagger UI directement dans le navigateur.

### Mode desktop (développement)

En mode desktop, la documentation est **accessible sans token** :

```
http://localhost:8000/api/docs
http://localhost:8000/api/redoc
```

## Usage

### Swagger UI (interface interactive)

```bash
# Production (avec token)
open "https://loko.wezon.fr/api/docs?token=$LOKO_ADMIN_TOKEN"

# Développement (sans token)
open "http://localhost:8000/api/docs"
```

**Fonctionnalités** :
- Explore tous les endpoints API
- Test des requêtes directement depuis l'interface
- Schémas de requête/réponse
- Exemples de code

### ReDoc (documentation alternative)

```bash
# Production
open "https://loko.wezon.fr/api/redoc?token=$LOKO_ADMIN_TOKEN"

# Développement
open "http://localhost:8000/api/redoc"
```

**Avantages** :
- Vue plus compacte et lisible
- Navigation par tags
- Pas d'interactivité (lecture seule)

### Schéma OpenAPI brut

```bash
# Télécharger le schéma
curl -H "Authorization: Bearer $LOKO_ADMIN_TOKEN" \
  https://loko.wezon.fr/api/openapi.json > openapi.json

# Générer des clients avec openapi-generator
openapi-generator-cli generate -i openapi.json -g python -o ./client
```

## Sécurité

### ✅ Protection implémentée

1. **Admin token obligatoire en production** :
   - Header `Authorization: Bearer <token>`
   - Query param `?token=<token>` (pour navigateur)

2. **Comparaison HMAC** :
   - Utilise `hmac.compare_digest()` pour éviter timing attacks

3. **Fail-closed** :
   - Si `LOKO_ADMIN_TOKEN` absent en mode server → 503 Service Unavailable
   - Si token invalide → 401 Unauthorized

4. **Mode desktop exempt** :
   - Pas de protection en mode desktop (environnement de développement sécurisé)

### ❌ Limites

- **Token en query string** : visible dans les logs HTTP/navigateur
  - ⚠️ À utiliser uniquement pour accès manuel temporaire
  - Préférer header Authorization pour scripts/automation

- **Pas de rate limiting spécifique** : utilise le rate limiting global de l'API

## Implémentation

### main.py

```python
# Configuration FastAPI
app = FastAPI(
    title="LOKO API",
    version=__version__,
    description="Deterministic chatbot platform for customer service.",
    docs_url="/api/docs",       # Swagger UI
    redoc_url="/api/redoc",     # ReDoc
    openapi_url="/api/openapi.json",
)

# Middleware de protection
class APIDocsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        mode = get_env("MODE", "desktop")
        docs_paths = ["/api/docs", "/api/redoc", "/api/openapi.json"]

        if mode == "server" and request.url.path in docs_paths:
            # Vérifier admin token (header ou query param)
            ...

app.add_middleware(APIDocsMiddleware)
```

### Ordre des middlewares

```
Requête HTTP
    ↓
CORSMiddleware (CORS headers)
    ↓
CSRFMiddleware (CSRF protection)
    ↓
SecurityHeadersMiddleware (X-Frame-Options, CSP, etc.)
    ↓
APIDocsMiddleware (protection /api/docs)
    ↓
Rate limiting (slowapi)
    ↓
Routes FastAPI
```

## Tests

### Test accès avec token

```bash
# Swagger UI
curl -I -H "Authorization: Bearer $LOKO_ADMIN_TOKEN" \
  https://loko.wezon.fr/api/docs

# Devrait retourner 200 OK

# Sans token
curl -I https://loko.wezon.fr/api/docs

# Devrait retourner 401 Unauthorized
```

### Test mode desktop

```bash
# Démarrer en mode desktop
export LOKO_MODE=desktop
uvicorn loko.main:app --reload

# Accès sans token
curl -I http://localhost:8000/api/docs
# → 200 OK
```

### Test schéma OpenAPI

```bash
# Vérifier que le schéma est valide
curl -H "Authorization: Bearer $LOKO_ADMIN_TOKEN" \
  https://loko.wezon.fr/api/openapi.json | jq '.info'

# Output attendu:
# {
#   "title": "LOKO API",
#   "description": "Deterministic chatbot platform for customer service.",
#   "version": "0.3.8"
# }
```

## Documentation publique (décision produit)

**Statut actuel** : Documentation interne uniquement (admin token requis)

**Options futures** (décision à prendre à E7) :

1. **Garder interne** (recommandé pour E6) :
   - Avantage : Contrôle total de l'accès
   - Inconvénient : Nécessite partage du token admin pour consulter

2. **Version publique anonyme** :
   - Créer endpoint `/api/public/docs` sans protection
   - Épurer le schéma OpenAPI (exclure endpoints admin)
   - Avantage : Facilite intégration par clients
   - Inconvénient : Exposition de la surface d'attaque

3. **Documentation statique** :
   - Générer documentation HTML statique (via redocly)
   - Héberger sur site séparé (docs.loko.wezon.fr)
   - Avantage : Meilleur contrôle, SEO, versionning
   - Inconvénient : Nécessite processus de génération/déploiement

**Recommandation E6** : Garder interne avec admin token. Ré-évaluer à E7 si besoin client.

## Cas d'usage

### Développeur client (intégration bot)

```bash
# 1. Obtenir le schéma OpenAPI
curl -H "Authorization: Bearer $TOKEN" \
  https://loko.wezon.fr/api/openapi.json > loko-api.json

# 2. Générer client TypeScript
npx @openapitools/openapi-generator-cli generate \
  -i loko-api.json \
  -g typescript-axios \
  -o ./src/loko-client

# 3. Utiliser le client
import { Configuration, BotPublicApi } from './loko-client';

const api = new BotPublicApi(
  new Configuration({ apiKey: 'bot_key_...' })
);

const session = await api.createSession({ bot_id: 'demo' });
```

### Administrateur système (debug)

```bash
# Explorer l'API rapidement dans le navigateur
open "https://loko.wezon.fr/api/docs?token=$LOKO_ADMIN_TOKEN"

# Tester un endpoint directement depuis Swagger UI
# → Cliquer sur "Try it out"
# → Remplir les paramètres
# → "Execute"
```

### Auditeur sécurité (E6)

```bash
# Vérifier tous les endpoints exposés
curl -H "Authorization: Bearer $TOKEN" \
  https://loko.wezon.fr/api/openapi.json | \
  jq '.paths | keys[]'

# Vérifier schémas de sécurité
curl -H "Authorization: Bearer $TOKEN" \
  https://loko.wezon.fr/api/openapi.json | \
  jq '.components.securitySchemes'
```

## Checklist C3

- ✅ FastAPI configuré avec `/api/docs`, `/api/redoc`, `/api/openapi.json`
- ✅ Middleware de protection par admin token (mode server)
- ✅ Support header `Authorization: Bearer <token>`
- ✅ Support query param `?token=<token>` (navigateur)
- ✅ Fail-closed si token absent/invalide en mode server
- ✅ Mode desktop exempt de protection
- ✅ Documentation d'accès et d'usage

## Intégration avec déploiement (E8)

Après déploiement, vérifier que la documentation est accessible :

```bash
# Test post-déploiement
curl -H "Authorization: Bearer $LOKO_ADMIN_TOKEN" \
  https://loko.wezon.fr/api/openapi.json

# Devrait retourner schéma JSON valide

# Ouvrir Swagger UI
open "https://loko.wezon.fr/api/docs?token=$LOKO_ADMIN_TOKEN"
```

---

**Document établi le** : 10 juillet 2026
**Référence** : PLAN_AMELIORATION_COMPLET_LOKO_2026-07-10.md (C3)
