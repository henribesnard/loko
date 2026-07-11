# Audit Logging Integration Guide (K2)

**Reference**: PLAN_AMELIORATION_COMPLET_LOKO_2026-07-10.md

Ce document explique comment intégrer l'audit logging dans les endpoints LOKO.

## Vue d'ensemble

Le système d'audit logging trace toutes les actions administratives et événements de sécurité dans une table append-only SQLite.

**Caractéristiques**:
- ✅ Append-only (pas de modification/suppression)
- ✅ Actions normées (e.g., `bot.create`, `auth.login_failed`)
- ✅ Sanitization automatique (passwords, tokens, messages)
- ✅ IP tracking
- ✅ Export CSV
- ✅ Purge automatique (aligné sur politique rétention)

## Actions standards

```python
from loko.db.audit import AuditLogger

# Bot management
AuditLogger.ACTION_BOT_CREATE = "bot.create"
AuditLogger.ACTION_BOT_UPDATE = "bot.update"
AuditLogger.ACTION_BOT_DELETE = "bot.delete"

# Intent management
AuditLogger.ACTION_INTENT_CREATE = "intent.create"
AuditLogger.ACTION_INTENT_DELETE = "intent.delete"

# API key management
AuditLogger.ACTION_KEY_CREATE = "key.create"
AuditLogger.ACTION_KEY_ROTATE = "key.rotate"
AuditLogger.ACTION_KEY_REVOKE = "key.revoke"

# Authentication
AuditLogger.ACTION_AUTH_LOGIN = "auth.login"
AuditLogger.ACTION_AUTH_LOGIN_FAILED = "auth.login_failed"
AuditLogger.ACTION_AUTH_LOGOUT = "auth.logout"
```

## Méthode 1: Logging manuel (recommandé pour auth)

Pour les endpoints d'authentification où vous devez logger les succès ET les échecs:

```python
from loko.api.audit_middleware import audit_log_sync, get_client_ip
from loko.db.audit import AuditLogger

@router.post("/api/auth/login")
async def login(request: Request, body: LoginRequest):
    ip = get_client_ip(request)

    # Vérifier credentials
    user = get_user_by_email(body.email)
    if not user or not verify_password(body.password, user.password_hash):
        # ❌ Échec: logger AVANT de raise
        audit_log_sync(
            action=AuditLogger.ACTION_AUTH_LOGIN_FAILED,
            ip_address=ip,
            details={"email": body.email, "reason": "invalid_credentials"}
        )
        raise HTTPException(401, "Invalid credentials")

    # ✅ Succès: logger après création session
    session_id = create_session(user.id)

    audit_log_sync(
        action=AuditLogger.ACTION_AUTH_LOGIN,
        user_id=user.id,
        ip_address=ip,
        details={"email": body.email}
    )

    return {"session_id": session_id}
```

## Méthode 2: Decorator (pour mutations admin)

Pour les endpoints CRUD qui réussissent toujours:

```python
from loko.api.audit_middleware import audit_log
from loko.db.audit import AuditLogger

@router.post("/api/bot")
@audit_log(action=AuditLogger.ACTION_BOT_CREATE)
async def create_bot(request: Request, bot: BotConfig):
    # Le decorator extrait automatiquement:
    # - user_id depuis request.state.user_id
    # - resource_id depuis result["id"] ou result["bot_id"]
    # - ip_address depuis request

    bot_id = save_bot(bot)
    return {"id": bot_id, "config": bot}
```

## Points d'intégration prioritaires

### 1. API Auth (`loko/api/user_auth.py`)

**À intégrer**:
- ✅ `POST /api/auth/login` → `ACTION_AUTH_LOGIN` (succès) + `ACTION_AUTH_LOGIN_FAILED` (échec)
- ✅ `POST /api/auth/signup` → `ACTION_AUTH_SIGNUP`
- ✅ `POST /api/auth/logout` → `ACTION_AUTH_LOGOUT`
- ✅ `POST /api/auth/reset-password` → `ACTION_AUTH_PASSWORD_RESET`
- ✅ `POST /api/auth/verify-email` → `ACTION_AUTH_EMAIL_VERIFY`

**Exemple d'intégration**:

