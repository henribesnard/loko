# RAPPORT DE CAMPAGNE — 2026-07-17 20:32 UTC

**Version** : 1.3.0
**Tag** : v1.3.0
**Commit** : a89cac3
**Image digest** : sha256:c0b31e001bfed
**Bot ID** : fa4d8b2d-548f-457b-bf65-acbc61a39cbb
**Manifeste modèle** : 
**Protocole** : v2.2
**Runner** : 1.0.0
**Machine de référence** : poste-ref-ryzen7-5800HS-win11-docker28.5-wsl2
**Dry-run** : NON

## Interdits opposables v2.2 (rappel)

- 1. Requalifier un test unitaire ou un exemple isole en pourcentage GNG.
- 2. Mesurer depuis l'hote au lieu du conteneur.
- 3. Omettre ou 'skipper' une ligne du tableau de synthese (non execute = FAIL).
- 4. Valider un critere 'structurellement' / 'au niveau code' sans execution.
- 5. Toucher aux CSV held-out (y compris renommage de labels), ou entrainer avec.
- 6. Committer pendant la campagne sans repartir de V0-1 (hors derogation V3-0 tracee).
- 7. Presenter des chiffres GNG a seuils non figes ou differents entre jeux.
- 8. Requalifier un FAIL en artefact de mesure pendant la campagne.
- 9. Declarer un gate ou un 'R' valide sans execution de toutes ses lignes ; les verdicts de gates sont calcules par le runner, jamais rediges.

## Tableau de synthèse

| # | Description | Verdict | Mesuré | Artefact |
|---|---|---|---|---|
| CE-1 | Worktree clean, main branch | PASS PASS | branch=main, clean=yes | CE-1.txt |
| CE-2 | Tag present + triple version check | PASS PASS | tag=v1.3.0, pyproject=1.3.0 | CE-2.txt |
| CE-3 | Docker image built + size <= 1.6 Go | PASS PASS | image=loko:v1.3.0, size=1001MB | CE-3.txt |
| CE-4 | Frozen datasets present + hashes match | PASS PASS | 5 files verified | CE-4.txt |
| CE-5 | Dataset intersection check (no leakage) | PASS PASS | exit 0 - no intersection | CE-5.txt |
| CE-6 | loko-eval installed and importable | PASS PASS | loko-eval importable | CE-6.txt |
| CE-7 | Campaign artifacts directory exists | PASS PASS | eval\recette-integrale\2026-07-17-v1.3.0 | 2026-07-17-v1.3.0 |
| CE-8 | LLM provider ping (temp 0) | PASS PASS | LLM config present | CE-8.txt |
| CE-9 | Bot conformity: 9 intents + L2 labels | PASS PASS | 9 intents, L2 OK | CE-9_conformity.json |
| V0-1 | pytest: all tests pass | FAIL FAIL | exit 1 | - |
| V0-2 | ML imports (PyTorch, SetFit) | PASS PASS | torch=2.10.0+cpu, cuda=False
setfit=ok
st=ok | V0-2_imports.txt |
| V0-3 | Anti-mock grep (0 occurrences) | PASS PASS | 0 occurrences | V0-3_grep.txt |
| V0-4 | npm/pip audit (0 vulnerabilities) | FAIL FAIL | EXCEPTION: [WinError 2] Le fichier spécifié est introuvable | - |
| V0-5 | Image size by inspect <= 1.6 Go | PASS PASS | 1001MB | V0-5_size.txt |
| V1-1 | Server startup + health check | FAIL FAIL | NON EXECUTE - requires running container or manual execution | - |
| V1-2 | No-mock guard active at runtime | FAIL FAIL | NON EXECUTE - requires running container or manual execution | - |
| V1-3 | Classifier loader integrity | FAIL FAIL | NON EXECUTE - requires running container or manual execution | - |
| V1-4 | CRITICAL log at boot (check_published_bots) | FAIL FAIL | NON EXECUTE - requires running container or manual execution | - |
| V1-5 | Offline mode (HF_HUB_OFFLINE=1) | FAIL FAIL | NON EXECUTE - requires running container or manual execution | - |
| V2-1 | Training time <= 300s | FAIL FAIL | NON EXECUTE - requires running container or manual execution | - |
| V2-2 | L2 coverage (help_account 5 labels) | FAIL FAIL | NON EXECUTE - requires running container or manual execution | - |
| V2-3 | Atomicity (train -> publish -> restart -> identical) | FAIL FAIL | NON EXECUTE - requires running container or manual execution | - |
| V2-4 | Improvement cycle: pair detected + re-train | FAIL FAIL | NON EXECUTE - requires running container or manual execution | - |
| V2-5 | Improvement cycle: verify pair resolved | FAIL FAIL | NON EXECUTE - requires running container or manual execution | - |
| V2-6 | Classification P95 <= 50ms (machine de reference) | FAIL FAIL | NON EXECUTE - requires running container or manual execution | - |
| V3-0 | Sweep Pareto 3-axis + selection | FAIL FAIL | selection.json not produced | - |
| V3-1 | GNG-1 >= 85% (heldout_metier) | FAIL FAIL | report.json not produced | - |
| V3-2 | GNG-2 >= 90% (heldout_conseiller) | FAIL FAIL | report.json not produced | - |
| V3-3 | GNG-3 >= 80%, routes directes <= 5 (heldout_horsscope) | FAIL FAIL | report.json not produced | - |
| V3-4 | Pieges >= 12/15 commentes | FAIL FAIL | report.json not produced | - |
| V3-5 | Modele + seuils + manifeste geles | FAIL FAIL | manifest.json not found | - |
| V3-6 | Reproducibility: diff vide sur 2 runs | FAIL FAIL | run 1 did not produce report.json | - |

## Verdicts des gates (CALCULÉS par le runner)

| Gate | Description | Verdict | Détail |
|---|---|---|---|
| CE | Conditions d'entree (bloquant) | PASS PASS | 9/9 passed |
| G-0 | Build validation | FAIL FAIL | 3/5 passed |
| G-1 | Runtime R0 (eliminatoire) | FAIL FAIL | 0/4 passed |
| G-1b | Offline mode | FAIL FAIL | 0/1 passed |
| G-2 | Training R1.a | FAIL FAIL | 0/6 passed |
| G-3 | Evaluation R1.b (verrou qualite) | FAIL FAIL | 0/7 passed |

## Anomalies de protocole suspectées

*(Cette section n'altère JAMAIS les verdicts ci-dessus)*

- V0-4: exception during execution: [WinError 2] Le fichier spécifié est introuvable

## Décision de campagne

**NON VALIDE** — Gates en échec : G-0, G-1, G-1b, G-2, G-3

---
*Rapport généré automatiquement par le runner de campagne v1.0.0*
*Les verdicts de gates sont calculés, non rédigés (interdit n°9).*