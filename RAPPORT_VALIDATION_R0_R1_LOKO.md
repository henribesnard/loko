# Rapport validation R0+R1 LOKO - campagne propre 2026-07-05 v0.3.4

## Verdict

**R0+R1 NON VALIDES.**

La reprise a bien validé les corrections majeures R0 : garde anti-mock, erreurs de publication `422` codées, provider LLM réel configuré, fail-fast runtime après suppression du modèle. En revanche la campagne ne peut pas ouvrir R2-R9, car plusieurs critères R1 et GNG restent en échec :

- CE-1 bloquant : worktree non clean au preflight (`RAPPORT_VALIDATION_R0_R1_LOKO.md` déjà modifié, `PLAN_CORRECTION_V0_3_4_LOKO.md` non suivi).
- V0-5 : image `docker images` = `3.69GB`, au-dessus de la cible `<= 1.6GB`.
- V2-1 : entraînement MGEN terminé mais très au-delà du seuil `< 2 min` : `1783.0s` bout en bout, L1 `764.33s`.
- V2-3 : pas de manifeste partiel après interruption et le retrain repart, mais le statut après redémarrage revient à `idle` au lieu de `failed` explicite.
- V2-4/V2-5 : matrice et endpoint existent, mais la confusion attendue `cotisations` <-> `changement_coordonnees` est `0` avant/après ; aucun conseil actionnable n'est produit.
- V2-6 : le manifeste post V2-5 annonce `P95=63.76ms`, au-dessus du seuil `50ms`.
- V3 : GNG-1 `73%`, GNG-2 `84.8%`, pièges `1/15` par le CLI (`7/15` en lecture sémantique manuelle), donc seuils non atteints. `loko-eval` plante aussi à l'écriture de `errors.csv` dès qu'il y a des erreurs.

## Périmètre

- Protocole appliqué : `PROTOCOLE_VALIDATION_R0_R1_LOKO.md`
- Mode : Docker local
- Dossier d'artefacts : `eval/campagne-R0R1/2026-07-05-codex-clean/`
- Tag demandé : `v0.3.4`
- Commit : `892032a8630b2f93c459cf417627d33c22e8df12`
- Image : `loko-r0r1-codex:v0.3.4`
- Image id/digest local : `sha256:8aefddc5799934a58981b0d6c6f5ed1e346c8032c46324d7e35f5da2e3b8bb9b`
- Taille inspect : `1,057,862,424 bytes`; taille `docker images` : `3.69GB`
- Provider LLM : `openai_compat`, modèle `deepseek-chat`, ping 1 token OK (`preview: OK`)
- Données sensibles : `.env` non copiée ; seules les clés de variables et l'environnement filtré ont été archivés. La clé API runtime générée pour V1-4 n'est pas stockée.
- Nettoyage : conteneurs et volumes temporaires supprimés en fin de campagne ; image Docker conservée.

## Conditions D'Entree

| ID | Verdict | Résultat objectif | Artefact |
|---|---:|---|---|
| CE-1 | FAIL | Preflight `6/7 BLOCKED` : branche `main`, mais worktree non clean, `untracked=1`. | `CE_preflight_with_args.txt` |
| CE-2 | PASS avec réserve | Tag `v0.3.4` présent, mais `git describe` global reste `v0.3.4-dirty` à cause des fichiers de rapport/plan. | `CE-2_git_describe.txt`, `commit.txt` |
| CE-3 | PASS | Image reconstruite depuis le code courant, id `8aefddc...`. | `CE-3_docker_build.txt`, `CE-3_image_inspect.txt` |
| CE-4 | PASS | Datasets présents et conformes : `train=125`, `heldout_metier=100`, `heldout_conseiller=125`, `heldout_horsscope=100`, `pieges=15`. | `CE-4_dataset_counts.txt`, `CE-4_hashes_sha256.txt` |
| CE-5 | PASS | `tools/make_datasets.py --check eval/datasets` retourne OK. | `CE-5_dataset_check.txt` |
| CE-6 | PASS | `loko-eval --help` fonctionne dans l'image. | `CE-6_loko_eval_help.txt` |
| CE-7 | PASS | Répertoire de campagne propre créé. | dossier campagne |
| CE-8 | PASS informatif | Ping LLM réel via `.env` mappé en `LOKO_LLM_*` : 1 token, `OK`, `1.501s`. | `CE-8_llm_ping.txt` |