```python
# En haut du fichier
from loko.api.audit_middleware import audit_log_sync, get_client_ip
from loko.db.audit import AuditLogger

# Dans l'endpoint login
@router.post("/login")
async def login(request: Request, body: LoginRequest, response: Response):
    ip = get_client_ip(request)
    _check_rate_limit(ip)
    _record_attempt(ip)

    user = get_user_by_email(body.email)

    if not user or not verify_password(body.password, user.password_hash):
        # Log échec
        audit_log_sync(
            action=AuditLogger.ACTION_AUTH_LOGIN_FAILED,
            ip_address=ip,
            details={"email": body.email}
        )
        raise HTTPException(401, "Email ou mot de passe incorrect.")

    if not user.is_verified:
        audit_log_sync(
            action=AuditLogger.ACTION_AUTH_LOGIN_FAILED,
            user_id=user.id,
            ip_address=ip,
            details={"email": body.email, "reason": "email_not_verified"}
        )
        raise HTTPException(403, "Email non verifie.")

    session_id = create_session(user.id)
    _set_session_cookie(response, session_id)

    # Log succès
    audit_log_sync(
        action=AuditLogger.ACTION_AUTH_LOGIN,
        user_id=user.id,
        ip_address=ip,
        details={"email": body.email}
    )

    return {"user_id": user.id, "email": user.email}
```

### 2. API Bot Admin (`loko/api/bot_admin.py`)

**À intégrer**:
- ✅ `POST /api/bot` → `ACTION_BOT_CREATE`
- ✅ `PUT /api/bot/{bot_id}` → `ACTION_BOT_UPDATE`
- ✅ `DELETE /api/bot/{bot_id}` → `ACTION_BOT_DELETE`
- ✅ `POST /api/bot/{bot_id}/intents` → `ACTION_INTENT_CREATE`
- ✅ `DELETE /api/bot/{bot_id}/intents/{intent_id}` → `ACTION_INTENT_DELETE`
- ✅ `POST /api/bot/{bot_id}/train` → `ACTION_MODEL_TRAIN`
- ✅ `POST /api/bot/{bot_id}/keys` → `ACTION_KEY_CREATE`

**Exemple**:

```python
from loko.api.audit_middleware import audit_log_sync, get_client_ip
from loko.db.audit import AuditLogger

@router.delete("/api/bot/{bot_id}")
async def delete_bot(bot_id: str, request: Request):
    # Vérifier permissions...
    user_id = request.state.user_id

    # Supprimer bot
    delete_bot_from_store(bot_id)

    # Log action
    audit_log_sync(
        action=AuditLogger.ACTION_BOT_DELETE,
        user_id=user_id,
        resource_id=bot_id,
        ip_address=get_client_ip(request)
    )

    return {"deleted": True}
```

### 3. API Keys (`loko/api/api_keys.py`)

**À intégrer** (K3):
- ✅ `POST /api/bot/{bot_id}/keys/rotate` → `ACTION_KEY_ROTATE`
- ✅ Expiration automatique → `ACTION_KEY_EXPIRED`

## Querying audit logs

### Via Python

```python
from loko.db.audit import AuditLogger
from datetime import datetime, timedelta, timezone

logger = AuditLogger()

# Tous les logs récents
logs = logger.get_logs(limit=100)

# Logs d'un utilisateur spécifique
user_logs = logger.get_logs(user_id="user123", limit=50)

# Échecs de connexion récents
failed_logins = logger.get_logs(
    action=AuditLogger.ACTION_AUTH_LOGIN_FAILED,
    since=datetime.now(timezone.utc) - timedelta(hours=24),
    limit=100
)

# Export CSV
logger.export_csv(
    "audit_export_2026-07.csv",
    since=datetime(2026, 7, 1, tzinfo=timezone.utc),
    until=datetime(2026, 7, 31, 23, 59, 59, tzinfo=timezone.utc)
)
```

### Via API (à implémenter)

