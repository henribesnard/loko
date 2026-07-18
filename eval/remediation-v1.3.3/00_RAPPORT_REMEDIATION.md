# Rapport de remediation post-campagne v1.3.3

**Version cible** : v1.3.4
**Date** : 2026-07-18
**Mission** : E2b — remediation inter-campagne
**Operateur** : Claude Code (Opus 4.6)

---

## Resume executif

17 corrections appliquees en 17 commits atomiques, couvrant 4 lots :
outillage (T), produit (P), donnees (D), modele (M).

Les 7 tests V0-1 en echec sont tous corriges (7/7 PASS).
Le re-figeage v2 elimine les 73 occurrences de "mutuelle" dans les datasets.
Le sweep est contraint (ECART_MIN, penalite hors-scope).
Le budget d'entrainement est reduit (num_iterations 5->3, batch_size 16->32).

**Statut** : pret pour revue humaine + tag v1.3.4.

---

## LOT T — Outillage (4 corrections)

| ID | Titre | Commit | Statut |
|----|-------|--------|--------|
| T1 | check_version_sync.py + CI job version-sync | `130258e` | DONE |
| T2 | Runner arret sur CE FAIL (--diagnostic) | `ead1583` | DONE |
| T3 | Scrub labels pre-scrub dans tools/ | `6b3b7d2` | DONE |
| T4 | CI guard-datasets + make_datasets --check | `d0b9705` | DONE |

**T1** : Nouveau script `tools/check_version_sync.py` verifie la coherence pyproject.toml / importlib / OpenAPI / git tag. Job CI `version-sync` ajoute (tags only).

**T2** : Le runner s'arrete apres la phase CE si CE FAIL (exit code 2). Mode `--diagnostic` disponible pour continuer en mode non-opposable.

**T3** : Renomme `SERVICES_EN_LIGNE_SUB_MOTIFS` -> `HELP_ACCOUNT_SUB_MOTIFS`, mise a jour de `REQUIRED_MODEL_LABELS` dans audit_label_mapping.py.

**T4** : Job CI guard-datasets execute `make_datasets.py --check` (presence fichiers, comptages, hashes, intersections, syntaxe pieges).

---

## LOT P — Produit (4 corrections, 7 tests fixes)

| ID | Titre | Tests fixes | Commit | Statut |
|----|-------|-------------|--------|--------|
| P1 | Validation min exemples | 3 | `35e0f10` | DONE |
| P2 | Asyncio Python 3.12 | 2 | `07e8a5d` | DONE |
| P3 | Migration schema v4 | 1 | `282e49a` | DONE |
| P4 | Auth email verification | 1 | `0ac8caf` | DONE |

**P1** : Ajout de validateurs Pydantic : Intent >= 8 exemples (model_validator, bypass is_system), SubMotif >= 3 exemples (field_validator).

**P2** : Remplacement `asyncio.get_event_loop().run_until_complete()` par `asyncio.run()` dans test_no_token_in_logs.py.

**P3** : Test migration attendait schema_version=2, code evolue a v4 (knowledge_sources). Test mis a jour.

**P4** : Re-activation du controle ACC-4 : login bloque si `email_verified_at IS NULL` (etait commente "disabled until SMTP configured").

---

## LOT D — Donnees (4 corrections)

| ID | Titre | Commit | Statut |
|----|-------|--------|--------|
| D1 | diff_refigeage.py — preuve v1 | `a47429a` | DONE |
| D2 | Re-figeage v2 (Santelis, B1 approuve) | `90524f4` | DONE |
| D3 | Preuve v2 + revue 15 pieges | `686e1bf` | DONE |
| D4 | Sauvegarde dataset.csv (SHA-256) | `bcbd3d8` | DONE |

**D1** : Script `tools/diff_refigeage.py` montre 33 modifications scrub et 73 lignes avec "mutuelle" (v1).

**D2** : Marque fictive **Santelis** (B1 approuve). `scrub_client()` remplace desormais le brand client ET "mutuelle" par "Santelis". Tous les POSTULAT_EXAMPLES, PIEGE_CASES et definitions d'intent mis a jour. Datasets regeneres, 0 occurrences de "mutuelle".

**D3** : 15/15 pieges valides apres re-figeage. Comportements attendus inchanges.

**D4** : Hash SHA-256 de dataset.csv archive. Fichier reste dans .gitignore (donnees client). Recommandation de sauvegarde hors depot.

---

## LOT M — Modele (5 corrections)

| ID | Titre | Commit | Statut |
|----|-------|--------|--------|
| M1 | Calibration (temperature scaling) | `6ab769f` | DONE |
| M2 | Sweep contraint | `6b1ec3f` | DONE |
| M3 | Enrichissement help_documents (+20 ex.) | `f5b8a59` | DONE |
| M4 | Budget entrainement (3 iter, batch 32) | `c2e0f4b` | DONE |
| M5 | Latence P95 (eval mode + no_grad) | `9c39913` | DONE |

**M1** : Module `loko/bot/classifier/calibration.py` avec `apply_temperature_scaling()` et `find_optimal_temperature()` (minimisation ECE). Integre dans `SetFitClassifierAdapter.classify_l1()`.

**M2** : Contrainte `ECART_MIN=0.05` dans `select_best_thresholds_pareto()`. 4eme critere lexicographique : penalite sur routes directes hors-scope.

**M3** : +20 exemples help_documents cibles (cartes, certificats, justificatifs). train.csv : 125 -> 145 lignes.

**M4** : `num_iterations` 5->3, `batch_size` 16->32 dans TrainingParams. Cible V2-1 < 300s.

**M5** : `model_body.eval()` au chargement, `torch.no_grad()` a l'inference. Reduction latence P95 sans impact qualite.

---

## Points d'arret B

| ID | Question | Decision |
|----|----------|----------|
| B1 | Marque fictive pour re-figeage v2 | **Santelis** (utilisateur) |
| B2 | Budget revisions (M4) | Applique : 3 iter, batch 32 |
| B3 | Pieges attendus | 15/15 valides post-Santelis |

---

## Version bump

- `pyproject.toml` : 1.3.2 -> 1.3.4
- Tag `v1.3.4` : **NON POSE** (attente revue humaine)

---

## Prochaines etapes

1. Revue humaine des 17 commits
2. Tag v1.3.4 si approuve
3. Lancer campagne v1.3.4 (script `tools/run_mission2_poste.ps1` avec `$TAG="v1.3.4"`)
4. Verifier : 7 tests V0-1 PASS, CE PASS, G-2 train < 300s, GNG-2 > 90%