## Environnement

- Python conteneur : `3.12.13`
- ML : `setfit==1.1.3`, `sentence-transformers==3.3.1`, `transformers==4.46.3`, `tokenizers==0.20.3`, `torch==2.12.1+cpu`, `httpx==0.28.1`
- Offline ML : `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `LOKO_BASE_MODEL_PATH=/app/models/base/minilm`
- Runtime : `RAGKIT_MODE=server`, `LOKO_DATA_DIR=/data`, `LOKO_ESCALATION_PROVIDER=mock`, `LOKO_LLM_PROVIDER=openai_compat`

Artefacts : `campaign_python_version.txt`, `campaign_pip_freeze_ml.txt`, `campaign_env_effective.txt`.

## Tableau De Synthese

| ID | Verdict | Résultat objectif | Artefact |
|---|---:|---|---|
| V0-1 | PASS | Suite complète in-container : `335 passed, 1 skipped`, aucun filtre de marqueur appliqué. | `V0-1_pytest.txt` |
| V0-2 | PASS | Imports ML OK, `torch 2.12.1+cpu`, CUDA `False`. | `V0-2_imports.txt` |
| V0-3 | PASS avec réserve | Tests anti-mock : `11 passed`. Grep statique trouve l'import `MockEscalationProvider` dans `bot_public.py`, mais uniquement sous `LOKO_ESCALATION_PROVIDER=mock`, exception admise par la règle 0. | `V0-3_anti_mock_pytest.txt`, `V0-3_static_anti_mock_grep.txt` |
| V0-4 | PASS | `npm audit --audit-level=high` : `found 0 vulnerabilities`. | `V0-4_audit.txt` |
| V0-5 | FAIL | `docker images` mesure `3.69GB`, cible `<= 1.6GB`. | `V0-5_image_size.txt` |
| V1-1 | PASS | Les 4 mocks lèvent `RuntimeError` hors test ; `LOKO_ESCALATION_PROVIDER=mock` n'autorise que `MockEscalationProvider`. | `V1-1_mock_guard.txt` |
| V1-2 | PASS | `load_classifier` échoue fermé en `ComponentUnavailableError` sur répertoire vide, config factice et config corrompue. | `V1-2_loader.txt` |
| V1-3 | PASS | Les trois contournements publication renvoient `422`: `manifest_missing`, `hash_mismatch`, `retrain_required`. | `V1-3_publish_integrity.http.json`, `V1-3_publish_integrity.txt` |
| V1-4 | PASS | Session témoin créée (`201`). Après suppression `models/level1` + restart : `POST /sessions` et `POST /messages` renvoient `503 bot_unavailable`, compteur sessions inchangé `1 -> 1`, aucun `hors_perimetre` généré. | `V1-4_failfast.json`, `V1-4_failfast.txt` |
| V1-5 | PASS | Conteneur `--network none`, train 2 intentions x 8, manifeste écrit, 3 inférences OK, variables offline présentes. | `V1-5_offline.txt` |
| V2-1 | FAIL | Train MGEN complet terminé, mais durée totale `1783.0s`; L1 `764.33s`, L2 `114.01s`, évaluation `747.51s`. Seuil attendu `< 120s`. | `V2-1_train_run.txt`, `V2-1_train_report.json`, `V2-1_manifest.json` |
| V2-2 | PASS | Manifeste avec `level2_services_en_ligne`, labels exacts : `compte_bloque`, `identifiants_perdus`, `mot_de_passe_oublie`, `premiere_connexion`, `probleme_technique`. | `V2-1_manifest.json`, `V2-5_manifest_after.json` |
| V2-3 | FAIL partiel | Interruption pendant `l1_training` : pas de manifeste partiel, retrain suivant terminé. Echec : statut après restart = `idle`, pas `failed` explicite. | `V2-3_atomicity.json`, `V2-3_atomicity.txt` |
| V2-4 | FAIL | Endpoint rapport et matrice 9x9 OK, accuracy CV `1.0`; mais confusion attendue `cotisations` <-> `changement_coordonnees` = `0`, conseil `[]`. | `V2-4_confusion.csv`, `V2-4_advice.json` |
| V2-5 | FAIL | 6 exemples ajoutés, hash dataset changé. Confusion paire avant `0`, après `0`, donc aucune réduction mesurable. Retrain encore très lent : `1483.5s`. | `V2-5_comparison.json`, `V2-5_matrices_avant_apres.csv` |
| V2-6 | FAIL | Manifeste post V2-5 : `P50=29.21ms`, `P95=63.76ms`. Contre-mesure 100 held-out : `P50=26.34ms`, `P95=34.59ms`. Le P95 manifeste dépasse `50ms` et l'écart P95 dépasse `30%`. | `V2-6_latency_independent.txt`, `V2-5_train_run.txt` |
| V3-1 | FAIL | GNG-1 métier : `73/100 = 73%`, seuil `85%`. Le CLI sort `1` et plante à l'écriture `errors.csv`. | `V3_eval_out/metier/report.json`, `V3_error_analysis.json` |
| V3-2 | FAIL | GNG-2 conseiller : `106/125 = 84.8%`, seuil `90%`. | `V3_eval_out/conseiller/report.json`, `V3_error_analysis.json` |
| V3-3 | FAIL avec métrique seuil OK | Hors-scope : `81/100 = 81%`, seuil global atteint, mais CLI sort `1` par bug `errors.csv` et 9 erreurs sont des routes métier directes hors-scope. | `V3_eval_out/horsscope/report.json`, `V3_error_analysis.json` |
| V3-4 | FAIL | CLI : `1/15 = 6.67%`. Lecture sémantique des décisions : environ `7/15`, toujours sous le seuil `12/15`. | `V3_eval_out/pieges/report.json`, `V3-4_pieges_decisions.json` |
| V3-5 | NON APPLICABLE | Calibration non tentée : les échecs ne sont pas marginaux (`GNG-1=73%`, pièges très bas) et le CLI d'évaluation est instable. | - |
| V3-6 | FAIL strict | Deux runs V3-1 après restart : accuracy identique `0.73`. Diff brut non vide (`duration_s` change), diff sans `duration_s` vide. Le protocole ne prévoit d'ignorer que l'horodatage. | `V3-6_repro_summary.txt`, `V3-6_repro/` |

## Chiffres GNG

| Critère | Résultat | Seuil | Verdict | Commentaire |
|---|---:|---:|---:|---|
| GNG-1 métier | `73%` | `85%` | FAIL | 27 erreurs : 17 faux rejets, 4 escalades indues, 3 mauvaises routes, 3 clarifications non pertinentes. |
| GNG-2 conseiller | `84.8%` | `90%` | FAIL | 19 erreurs : 16 rejets au lieu d'escalade, 2 clarifications, 1 route. |
| GNG-3 hors-scope | `81%` | `80%` | FAIL technique | Seuil métrique atteint, mais sortie CLI en erreur et 9 routes métier directes hors-scope. |
| Pièges | `1/15` CLI, `~7/15` sémantique | `12/15` | FAIL | Le CLI compare `decision.type` à la chaîne complète `route:intent`, ce qui sous-compte les routes correctes ; même corrigé, le seuil n'est pas atteint. |

## Pièges V3-4

| ID | Attendu | Observé | Verdict sémantique |
|---|---|---|---:|
| T01 | route `services_en_ligne` | clarification inter, candidat `services_en_ligne` | FAIL |
| T02 | route `services_en_ligne` | route `changement_coordonnees` | FAIL |
| T03 | clarification intra `services_en_ligne` | route `services_en_ligne` | FAIL |
| T04 | clarification inter `changement_coordonnees/cotisations` | route `changement_coordonnees` | FAIL |
| T05 | clarification inter `changement_coordonnees/cotisations` | route `cotisations` | FAIL |
| T06 | clarification inter `arret_travail/cotisations/justificatif_droits` | route `justificatif_droits` | FAIL |
| T07 | route `justificatif_droits` | route `justificatif_droits` | PASS sémantique, FAIL CLI |
| T08 | route `arret_travail` | route `arret_travail` | PASS sémantique, FAIL CLI |
| T09 | route `teletransmission_noemie` | route `teletransmission_noemie` | PASS sémantique, FAIL CLI |
| T10 | route `resiliation` | route `resiliation` | PASS sémantique, FAIL CLI |
| T11 | escalade conseiller | `escalate`, intent `demande_conseiller` | PASS sémantique, FAIL CLI |
| T12 | rejet | `reject`, intent `hors_perimetre` | PASS |
| T13 | rejet | clarification inter, candidat `cotisations` | FAIL |
| T14 | route `teletransmission_noemie` | route `teletransmission_noemie` | PASS sémantique, FAIL CLI |
| T15 | route `services_en_ligne` | rejet, intent `changement_coordonnees` | FAIL |

## Anomalies

1. **Image trop lourde** : `3.69GB` via `docker images`.
2. **Préflight strict bloqué** : worktree non clean avant campagne. Les fichiers concernés sont des livrables/plan, pas le code applicatif, mais la règle CE-1 reste échouée.
3. **Entraînement trop lent** : même après correction du crash CV, le train MGEN prend 25-30 minutes selon l'itération.
4. **Atomicité incomplète** : un kill/restart ne laisse pas de manifeste partiel, mais l'état de job n'est pas persisté en `failed`.
5. **Matrice/advice peu utiles** : CV head-only donne 100% et aucun conseil ; elle ne révèle pas la confusion attendue par le protocole.
6. **Latence manifeste instable** : la mesure indépendante passe, la mesure manifeste post V2-5 échoue.
7. **`loko-eval` bug de sortie** : `errors.csv` plante avec `ValueError: dict contains fields not in fieldnames: 'correct'`.
8. **`loko-eval` pièges bug de sémantique** : `route:services_en_ligne` est comparé à `decision.type == "route"` sans vérifier l'intention, ce qui fausse le score CLI.
9. **GNG insuffisants** : GNG-1, GNG-2 et pièges sous les seuils ; GNG-3 atteint le seuil global mais expose 9 routes métier directes hors-scope.

## Gates

| Gate | Verdict | Motif |
|---|---:|---|
| G-0 | FAIL | CE-1 et V0-5 échouent. V0-1/V0-2/V0-4 passent ; V0-3 passe avec réserve. |
| G-1 éliminatoire | PASS | V1-1 à V1-4 passent. |
| G-1b | PASS | V1-5 offline passe fonctionnellement. |
| G-2 | FAIL | V2-1, V2-3, V2-4, V2-5, V2-6 échouent ou partiellement échouent. |
| G-3 | FAIL | GNG-1, GNG-2, V3-4 et V3-6 échouent ; V3-3 est techniquement invalide malgré `81%`. |

## Décision

**R0+R1 NON VALIDES.** Les corrections R0 sont globalement efficaces et permettent enfin d'obtenir une session runtime positive avec provider LLM réel, puis un fail-fast propre après suppression du modèle. La suite doit maintenant cibler R1 : performance d'entraînement, persistance explicite des jobs interrompus, utilité réelle de l'évaluation CV/advice, correction de `loko-eval`, amélioration métier du modèle sur les held-out et les pièges.
