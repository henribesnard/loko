# RAPPORT DE CAMPAGNE — 2026-07-17 13:11 UTC

**Version** : 1.2.2
**Tag** : 
**Commit** : 0c00423
**Image digest** : 
**Bot ID** : reference
**Manifeste modèle** : 
**Protocole** : v2.2
**Runner** : 1.0.0
**Machine de référence** : (non declare)
**Dry-run** : OUI

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
| CE-1 | Worktree clean, main branch | FAIL FAIL | branch=main, dirty=75 | - |
| CE-2 | Tag present + triple version check | PASS PASS | tag=v1.2.2, pyproject=1.2.2 | CE-2.txt |
| CE-3 | Docker image built + size <= 1.6 Go | FAIL FAIL | no image specified | - |
| CE-4 | Frozen datasets present + hashes match | FAIL FAIL | HASHES.sha256 missing | - |
| CE-5 | Dataset intersection check (no leakage) | FAIL FAIL | make_datasets.py not found | - |
| CE-6 | loko-eval installed and importable | PASS PASS | loko-eval importable | CE-6.txt |
| CE-7 | Campaign artifacts directory exists | PASS PASS | /tmp/campagne-dryrun | campagne-dryrun |
| CE-8 | LLM provider ping (temp 0) | FAIL FAIL | config.json not found | - |
| CE-9 | Bot conformity: 9 intents + L2 labels | FAIL FAIL | config.json not found | - |
| V0-1 | pytest: all tests pass | FAIL FAIL | exit 1 | - |
| V0-2 | ML imports (PyTorch, SetFit) | FAIL FAIL | import error | - |
| V0-3 | Anti-mock grep (0 occurrences) | PASS PASS | 0 occurrences | V0-3_grep.txt |
| V0-4 | npm/pip audit (0 vulnerabilities) | FAIL FAIL | vulnerabilities found | - |
| V0-5 | Image size by inspect <= 1.6 Go | FAIL FAIL | no image specified | - |
| V1-1 | Server startup + health check | FAIL FAIL | DRY-RUN - non execute | - |
| V1-2 | No-mock guard active at runtime | FAIL FAIL | DRY-RUN - non execute | - |
| V1-3 | Classifier loader integrity | FAIL FAIL | DRY-RUN - non execute | - |
| V1-4 | CRITICAL log at boot (check_published_bots) | FAIL FAIL | DRY-RUN - non execute | - |
| V1-5 | Offline mode (HF_HUB_OFFLINE=1) | FAIL FAIL | DRY-RUN - non execute | - |
| V2-1 | Training time <= 300s | FAIL FAIL | DRY-RUN - non execute | - |
| V2-2 | L2 coverage (help_account 5 labels) | FAIL FAIL | DRY-RUN - non execute | - |
| V2-3 | Atomicity (train -> publish -> restart -> identical) | FAIL FAIL | DRY-RUN - non execute | - |
| V2-4 | Improvement cycle: pair detected + re-train | FAIL FAIL | DRY-RUN - non execute | - |
| V2-5 | Improvement cycle: verify pair resolved | FAIL FAIL | DRY-RUN - non execute | - |
| V2-6 | Classification P95 <= 50ms (machine de reference) | FAIL FAIL | DRY-RUN - non execute | - |
| V3-0 | Sweep Pareto 3-axis + selection | FAIL FAIL | DRY-RUN - non execute | - |
| V3-1 | GNG-1 >= 85% (heldout_metier) | FAIL FAIL | DRY-RUN - non execute | - |
| V3-2 | GNG-2 >= 90% (heldout_conseiller) | FAIL FAIL | DRY-RUN - non execute | - |
| V3-3 | GNG-3 >= 80%, routes directes <= 5 (heldout_horsscope) | FAIL FAIL | DRY-RUN - non execute | - |
| V3-4 | Pieges >= 12/15 commentes | FAIL FAIL | DRY-RUN - non execute | - |
| V3-5 | Modele + seuils + manifeste geles | FAIL FAIL | DRY-RUN - non execute | - |
| V3-6 | Reproducibility: diff vide sur 2 runs | FAIL FAIL | DRY-RUN - non execute | - |

## Verdicts des gates (CALCULÉS par le runner)

| Gate | Description | Verdict | Détail |
|---|---|---|---|
| CE | Conditions d'entree (bloquant) | FAIL FAIL | 3/9 passed |
| G-0 | Build validation | FAIL FAIL | 1/5 passed |
| G-1 | Runtime R0 (eliminatoire) | FAIL FAIL | 0/4 passed |
| G-1b | Offline mode | FAIL FAIL | 0/1 passed |
| G-2 | Training R1.a | FAIL FAIL | 0/6 passed |
| G-3 | Evaluation R1.b (verrou qualite) | FAIL FAIL | 0/7 passed |

## Anomalies de protocole suspectées

*(Cette section n'altère JAMAIS les verdicts ci-dessus)*

Aucune anomalie signalée.

## Décision de campagne

**MODE DRY-RUN — Aucune validation opposable**

---
*Rapport généré automatiquement par le runner de campagne v1.0.0*
*Les verdicts de gates sont calculés, non rédigés (interdit n°9).*