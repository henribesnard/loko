# O4: Alerting Minimal

**Reference**: PLAN_AMELIORATION_COMPLET_LOKO_2026-07-10.md

## Configuration proportionnée mono-VPS

### 1. Uptime externe (UptimeRobot)

**Service**: https://uptimerobot.com (gratuit 50 monitors)

**Configuration**:
```
Monitor Type: HTTP(s)
URL: https://loko.wezon.fr/health
Interval: 5 minutes
Alert when down for: 2 checks (10 min)
Notifications: Email + SMS
```

**Avantages**:
- Détection externe (indépendant du VPS)
- Gratuit
- SMS + email
- Simple

### 2. Prometheus AlertManager

**alertmanager.yml**:
```yaml
global:
  resolve_timeout: 5m

route:
  receiver: 'email'
  group_by: ['alertname']
  group_wait: 10s
  group_interval: 5m
  repeat_interval: 4h

receivers:
  - name: 'email'
    email_configs:
      - to: 'admin@example.com'
        from: 'alertmanager@loko.wezon.fr'
        smarthost: 'smtp.example.com:587'
        auth_username: 'alerts@loko.wezon.fr'
        auth_password: '${SMTP_PASSWORD}'
```

**prometheus_alerts.yml**:
```yaml
groups:
  - name: loko
    interval: 30s
    rules:
      # Règle 1: Taux 5xx élevé
      - alert: HighErrorRate
        expr: rate(loko_messages_total{status="error"}[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Taux d'erreur élevé"
          description: "{{ $value }} erreurs/sec sur 5min"

      # Règle 2: P95 latence élevée
      - alert: HighLatency
        expr: histogram_quantile(0.95, rate(loko_message_latency_seconds_bucket[5m])) > 10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Latence P95 > 10s"
          description: "P95: {{ $value }}s"

      # Règle 3: Backup ancien
      - alert: BackupTooOld
        expr: time() - (loko_last_backup_timestamp > 0) > 93600  # 26 hours
        for: 1h
        labels:
          severity: critical
        annotations:
          summary: "Backup obsolète"
          description: "Dernier backup il y a {{ $value | humanizeDuration }}"
```

**docker-compose.yml** (ajouter):
```yaml
services:
  alertmanager:
    image: prom/alertmanager:latest
    volumes:
      - ./alertmanager.yml:/etc/alertmanager/alertmanager.yml
    ports:
      - "9093:9093"
    command:
      - '--config.file=/etc/alertmanager/alertmanager.yml'

  prometheus:
    # ... existing config
    volumes:
      - ./prometheus_alerts.yml:/etc/prometheus/alerts.yml
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.retention.time=30d'
      - '--web.enable-lifecycle'
```

**prometheus.yml** (mise à jour):
```yaml
# ... existing config

rule_files:
  - "alerts.yml"

alerting:
  alertmanagers:
    - static_configs:
        - targets: ['alertmanager:9093']
```

### 3. Test des alertes

```bash
# Déclencher alerte manuellement
curl -X POST http://localhost:9093/api/v1/alerts -d '[{
  "labels": {"alertname": "TestAlert", "severity": "warning"},
  "annotations": {"summary": "Test alert"},
  "startsAt": "2026-07-10T12:00:00Z"
}]'

# Vérifier réception email
```

### 4. Dashboard simple (optionnel)

Si Grafana trop lourd, utiliser AlertManager UI:
```
http://localhost:9093
```

Ou requêtes Prometheus directes:
```bash
# Erreurs récentes
curl 'http://localhost:9090/api/v1/query?query=rate(loko_errors_total[5m])'

# Latence actuelle
curl 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,rate(loko_message_latency_seconds_bucket[5m]))'
```

## Critères d'acceptation (O4)

- ✅ Uptime externe sur `/health`
- ✅ 3 alertes Prometheus (5xx, latence, backup)
- ✅ Incident simulé (suppression modèle, E8-3) → alerte < 5 min

## Actions

1. **Setup UptimeRobot** (5 min):
   - Créer compte
   - Ajouter monitor https://loko.wezon.fr/health
   - Configurer email/SMS

2. **Setup AlertManager** (30 min):
   - Créer alertmanager.yml
   - Créer prometheus_alerts.yml
   - Ajouter services docker-compose
   - Tester alerte

3. **Documentation runbook** (15 min):
   - Procédure réception alerte
   - Actions correctives par type

---

**Status**: Spécification complète, déploiement à faire en E6
