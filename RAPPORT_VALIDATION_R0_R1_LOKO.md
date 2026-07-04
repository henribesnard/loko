# Rapport campagne R0+R1 - 2026-07-05

## Verdict

**R0+R1 NON VALIDES.**

La campagne opposable est bloquee avant V0 : l'image applicative ne construit pas et le worktree n'est pas clean. Les tests R0/R1 in-container sur l'image cible n'ont donc pas pu etre declares valides. Les controles independants executables dans des conteneurs generiques ont ete collectes a titre diagnostique, sans valeur de validation produit.

## Perimetre

- Protocole applique : `PROTOCOLE_VALIDATION_R0_R1_LOKO.md`
- Mode d'execution demande : Docker local
- Date d'execution : 2026-07-05
- Tag courant : `v0.3.1`
- Commit : `dcd3a5db738763b049e4ec826736e7ab9e4a0d04`
- Description Git : `v0.3.1-dirty`
- Image cible tentee : `loko-r0r1-codex:2026-07-05`
- Repertoire artefacts : `eval/campagne-R0R1/2026-07-05-codex/`

Aucune valeur sensible de `.env` n'a ete copiee dans les artefacts.

## Conditions d'entree

| ID | Verdict | Constats | Artefact |
|---|---:|---|---|
| CE-1 | FAIL | Branche `main`, mais worktree non clean : `PLAN_CORRECTION_R0_R1_LOKO.md` et `RAPPORT_VALIDATION_R0_R1_LOKO.md` etaient supprimes au debut de campagne. | `CE_preflight_with_args.txt`, `git_status_porcelain.txt` |
| CE-2 | PASS avec reserve | Tag exact `v0.3.1` present, commit consigne. Reserve : `git describe --dirty` retourne `v0.3.1-dirty`. | `CE-2_git_describe.txt`, `commit.txt` |
| CE-3 | FAIL | `docker build -t loko-r0r1-codex:2026-07-05 .` echoue. Cause : `project.license = "Proprietary"` est refuse par `setuptools` car ce n'est pas un identifiant SPDX valide ni une table `{text=...}` / `{file=...}`. Aucune image produite, aucun digest disponible. | `CE-3_docker_build.txt`, `CE-3_image_inspect.txt` |
| CE-4 | FAIL protocole strict / PASS outil interne | Les hashes sont conformes, mais le protocole attend `heldout_conseiller.csv = 126` lignes alors que le dataset, `tools/make_datasets.py` et `tests/test_datasets.py` attendent et mesurent 125 lignes. | `CE-4_dataset_counts.txt`, `CE-4_hashes_sha256.txt` |
| CE-5 | PASS | `python tools/make_datasets.py --check eval/datasets` retourne exit 0. | `CE-5_dataset_check.txt` |
| CE-6 | FAIL | `loko-eval` est importable localement, mais non verifiable dans l'image car l'image n'existe pas. | `CE_preflight_with_args.txt` |
| CE-7 | PASS | Repertoire d'artefacts cree. | `CE_preflight_with_args.txt` |

Resultat preflight avec arguments : **4/7 PASS, BLOCKED**.

## Tableau de synthese V0-V3

| ID | Verdict | Resultat objectif | Artefact |
|---|---:|---|---|
| V0-1 | BLOQUE | Suite complete non executee : l'image applicative ne construit pas. | `CE-3_docker_build.txt` |
| V0-2 | BLOQUE | Imports ML non executes dans l'image cible absente. | `CE-3_docker_build.txt` |
| V0-3 | DIAG PASS / BLOQUE protocole | Tests AST anti-mock executes dans `python:3.12-slim` avec dependances minimales : 11 passed. Le grep brut detecte seulement une mention en docstring dans `loko/bot/escalation.py`, pas un import de production. Non opposable car hors image cible. | `DIAG_no_mock_pytest_generic_container_rerun.txt`, `DIAG_static_mock_reference_grep.txt` |
| V0-4 | FAIL | `npm ci` echoue avant audit sur conflit de dependances : `vite@8.1.3` n'est pas compatible avec le peer range de `@vitejs/plugin-react@4.7.0` (`^4.2.0 || ^5 || ^6 || ^7`). Diagnostic lockfile-only : 0 vulnerabilities, non opposable car `npm ci` echoue. | `V0-4_npm_audit_generic_container.txt`, `DIAG_npm_audit_lockfile_only.txt` |
| V0-5 | BLOQUE | Taille image non mesuree : aucune image produite. | `CE-3_image_inspect.txt` |
| V1-1 | DIAG PASS / BLOQUE protocole | Tests et contre-epreuves manuelles executes dans conteneur Python generique : les 4 mocks levent `RuntimeError` hors test ; `LOKO_ESCALATION_PROVIDER=mock` n'autorise que `MockEscalationProvider`. Non opposable car hors image cible. | `DIAG_no_mock_pytest_generic_container_rerun.txt`, `DIAG_V1-1_manual_mock_guard_generic_container.txt` |
| V1-2 | DIAG PARTIEL PASS / BLOQUE protocole | `load_classifier("bot-inexistant")` leve `ComponentUnavailableError` sans fallback mock. Verification manifeste corrompu non executee, et test hors image cible. | `DIAG_V1-2_load_classifier_empty_generic_container.txt`, `V1-2_loader_static_grep.txt` |
| V1-3 | BLOQUE | Publication et contournements d'integrite non executables sans serveur issu de l'image. | `CE-3_docker_build.txt` |
| V1-4 | BLOQUE | Fail-fast runtime sur modele supprime non executable sans serveur issu de l'image. | `CE-3_docker_build.txt` |
| V1-5 | BLOQUE | Test offline non executable sans image contenant le modele local. | `CE-3_docker_build.txt` |
| V2-1 | BLOQUE | Entrainement L1 complet non execute : porte V1 non opposable et image absente. | `CE-3_docker_build.txt` |
| V2-2 | BLOQUE | Entrainement L2 non execute. | `CE-3_docker_build.txt` |
| V2-3 | BLOQUE | Atomicite entrainement non testee. | `CE-3_docker_build.txt` |
| V2-4 | BLOQUE | Rapport matrice/confusion non exporte. | `CE-3_docker_build.txt` |
| V2-5 | BLOQUE | Cycle d'amelioration mesure non execute. | `CE-3_docker_build.txt` |
| V2-6 | BLOQUE | Latence inference non mesuree. | `CE-3_docker_build.txt` |
| V3-1 | BLOQUE | Evaluation GNG-1 non executee. | `CE-3_docker_build.txt` |
| V3-2 | BLOQUE | Evaluation GNG-2 non executee. | `CE-3_docker_build.txt` |
| V3-3 | BLOQUE | Evaluation GNG-3 non executee. | `CE-3_docker_build.txt` |
| V3-4 | BLOQUE | Evaluation pieges non executee. | `CE-3_docker_build.txt` |
| V3-5 | NON APPLICABLE | Calibration non applicable : aucune evaluation V3 produite. | - |
| V3-6 | BLOQUE | Reproductibilite des chiffres non testee. | `CE-3_docker_build.txt` |

