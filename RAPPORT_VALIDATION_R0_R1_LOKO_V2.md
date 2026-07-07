# Rapport campagne R0+R1 — 2026-07-06 — protocole v2.0

Version : tag `v0.3.6`, commit `dff316161c1438e23f8a93037b723079a9d689df`, image `loko-r0r1-codex:v0.3.6`, digest `sha256:d9a475712c576a52caa8cb07ce7f21cb7c7094fe49c68b25af4ce534940a7ddf`.

Artefacts : `eval/campagne-R0R1/2026-07-06-codex-v2-v036/`

Verdict global : **R0+R1 NON VALIDÉS**.

La campagne a été exécutée entièrement en Docker local après nettoyage des anciens artefacts. Elle reste non opposable dès l’entrée car CE-1 échoue : `git describe --tags --dirty --always` retourne `v0.3.6-dirty` avec 5 suppressions Markdown suivies par Git. Les tests ont néanmoins été exécutés pour fournir un diagnostic complet.

## Conditions d'entrée

| CE | Verdict | Résultat |
|---|---:|---|
| CE-1 | FAIL | Branche `main`, mais worktree dirty : `AMELIORATION_R0_R1_LOKO.md`, `PLAN_CORRECTION_V0_3_4_LOKO.md`, `PLAN_CORRECTION_V0_3_5_LOKO.md`, `PROTOCOLE_VALIDATION_R0_R1_LOKO.md`, `RAPPORT_VALIDATION_R0_R1_LOKO.md` supprimés. |
| CE-2 | PASS | Triple version OK : tag `0.3.6`, `pyproject.toml=0.3.6`, `pip show loko=0.3.6`. |
| CE-3 | PASS | Image inspect : `1 057 940 056` octets, soit ~1009 MiB, seuil 1,6 Go respecté. `docker images` indique 3.69 GB à titre informatif. |
| CE-4 | PASS | Hashes datasets vérifiés. |
| CE-5 | PASS | `tools/make_datasets.py --check eval/datasets` OK. |
| CE-6 | PASS | `loko-eval --help` présent avec `--sweep` et `--sweep-datasets` 3 axes. |
| CE-7 | PASS | Répertoire artefacts créé. |
| CE-8 | PASS | Ping LLM DeepSeek réel OK après normalisation locale de la clé `.env`; aucun secret archivé. |

## Tableau de synthèse

| ID | Verdict | Fait mesuré | Artefact |
|---|---:|---|---|
| V0-1 | PASS | `393 passed, 1 skipped` en conteneur. | `V0-1_pytest.txt` |
| V0-2 | PASS | `setfit=1.1.3`, `sentence-transformers=3.3.1`, `torch=2.12.1+cpu`, CUDA `False`. | `V0-2_imports.txt` |
| V0-3 | PASS | Scan AST runtime : aucun import/définition mock hors `loko/testing`; exception escalade détectée. | `V0-3_grep.txt` |
| V0-4 | PASS | `npm audit --audit-level=high` : 0 vulnérabilité. | `V0-4_audit.txt` |
| V0-5 | PASS | Taille inspect ~1009 MiB ≤ 1,6 Go. | `V0-5_image_size.txt` |
| V1-1 | PASS | 4 `RuntimeError` hors `RAGKIT_ENV=test`; escalade mock autorisée seulement avec `LOKO_ESCALATION_PROVIDER=mock`. | `V1-1_mock_guard.txt` |
| V1-2 | PASS | Modèle absent, factice, corrompu : `ComponentUnavailableError`, jamais d'instance. | `V1-2_loader.txt` |
| V1-3 | PASS | `422 manifest_missing`, `422 hash_mismatch`, `422 retrain_required`, puis restauration OK. | `V1-3_publish.http.json` |
| V1-4 | FAIL | Session témoin `201`, puis modèle supprimé : `503 bot_unavailable`, 0 nouvelle session, aucun `hors_perimetre`; mais pas de log `CRITICAL` au boot, seulement erreur d'indisponibilité à la requête. | `V1-4_failfast.json` |
| V1-5 | PASS | Conteneur `--network none`, entraînement et 3 inférences OK. | `V1-5_offline.txt` |
| V2-1 | PASS | Entraînement MGEN complet en `222.218 s` ≤ 300 s; profil et manifeste présents. | `V2-1_train_run.txt`, `V2-1_manifest.json` |
| V2-2 | PASS | `level2_services_en_ligne` présent avec les 5 labels attendus. | `V2-1_manifest_summary.json` |
| V2-3 | PASS | Kill pendant `l1_training` : statut `failed/interrupted`, pas de manifeste partiel, retrain suivant `completed`. | `V2-3_atomicity.json` |
| V2-4 | PASS | Matrice 9x9 exportée, `cv_method=base_model_frozen`, 3 conseils détectés. Première paire : `arret_travail` / `hors_perimetre`. | `V2-4_confusion.csv`, `V2-4_advice.json` |
| V2-5 | FAIL | 6 exemples ajoutés, retrain `268.552 s`, hash dataset modifié, mais signal de paire inchangé : 8 confusions croisées avant et après; advice sur la paire inchangé `2 -> 2`. | `V2-5_comparison.json` |
| V2-6 | PASS | Manifeste P95 `28.54 ms`; contre-mesure indépendante alignée P95 `27.20 ms`; écart `4.7 %`. | `V2-6_latency.json` |
| V3-0 | FAIL | Sweep 240 points : aucun point ne satisfait GNG-1/GNG-2/GNG-3 + routes directes ≤ 5. Point le plus proche figé : haut `0.90`, bas `0.30`, écart `0.05`. | `sweep/sweep_3axis.json`, `V3-0_selection.json` |
| V3-1 | FAIL | GNG-1 : `72/100 = 72.0 %`, seuil 85 %. 28 erreurs classées. | `V3-1_metier/report.json`, `V3-1_errors_classified.csv` |
| V3-2 | FAIL | GNG-2 : `103/125 = 82.4 %`, seuil 90 %. | `V3-2_conseiller/report.json` |
| V3-3 | FAIL | GNG-3 : `72/100 = 72.0 %`, seuil 80 %. Routes directes métier : `2/100`, sous-seuil ≤ 5 respecté. | `V3-3_horsscope/report.json` |
| V3-4 | FAIL | Pièges : `6/15`, seuil 12/15. Les 9 écarts sont commentés individuellement. | `V3-4_pieges/report.json`, `V3-4_pieges_comments.csv` |
| V3-5 | N/A | Supprimé par protocole v2.0. | N/A |
| V3-6 | PASS | Deux runs V3-1 avec restart Docker entre les deux : `report.json` strictement identiques. | `V3-6_summary.json`, `V3-6_report_diff.txt` |
| V3-7 | NON ENGAGÉ | Boucle corrective requise par l'échec G-3, mais non exécutée dans cette campagne de validation déjà invalidée par CE-1, V1-4 et V2-5. | `V3_summary.json` |

