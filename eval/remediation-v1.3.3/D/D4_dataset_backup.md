# D4 — Sauvegarde dataset.csv

## Fichier source

- Chemin : `dataset.csv` (racine du projet)
- Lignes : 6063 (header + 6062 verbatims)
- Colonnes : text, intent, locale
- SHA-256 : `cbbc1025eee434200d70f6e6ece0f14145a88fe03c4001a2fe1fe6202266ca5b`

## Statut git

Le fichier est dans `.gitignore` (ligne 59) pour éviter de committer des données
client en clair. C'est correct du point de vue sécurité.

## Mesures de sauvegarde

1. Le hash SHA-256 est archivé dans ce fichier de preuve (traçabilité)
2. Les datasets figés (`eval/datasets/`) sont dérivés de dataset.csv via
   `make_datasets.py` avec seed=42 — la régénération est déterministe
3. Le fichier `eval/datasets/HASHES.sha256` garantit l'intégrité des dérivés
4. La CI vérifie les hashes à chaque push (guard-datasets job)

## Recommandation

Le fichier dataset.csv doit être sauvegardé hors du dépôt git (drive partagé,
stockage chiffré). Sa perte empêcherait la régénération des datasets et
l'ajout de nouveaux exemples (M3).
