# RAPPORT DE CAMPAGNE — 2026-07-17 21:45 UTC

**Version** : 1.3.2
**Tag** : v1.3.2
**Commit** : 21b1fbf
**Image digest** : sha256:fc4a926b910b6
**Bot ID** : fa4d8b2d-548f-457b-bf65-acbc61a39cbb
**Manifeste modèle** : 
**Protocole** : v2.2
**Runner** : 1.1.0
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
| CE-2 | Tag present + triple version check | PASS PASS | tag=v1.3.2, pyproject=1.3.2 | CE-2.txt |
| CE-3 | Docker image built + size <= 1.6 Go | PASS PASS | image=loko:v1.3.2, size=1001MB | CE-3.txt |
| CE-4 | Frozen datasets present + hashes match | PASS PASS | 5 files verified | CE-4.txt |
| CE-5 | Dataset intersection check (no leakage) | PASS PASS | exit 0 - no intersection | CE-5.txt |
| CE-6 | loko-eval installed and importable | PASS PASS | loko-eval importable | CE-6.txt |
| CE-7 | Campaign artifacts directory exists | PASS PASS | eval\recette-integrale\2026-07-17-v1.3.2 | 2026-07-17-v1.3.2 |
| CE-8 | LLM provider ping (temp 0) | PASS PASS | LLM config present | CE-8.txt |
| CE-9 | Bot conformity: 9 intents + L2 labels | PASS PASS | 9 intents, L2 OK | CE-9_conformity.json |
| V0-1 | pytest: all tests pass | FAIL FAIL | exit 1 (in-container) | - |
| V0-2 | ML imports (PyTorch, SetFit) | PASS PASS | in-container: torch=2.12.1+cpu, cuda=False setfit=ok st=ok | V0-2_imports.txt |
| V0-3 | Anti-mock grep (0 occurrences) | PASS PASS | 0 occurrences | V0-3_grep.txt |
| V0-4 | npm/pip audit (0 vulnerabilities) | PASS PASS | pip check in-container OK (pip-audit absent de l'image) | V0-4_audit.txt |
| V0-5 | Image size by inspect <= 1.6 Go | PASS PASS | 1001MB | V0-5_size.txt |
| V1-1 | Server startup + health check | PASS PASS | health 200: {"status":"ok","service":"loko-bot","version":"1.3.2"} | V1-1_boot.txt |
| V1-2 | No-mock guard active at runtime | PASS PASS | garde active: RuntimeError levée hors env test | V1-2_nomock.txt |
| V1-3 | Classifier loader integrity | PASS PASS | fail-fast: exception typée, aucun fallback loader | V1-3_loader.txt |
| V1-4 | CRITICAL log at boot (check_published_bots) | PASS PASS | CRITICAL loggé au boot pour bot publié sans modèle (v14-4005fa6b) | V1-4_boot_critical.txt |
| V1-5 | Offline mode (HF_HUB_OFFLINE=1) | PASS PASS | service OK sous --network none: {"status":"ok","service":"loko-bot","version":"1.3.2"} | V1-5_offline.txt |
| V2-1 | Training time <= 300s | FAIL FAIL | EXCEPTION: can only concatenate str (not "NoneType") to str | - |
| V2-2 | L2 coverage (help_account 5 labels) | PASS PASS | L2 help_account: 5 labels | V2-2_l2.txt |
| V2-3 | Atomicity (train -> publish -> restart -> identical) | PASS PASS | état antérieur intact après kill, modèle rechargeable | V2-3_atomicity.txt |
| V2-4 | Improvement cycle: pair detected + re-train | FAIL FAIL | EXCEPTION: can only concatenate str (not "NoneType") to str | - |
| V2-5 | Improvement cycle: verify pair resolved | FAIL FAIL | artefacts V2-4 absents | - |
| V2-6 | Classification P95 <= 50ms (machine de reference) | FAIL FAIL | P95=230.13ms (contre-mesure 50.68ms, écart 78%), n=200, in-container | - |
| V3-0 | Sweep Pareto 3-axis + selection | PASS PASS | haut=0.90 bas=0.40 ecart=0.00 | GNG-1=78.0% GNG-2=85.6% GNG-3=84.0% | selection.json |
| V3-1 | GNG-1 >= 85% (heldout_metier) | FAIL FAIL | GNG-1=78.0% (78/100) | - |
| V3-2 | GNG-2 >= 90% (heldout_conseiller) | FAIL FAIL | GNG-2=85.6% (107/125) | - |
| V3-3 | GNG-3 >= 80%, routes directes <= 5 (heldout_horsscope) | PASS PASS | GNG-3=84.0% (84/100) | report.json |
| V3-4 | Pieges >= 12/15 commentes | FAIL FAIL | pieges=53.3% (8/15) | - |
| V3-5 | Modele + seuils + manifeste geles | PASS PASS | manifest_hash=8aca9bca264bee64... | manifest.json |
| V3-6 | Reproducibility: diff vide sur 2 runs | PASS PASS | 2 runs in-container identiques | V3-6_diff.txt |

## Verdicts des gates (CALCULÉS par le runner)

| Gate | Description | Verdict | Détail |
|---|---|---|---|
| CE | Conditions d'entree (bloquant) | PASS PASS | 9/9 passed |
| G-0 | Build validation | FAIL FAIL | 4/5 passed |
| G-1 | Runtime R0 (eliminatoire) | PASS PASS | 4/4 passed |
| G-1b | Offline mode | PASS PASS | 1/1 passed |
| G-2 | Training R1.a | FAIL FAIL | 2/6 passed |
| G-3 | Evaluation R1.b (verrou qualite) | FAIL FAIL | 4/7 passed |

## Anomalies de protocole suspectées

*(Cette section n'altère JAMAIS les verdicts ci-dessus)*

- V2-1: exception during execution: can only concatenate str (not "NoneType") to str
- V2-4: exception during execution: can only concatenate str (not "NoneType") to str

## Décision de campagne

**NON VALIDE** — Gates en échec : G-0, G-2, G-3

---
*Rapport généré automatiquement par le runner de campagne v1.1.0*
*Les verdicts de gates sont calculés, non rédigés (interdit n°9).*