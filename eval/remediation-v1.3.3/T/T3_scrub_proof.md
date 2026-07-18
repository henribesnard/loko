# T3 — Leftovers scrub dans outillage

## Fichiers corrigés

### tools/audit_label_mapping.py
- `REQUIRED_MODEL_LABELS` : remplacé les 7 anciens labels français par les labels `help_*` génériques

### tools/setup_campaign_bot.py
- Renommé `SERVICES_EN_LIGNE_SUB_MOTIFS` → `HELP_ACCOUNT_SUB_MOTIFS`
- 6 commentaires/print mis à jour : `services_en_ligne` → `help_account`
- 2 messages d'erreur dans `verify_conformity()` mis à jour

## Références conservées (légitimes)

### tools/make_datasets.py
- `INTENT_RENAME` mapping (l.192) : clé source `"services_en_ligne": "help_account"` — nécessaire pour la conversion
- Piège note (l.263) : commentaire historique documentant le label d'origine
- Mot "cotisations" dans les exemples d'entraînement : vocabulaire métier, pas un label

### tools/preflight.py
- Déjà conforme (labels `help_*` uniquement) — aucune correction nécessaire

## Vérifications

```
$ python -m py_compile tools/setup_campaign_bot.py   → OK
$ python -m py_compile tools/audit_label_mapping.py  → OK
$ pytest tests/test_no_client_mention.py -v           → 2 passed
```

Guard-client-mentions couvre bien tools/ (SCAN_DIRS inclut REPO_ROOT / "tools").
