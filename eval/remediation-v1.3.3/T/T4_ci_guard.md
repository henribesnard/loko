# T4 — Garde CI sur eval/datasets (C5)

## Modification

### .github/workflows/ci.yml — job guard-datasets
1. Ajout d'un step `Set up Python` (actions/setup-python@v5) pour pouvoir exécuter make_datasets.py
2. Ajout d'un step `Deep dataset validation (C5)` qui exécute :
   ```
   python tools/make_datasets.py --check eval/datasets/
   ```

Ce step valide :
- (a) Présence des 5 fichiers + HASHES.sha256
- (b) Comptages de lignes exacts (train=125, heldout_metier=100, etc.)
- (c) Vérification des hashes SHA-256
- (d) Absence d'intersection entre train/heldout/pièges (case-folded, accent-normalized)
- (e) Syntaxe expected_behavior dans pieges.csv
- (e bis) IDs pièges T01-T15

Le step existant `sha256sum -c HASHES.sha256` est conservé comme filet de sécurité bas niveau.

## Preuve locale

```
$ python tools/make_datasets.py --check eval/datasets/
OK - all checks passed for eval\datasets
```