## Calibration V3-0

La grille V3-0 contient 240 points. Aucun point ne respecte simultanément :

- GNG-1 ≥ 85 %
- GNG-2 ≥ 90 %
- GNG-3 ≥ 80 %
- routes directes hors-scope ≤ 5/100

Le point retenu par distance minimale aux seuils est :

| seuil_haut | seuil_bas | seuil_ecart | GNG-1 | GNG-2 | GNG-3 | routes directes | pièges |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.90 | 0.30 | 0.05 | 72.0 % | 82.4 % | 72.0 % | 2/100 | 6/15 |

Ces seuils ont été figés dans la config du bot : `V3-0_freeze_config.json`.

## Chiffres GNG

Aux seuils figés :

- GNG-1 : `72.0 %` versus seuil `85 %`.
- GNG-2 : `82.4 %` versus seuil `90 %`.
- GNG-3 : `72.0 %` versus seuil `80 %`, avec `2/100` routes directes métier versus seuil ≤ 5.
- Pièges : `6/15` versus seuil `12/15`; `9/9` écarts commentés.

## Itérations V3-7

| Itération | Action | GNG-1 | GNG-2 | GNG-3 routes directes | Pièges |
|---|---|---:|---:|---:|---:|
| 0 | Calibration obligatoire V3-0, aucun point conforme; point le plus proche figé. | 72.0 % | 82.4 % | 72.0 %, 2/100 | 6/15 |

Aucune itération corrective d'exemples n'a été engagée dans cette campagne. Le rapport constate donc que V3-7 serait nécessaire avant toute tentative de validation G-3, mais que la campagne est déjà non validée par d'autres gates.

## Anomalies

Anomalies produit ou validation :

- CE-1 bloquant : worktree dirty (`v0.3.6-dirty`) à cause de suppressions Markdown suivies par Git.
- V1-4 : fail-fast runtime fonctionnel, mais absence de log `CRITICAL` au boot après suppression du modèle.
- V2-5 : l'amélioration demandée sur la paire détectée ne réduit pas le signal mesuré.
- V3-0 à V3-4 : calibration incapable d'atteindre les seuils GNG; les scores restent nettement sous les seuils.

Anomalies de protocole suspectées :

- V0-4 a été exécuté dans un conteneur Node dédié, car l'image runtime finale ne contient pas `npm`. Le protocole exige l'exécution in-container, ce qui est respecté, mais ne précise pas si `npm audit` doit vivre dans l'image runtime finale.
- Les rapports `loko-eval` standards n'embarquent pas directement le hash dataset et la référence manifeste; ces éléments sont consignés en sidecar dans `V3_summary.json`.

## Gates

| Gate | Verdict | Motif |
|---|---:|---|
| Conditions d'entrée | FAIL | CE-1 dirty worktree. |
| G-0 | PASS | V0-1 à V0-5 PASS. |
| G-1 éliminatoire | FAIL | V1-4 échoue sur le log `CRITICAL` au boot. |
| G-1b | PASS | V1-5 offline PASS. |
| G-2 | FAIL | V2-5 ne démontre aucune réduction du signal de paire. |
| G-3 | FAIL | GNG-1, GNG-2, GNG-3 et pièges sous seuils, malgré V3-6 PASS. |

## Verdict

**R0+R1 NON VALIDÉS.**

Les phases R2-R9 ne doivent pas être ouvertes sur la base de cette campagne comme validation R0+R1. Les travaux de développement parallèles restent possibles dans les limites du protocole, mais la recette dépendante de la qualité de routage reste bloquée.