## Chiffres GNG

Aucun chiffre GNG opposable n'a ete produit.

- GNG-1 : non execute
- GNG-2 : non execute
- GNG-3 : non execute
- Pieges : non execute

Les scores seraient invalides tant que CE-3, CE-6 et la porte V1 ne sont pas passes dans l'image cible.

## Diagnostics executes hors campagne opposable

### Datasets

- `tools/make_datasets.py --check eval/datasets` : PASS.
- `pytest tests/test_datasets.py` dans `python:3.12-slim` : 12 passed.
- Comptes mesures :
  - `train.csv` : 125
  - `heldout_metier.csv` : 100
  - `heldout_conseiller.csv` : 125
  - `heldout_horsscope.csv` : 100
  - `pieges.csv` : 15

Point a arbitrer : le protocole ecrit `heldout_conseiller.csv = 126`, mais l'implementation et les tests figent 125.

### Anti-mock

- `pytest tests/bot/test_no_mock_import.py tests/bot/test_no_mock_guard.py -q` dans `python:3.12-slim` avec `pytest pydantic` : 11 passed.
- Contre-epreuves manuelles :
  - `_MockClassifier` bloque hors `RAGKIT_ENV=test`.
  - `MockLLMProvider` bloque hors `RAGKIT_ENV=test`.
  - `InMemorySearchBackend` bloque hors `RAGKIT_ENV=test`.
  - `MockEscalationProvider` bloque hors `RAGKIT_ENV=test`.
  - `LOKO_ESCALATION_PROVIDER=mock` autorise `MockEscalationProvider`.
  - `LOKO_ESCALATION_PROVIDER=mock` n'autorise pas `MockLLMProvider`.

Ces resultats sont encourageants mais non opposables au protocole car ils ne proviennent pas de l'image applicative.

### Loader classifier

`load_classifier("bot-inexistant")` leve :

```text
ComponentUnavailableError
classifier_l1 unavailable for bot bot-inexistant: Level 1 classifier not trained
```

Le fallback mock n'est donc pas observe sur le cas vide. Le cas manifeste corrompu n'a pas ete execute.

### Frontend

`npm ci` dans `node:20-alpine` echoue avant audit :

```text
ERESOLVE could not resolve
Found: vite@8.1.3
peer vite "^4.2.0 || ^5.0.0 || ^6.0.0 || ^7.0.0" from @vitejs/plugin-react@4.7.0
```

`npm audit --package-lock-only --audit-level=high` retourne 0 vulnerabilite, mais ce diagnostic ne remplace pas V0-4 puisque l'installation reproductible echoue.

## Anomalies bloquantes

1. **Build Docker impossible** : `pyproject.toml` n'est pas accepte par le backend de build actuel. Le champ `project.license` doit etre corrige avant toute nouvelle campagne.
2. **Worktree non clean** : les suppressions de `PLAN_CORRECTION_R0_R1_LOKO.md` et du rapport precedent rendent le tag `v0.3.1` dirty au moment de la campagne.
3. **Conflit npm reproductible** : `npm ci` echoue sur les dependances front. Meme apres correction Python, le Dockerfile devrait atteindre ce blocage lors du stage frontend.
4. **Incoherence protocole/datasets** : le protocole demande 126 lignes conseiller, les artefacts figes en contiennent 125 et les tests internes valident 125.

## Gates

| Gate | Verdict | Motif |
|---|---:|---|
| G-0 | FAIL | V0 non executable dans l'image ; V0-4 echoue sur `npm ci`. |
| G-1 | BLOQUE | V1-1/V1-2 seulement diagnostiques hors image ; V1-3/V1-4 non executes. |
| G-1b | BLOQUE | Offline non execute. |
| G-2 | BLOQUE | Entrainement non execute. |
| G-3 | BLOQUE | Evaluations statistiques non executees. |

## Decision

**R0+R1 NON VALIDES.**

Une nouvelle campagne doit repartir de CE-1 apres corrections minimales suivantes :

1. Corriger la metadata Python pour que `pip install -e ".[server,ml]"` fonctionne dans Docker.
2. Corriger l'arbre Git pour obtenir `git describe --tags --dirty --always` sans suffixe `dirty`.
3. Corriger les dependances frontend pour que `npm ci` passe.
4. Aligner le protocole et les datasets sur 125 ou 126 lignes `heldout_conseiller.csv`, puis regenerer/figer les hashes si necessaire.
