# K4: Rate Limiting Composite (IP + API key)

**Reference**: PLAN_AMELIORATION_COMPLET_LOKO_2026-07-10.md

## Objectif

Empêcher le contournement du rate limiting par rotation d'IPs.

## Implementation

### Clé composite

```python
# loko/api/rate_limit.py

def get_rate_limit_key(request: Request, api_key_record: Optional[APIKeyRecord] = None) -> str:
    """
    Generate composite rate limit key.

    Returns:
        - "(ip, api_key)" if API key present
        - "ip" if no API key (fallback)
    """
    ip = get_client_ip(request)

    if api_key_record:
        return f"{ip}:{api_key_record.key_id}"

    return ip
```

### Plafond global par API key

```python
# Dans bot_public.py

from slowapi import Limiter
from slowapi.util import get_remote_address

# Limiter par IP (existant)
limiter_ip = Limiter(key_func=get_remote_address)

# Nouveau: limiter par API key (global, tous IPs confondus)
from collections import defaultdict
import time

_api_key_buckets: dict[str, list[float]] = defaultdict(list)

def check_api_key_rate_limit(api_key_id: str, max_requests: int = 1000, window_seconds: int = 3600):
    """Check global rate limit per API key (across all IPs)."""
    now = time.time()
    bucket = _api_key_buckets[api_key_id]

    # Remove old entries
    _api_key_buckets[api_key_id] = [t for t in bucket if now - t < window_seconds]

    if len(_api_key_buckets[api_key_id]) >= max_requests:
        raise HTTPException(429, f"API key rate limit exceeded ({max_requests}/{window_seconds}s)")

    _api_key_buckets[api_key_id].append(now)


# Dans l'endpoint de message
@router.post("/api/v1/bot/{bot_id}/message")
@limiter_ip.limit("30/minute")  # Par IP (existant)
async def send_message(bot_id: str, request: Request, ...):
    # Extraire API key
    api_key_record = ... # depuis header Authorization

    # Check global API key limit (nouveau)
    if api_key_record:
        check_api_key_rate_limit(api_key_record.key_id, max_requests=1000, window_seconds=3600)

    # ... rest of handler
```

### Configuration

```bash
# .env
LOKO_RATE_API_KEY_MAX=1000  # Max requests per API key per hour
```

## Critères d'acceptation

- ✅ Rafale multi-IP sur une même clé → 429 au plafond global
- ✅ Les limites existantes (par IP) non régressées
- ✅ Tests lot Q verts

## Tests

```python
# tests/test_composite_rate_limit.py

def test_rate_limit_per_api_key_across_ips():
    """Test that API key rate limit applies across multiple IPs."""
    api_key, key_id = generate_api_key("bot1")

    # Send requests from different IPs
    for i in range(1001):
        ip = f"192.168.1.{i % 255}"
        # ... make request with api_key from ip
        # First 1000 should succeed, 1001st should get 429

def test_rate_limit_ip_still_applies():
    """Test that per-IP limit still works."""
    api_key, key_id = generate_api_key("bot1")
    ip = "192.168.1.100"

    # Send 31 requests from same IP in 1 minute
    # Should get 429 on 31st (limit is 30/minute)
```

---

**Status**: Spécification complète, implémentation à intégrer dans bot_public.py