```python
# À ajouter dans bot_admin.py ou ops.py

@router.get("/api/audit/logs")
async def get_audit_logs(
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 100,
    admin_token: str = Depends(verify_admin_token)
):
    """Get audit logs (admin only)."""
    logger = get_audit_logger()
    logs = logger.get_logs(user_id=user_id, action=action, limit=limit)
    return {"logs": logs}

@router.get("/api/audit/export")
async def export_audit_logs(
    since: Optional[str] = None,
    until: Optional[str] = None,
    admin_token: str = Depends(verify_admin_token)
):
    """Export audit logs as CSV (admin only)."""
    import tempfile
    from fastapi.responses import FileResponse

    logger = get_audit_logger()

    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        since_dt = datetime.fromisoformat(since) if since else None
        until_dt = datetime.fromisoformat(until) if until else None

        logger.export_csv(f.name, since=since_dt, until=until_dt)

        return FileResponse(
            f.name,
            media_type='text/csv',
            filename=f'audit_logs_{datetime.now().strftime("%Y%m%d")}.csv'
        )
```

## Purge automatique

Ajouter à cron (via le script backup):

```python
# Dans tools/backup_loko.sh ou cron séparé
from loko.db.audit import AuditLogger

logger = AuditLogger()
deleted = logger.purge_old_logs(days=365)  # Aligner sur politique rétention Q
print(f"Purged {deleted} old audit logs")
```

## Sécurité et RGPD

### ✅ Sanitization automatique

Le système sanitize automatiquement:
- `password`, `password_hash`, `token`, `api_key`, `secret`
- `message`, `content` (données conversationnelles)
- Toute clé contenant "password", "token", "secret", "key"

### ❌ Ne JAMAIS logger

- Mots de passe en clair
- Tokens/clés API
- Messages utilisateurs (conversations)
- Données personnelles sensibles

### ✅ OK à logger

- Actions administratives
- IDs (user_id, bot_id, resource_id)
- Emails (login attempts)
- IP addresses (sécurité)
- Métadonnées de configuration
- Raisons d'échec (generic)

## Tests

```bash
pytest tests/test_audit.py -v
```

Tests couverts:
- ✅ Log basique
- ✅ Sanitization (passwords, tokens, messages)
- ✅ Query par user/action/timestamp
- ✅ Export CSV
- ✅ Purge logs anciens
- ✅ Tracking tentatives login échouées

## Migration

1. **Aucune migration nécessaire** - Le système crée automatiquement `audit.db` au premier log
2. **Intégration progressive** - Ajouter l'audit logging endpoint par endpoint
3. **Priorités**:
   - Phase 1: Auth (login, signup, logout) - **sécurité critique**
   - Phase 2: Bot CRUD (create, update, delete) - **traçabilité**
   - Phase 3: API keys (rotate, revoke) - **K3 dépend de K2**

## Configuration

Variables d'environnement (optionnel):

```bash
# Path vers la base d'audit (défaut: .loko/audit.db)
LOKO_AUDIT_DB_PATH=/path/to/audit.db

# Rétention (jours, défaut: 365)
LOKO_AUDIT_RETENTION_DAYS=365
```

## Monitoring

Exemples de requêtes utiles pour le monitoring:

```python
# Détection brute force (> 10 échecs login sur 1h)
from collections import Counter

logger = AuditLogger()
failed = logger.get_logs(
    action=AuditLogger.ACTION_AUTH_LOGIN_FAILED,
    since=datetime.now(timezone.utc) - timedelta(hours=1),
    limit=1000
)

ip_counts = Counter(log["ip_address"] for log in failed)
suspicious_ips = {ip: count for ip, count in ip_counts.items() if count > 10}
print(f"Suspicious IPs: {suspicious_ips}")

# Actions par utilisateur
user_actions = logger.get_logs(user_id="user123", limit=50)
for log in user_actions:
    print(f"{log['timestamp']}: {log['action']} on {log['resource_id']}")
```

## Critères d'acceptation (K2)

- ✅ Chaque mutation admin produit exactement une ligne
- ✅ Tentative de connexion échouée journalisée
- ✅ Aucune donnée conversationnelle dans la table (test)
- ✅ Export CSV fonctionnel
- ✅ Purge automatique alignée sur politique Q

---

**Document établi le**: 10 juillet 2026
**Référence**: PLAN_AMELIORATION_COMPLET_LOKO_2026-07-10.md (K2)
