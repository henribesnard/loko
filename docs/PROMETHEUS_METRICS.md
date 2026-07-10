# O1: Prometheus Metrics

**Reference**: PLAN_AMELIORATION_COMPLET_LOKO_2026-07-10.md

## Métriques exposées

### Messages & Conversations

```promql
# Total messages par bot et statut
loko_messages_total{bot_id="bot1", status="success"}
loko_messages_total{bot_id="bot1", status="error"}
loko_messages_total{bot_id="bot1", status="rate_limited"}

# Escalations vers conseillers
loko_escalations_total{bot_id="bot1", reason="hors_perimetre"}
loko_escalations_total{bot_id="bot1", reason="demande_conseiller"}
```

### Classification

```promql
# Classifications par niveau et décision
loko_classifications_total{bot_id="bot1", level="l1", decision="route"}
loko_classifications_total{bot_id="bot1", level="l1", decision="clarify"}
loko_classifications_total{bot_id="bot1", level="l2", decision="reject"}

# Confiance de classification (histogram)
loko_classification_confidence_bucket{bot_id="bot1", level="l1", le="0.7"}
loko_classification_confidence_sum{bot_id="bot1", level="l1"}
loko_classification_confidence_count{bot_id="bot1", level="l1"}
```

### Latence

```promql
# Latence par étape (histogram)
loko_step_latency_seconds_bucket{step="classification_l1", le="0.1"}
loko_step_latency_seconds_bucket{step="retrieval", le="0.5"}
loko_step_latency_seconds_bucket{step="generation", le="2.0"}

# Latence totale par bot
loko_message_latency_seconds_bucket{bot_id="bot1", le="5.0"}
```

### Système

```promql
# Modèles chargés en mémoire
loko_models_loaded{bot_id="bot1", level="l1"}
loko_models_loaded{bot_id="bot1", level="l2"}

# Sessions actives
loko_sessions_active{bot_id="bot1"}
```

### Erreurs

```promql
# Erreurs par type
loko_errors_total{error_type="classification_error", bot_id="bot1"}
loko_errors_total{error_type="retrieval_error", bot_id="bot1"}
loko_errors_total{error_type="generation_error", bot_id="bot1"}
```

### Authentification

```promql
# Tentatives d'authentification
loko_auth_attempts_total{result="success"}
loko_auth_attempts_total{result="failed"}
loko_auth_attempts_total{result="rate_limited"}
```

## Configuration Prometheus

### prometheus.yml

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'loko'
    static_configs:
      - targets: ['loko:8000']
    metrics_path: '/metrics'
    scheme: 'http'
    # Important: Ajouter admin token
    authorization:
      type: Bearer
      credentials: '${LOKO_ADMIN_TOKEN}'
```

### docker-compose.yml (add Prometheus)

```yaml
services:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus-data:/prometheus
    ports:
      - "9090:9090"
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.retention.time=30d'

volumes:
  prometheus-data:
```

## Requêtes utiles

### Taux de messages par seconde

```promql
rate(loko_messages_total[5m])
```

### Taux d'escalation

```promql
sum(rate(loko_escalations_total[5m])) by (reason)
```

### P95 latence de génération

```promql
histogram_quantile(0.95, rate(loko_step_latency_seconds_bucket{step="generation"}[5m]))
```

### Taux d'erreur

```promql
rate(loko_errors_total[5m])
```

### Confidence moyenne L1

```promql
rate(loko_classification_confidence_sum{level="l1"}[5m]) /
rate(loko_classification_confidence_count{level="l1"}[5m])
```

## Dashboards Grafana

### Dashboard ID: loko-overview

```json
{
  "dashboard": {
    "title": "LOKO Overview",
    "panels": [
      {
        "title": "Messages/sec",
        "targets": [{
          "expr": "rate(loko_messages_total[5m])"
        }]
      },
      {
        "title": "P95 Latency",
        "targets": [{
          "expr": "histogram_quantile(0.95, rate(loko_message_latency_seconds_bucket[5m]))"
        }]
      },
      {
        "title": "Error Rate",
        "targets": [{
          "expr": "rate(loko_errors_total[5m])"
        }]
      }
    ]
  }
}
```

## Sécurité

### ✅ Endpoint /metrics

- **Protected**: Admin token required
- **Never public**: Not exposed via Caddy
- **Internal only**: Docker network or authenticated admin
- **Tested in R7**: Security audit (E6)

### ❌ Cardinalité

- **bot_id**: Limité au nombre de bots (OK)
- **step**: Fixe (4-5 valeurs)
- **error_type**: Énumération fixe
- **NEVER**: session_id, user_id, message content

## Intégration dans le code

### Exemple: bot_public.py

```python
from loko.monitoring.metrics import (
    record_message,
    record_classification,
    record_step_latency,
    record_error
)
import time

@router.post("/api/v1/bot/{bot_id}/message")
async def send_message(bot_id: str, ...):
    start = time.time()

    try:
        # ... classification L1
        classify_start = time.time()
        result_l1 = classifier.classify(text)
        record_step_latency("classification_l1", time.time() - classify_start)

        record_classification(
            bot_id=bot_id,
            level="l1",
            decision=result_l1.decision,  # 'route', 'clarify', 'reject'
            confidence=result_l1.confidence
        )

        # ... rest of processing

        # Success
        record_message(bot_id, status="success")
        record_message_latency(bot_id, time.time() - start)

    except Exception as e:
        record_error("generation_error", bot_id)
        record_message(bot_id, status="error")
        raise
```

### Exemple: user_auth.py

```python
from loko.monitoring.metrics import record_auth_attempt

@router.post("/api/auth/login")
async def login(...):
    try:
        user = authenticate(...)
        record_auth_attempt("success")
        return {"token": ...}
    except RateLimitError:
        record_auth_attempt("rate_limited")
        raise
    except AuthError:
        record_auth_attempt("failed")
        raise
```

## Tests

```bash
# Démarrer Prometheus
docker compose up -d prometheus

# Vérifier endpoint /metrics
curl -H "Authorization: Bearer $LOKO_ADMIN_TOKEN" http://localhost:8000/metrics

# Vérifier Prometheus UI
open http://localhost:9090

# Query de test
rate(loko_messages_total[5m])
```

## Critères d'acceptation (O1)

- ✅ `/metrics` sert les métriques in-container
- ✅ Scrape Prometheus fonctionnel
- ✅ `/metrics` inaccessible depuis l'extérieur (R7)
- ✅ Cardinalité bornée (pas de label à valeur libre)

---

**Status**: Module complet, intégration à faire dans bot_public.py/user_auth.py
