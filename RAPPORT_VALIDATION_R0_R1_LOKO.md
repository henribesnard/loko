# Rapport campagne R0+R1 — 4 juillet 2026

Protocole : `PROTOCOLE_VALIDATION_R0_R1_LOKO.md`  
Mode : Docker local, executions in-container uniquement lorsque possible  
Artefacts : `eval/campagne-R0R1/2026-07-04-codex/`  
Tag annonce : `v0.3.0`  
Commit : `2297fa5e349a79cec60c8f96dd78cd7e47a2285a`

## Verdict

**R0+R1 NON VALIDES.**

La campagne ne demarre pas validement : la condition d'entree CE-3 echoue. L'image Docker ne se construit pas, car `pip install -e ".[server,ml]"` echoue sur le backend `setuptools.backends._legacy:_Backend` declare dans `pyproject.toml`. La meme erreur est reproduite dans un conteneur `python:3.12-slim`, ce qui confirme un probleme de packaging du depot, pas un incident Docker.

Selon le protocole, toutes les executions R0/R1 doivent etre in-container. Sans image construite, V0-1/V0-2 puis V1/V2/V3 sont non recevables et notes FAIL/non executes par defaut.

## Conditions d'entree

| ID | Verdict | Observation | Artefact |
|---|---|---|---|
| CE-1 CI verte | NON VERIFIE | Aucun lien CI fourni dans le depot local. | - |
| CE-2 Tag/commit | PASS partiel | `git describe`: `v0.3.0`, commit consigne. Worktree non propre : `dataset.csv` et artefacts non suivis. | `CE-2_git_version.txt` |
| CE-3 Image construite | **FAIL bloquant** | `docker build -t loko-r0r1-codex:latest .` echoue : `Cannot import 'setuptools.backends._legacy'`. | `CE-3_docker_build.txt`, `CE-3_pyproject_backend.txt` |
| CE-4 Datasets figes | PASS partiel | Hashes recalcules conformes a `HASHES.sha256`. Comptes : 100/126/100/15 OK ; `train.csv` contient 1801 lignes. | `CE-4_dataset_hashes_counts.txt` |
| CE-5 Intersection train/held-out vide | FAIL partiel | Held-out metier/conseiller/horsscope : overlap 0. `pieges.csv` chevauche `train.csv` sur `noemie`. `tools/make_datasets.py --check` n'existe pas. | `CE-5_train_heldout_overlap.txt`, `CE-5_make_datasets_check.txt` |
| CE-6 `loko-eval` dans image | FAIL par dependance | Script declare dans `pyproject.toml`, modules presents, mais impossible de verifier l'installation dans l'image puisque le build echoue. | `CE-6_loko_eval_presence.txt` |
| CE-7 Repertoire artefacts | PASS | Repertoire cree. | `eval/campagne-R0R1/2026-07-04-codex/` |

## V0 — Recevabilite technique

| ID | Verdict | Observation |
|---|---|---|
| V0-1 Suite complete in-container | FAIL non executable | Image non construite. |
| V0-2 Imports ML in-container | FAIL non executable | Image non construite. |
| V0-3 Lint anti-mock | FAIL protocole | Le grep statique trouve encore des imports/definitions de mocks dans `loko/`. Certains sont gardes par `RAGKIT_ENV`, mais le protocole V0-3 demandait 0 occurrence hors tests. |
| V0-4 Audit front | **FAIL** | `npm audit --audit-level=high` retourne 5 vulnerabilites, dont 1 high et 1 critical via Vite/Vitest. |
| V0-5 Taille image | FAIL non executable | Image non construite. |

## V1 — Integrite anti-mock

Non executable validement. Les tests V1-1 a V1-5 exigent le conteneur de campagne. Comme CE-3 echoue, la gate G-1 est **FAIL par defaut**.

Constats statiques utiles :

- Les gardes de mocks semblent avoir ete ajoutes dans `_MockClassifier`, `MockLLMProvider`, `InMemorySearchBackend`, `MockEscalationProvider`.
- Le protocole manuel reference `tests/bot/test_no_mock_guard.py`, mais le fichier present est `tests/bot/test_mock_guards.py`.
- Le protocole reference `loko.bot.classifier.loader._load_classifier`, mais `_load_classifier` est actuellement dans `loko/api/bot_public.py`.
- `MockEscalationProvider` est autorisable via `LOKO_ESCALATION_PROVIDER=mock`, conforme a l'exception prevue, mais non verifie in-container.

## V2/V3 — Entrainement et evaluation statistique

Non executes. La porte intermediaire V1-1 a V1-4 ne peut pas passer sans image, et le protocole interdit de produire des chiffres R1 sur un environnement non recevable.

Ecarts detectes avant execution :

- `constraints-ml.txt` est un gabarit vide, pas un vrai `pip freeze` verrouille.
- Le Dockerfile copie `constraints-ml.txt` mais n'utilise pas `-c constraints-ml.txt` dans `pip install`.
- `tools/make_datasets.py` ne propose pas `--check`, contrairement a CE-5.
- `pieges.csv` ne correspond pas aux T01-T15 du postulat d'origine cite par le protocole R1.9 ; par exemple T04 n'est pas `RIB coordonnees bancaires` mais une demande conseiller.

## Anomalies bloquantes

1. **Packaging Python invalide**
   - Fichier : `pyproject.toml`
   - Ligne : `build-backend = "setuptools.backends._legacy:_Backend"`
   - Effet : build Docker et installation editable impossible.
   - Correction attendue avant nouvelle campagne : remplacer par un backend setuptools valide, typiquement `setuptools.build_meta` ou `setuptools.build_meta:__legacy__` selon le besoin.

2. **Audit frontend encore rouge**
   - `npm audit --audit-level=high` echoue.
   - 5 vulnerabilites : 3 moderate, 1 high, 1 critical.

3. **Outillage dataset incomplet**
   - `tools/make_datasets.py --check` absent.
   - Intersection `train.csv` / `pieges.csv` non vide.
   - Jeux pieges non alignes avec les cas T01-T15 attendus par le protocole.

4. **Contraintes ML non verrouillees**
   - `constraints-ml.txt` ne contient pas de versions freezees.
   - Le Dockerfile ne l'applique pas.

## Conclusion

La campagne R0+R1 doit etre rejouee depuis V0-1 apres correction du packaging et reconstruction d'une image valide. Aucun chiffre GNG-1/GNG-2/GNG-3 n'est opposable dans cet etat.

Priorite de reprise :

1. Corriger `pyproject.toml` pour rendre `pip install -e ".[server,ml]"` executable.
2. Appliquer reellement `constraints-ml.txt` ou le remplir/supprimer proprement.
3. Corriger `npm audit --audit-level=high`.
4. Ajouter `tools/make_datasets.py --check` et aligner `pieges.csv` sur le protocole.
5. Reconstruire l'image, consigner le digest, puis relancer V0-1 a V3-6.
