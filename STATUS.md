# LOKO — Tableau de bord projet

> Derniere mise a jour : 2026-08-01 (LOT F2 + audit de completude LOT C)
> Version courante : **1.3.4** (pyproject.toml)

---

## 1. Securite et garde-fous

| Composant | Statut | Detail |
|---|---|---|
| Pre-filtre regex (guardrails.py) | FAIT | 7 regles systeme, 5 categories, protection ReDoS (<1ms) |
| reject_no_llm (aucun appel LLM) | FAIT | Orchestrateur bloque avant classification+retrieval |
| Durcissement prompt systeme | FAIT | Anti-injection, anti-divulgation, balises `<contexte>` |
| Detection de fuites (post-gen) | FAIT | Patterns cles API, tokens, chemins disque, stack traces |
| Detection fuites streaming | FAIT | Fenetre glissante 200 chars, arret immediat |
| Compteur d'infractions | FAIT | Session.infractions, max configurable, FIN_FERME ou escalade |
| Grounding check (ancrage FAQ) | FAIT | n-grammes vs chunks, mode observation (block_low_grounding=false) |
| Basic-auth Caddy (prod) | FAIT | Toutes routes protegees sur loko.wezon.fr |
| adversarial.csv (55 cas) | FAIT | 6 categories: injection, dangereux, tiers, contournement, pieges |
| Documents canari (ZORGLUB-4417) | FAIT | 5 documents avec injection indirecte, README documente |

## 2. Classifieur et calibration

| Composant | Statut | Detail |
|---|---|---|
| SetFit L1 (paraphrase-multilingual-MiniLM-L12-v2) | FAIT | 9 intentions + hors_perimetre + demande_conseiller |
| SetFit L2 (sous-motifs help_account) | FAIT | 5 sous-labels |
| Calibration temperature (A1) | FAIT | Lecture temperature depuis manifest dans loader.py |
| Calibration training (A2) | FAIT | find_optimal_temperature() appele en fin d'entrainement |
| Parite runtime/eval (A3) | FAIT | loko-eval utilise le meme SetFitClassifierAdapter que le runtime |
| Mesure effet calibration (A4) | A FAIRE | Necessite execution in-container avec bot entraine |
| Manifest modele (A4/A5) | FAIT | SHA-256 fichiers, labels, metriques, calibration |
| Verification integrite modele | FAIT | verify_model(): manifest + hash + load + smoke test |
| Latence inference (B3/L5) | FAIT | measure_inference_latency(): P50/P95, warmup, GC |

## 3. Logique de decision

| Composant | Statut | Detail |
|---|---|---|
| decide_l1() route/clarify/reject/escalate | FAIT | Seuils haut/bas/ecart configurables |
| Clarification intra-intention | FAIT | Sous-motifs L2 quand confiance L1 haute |
| Clarification inter-intentions | FAIT | Top-2 proches quand confiance dans zone grise |
| Escalade demande_conseiller | FAIT | Detection transverse + template escalade |
| Rejet hors_perimetre | FAIT | Intention hors_perimetre -> template reject |
| Pieges T01-T15 | FAIT | 15 cas limites documentes et testes |

## 4. Datasets et evaluation

| Dataset | Lignes | Hash gele | CI guard |
|---|---|---|---|
| train.csv | 145 | Oui | sha256sum + make_datasets.py --check |
| heldout_metier.csv | 100 | Oui | idem |
| heldout_conseiller.csv | 125 | Oui | idem |
| heldout_horsscope.csv | 100 | Oui | idem |
| pieges.csv | 15 | Oui | idem + validation IDs T01-T15 |
| adversarial.csv | 55 | Oui | idem + validation colonnes/categories/behaviors |

Toute modification CSV sans mise a jour HASHES.sha256 -> CI FAIL (Interdit #5).

## 5. Pipeline CI/CD

| Job | Role | Declencheur |
|---|---|---|
| guard-datasets (V2/C5) | Integrite datasets + HASHES.sha256 + make_datasets.py --check | push, PR |
| guard-client-mentions (H1) | Aucune mention client reelle dans le code | push, PR |
| lint-python | ruff check + ruff format | push, PR |
| test-python (in-container) | pytest ~470 tests in-container, Docker build, coverage | push, PR (apres guards) |
| test-frontend | ESLint + Vitest + npm audit | push, PR |
| guard-version (V1) | Pas de doublon de version | main, tags |
| version-sync (T1) | Tag git = pyproject.toml = importlib | tags v* |

## 6. Tests

| Domaine | Fichiers | Tests | Couverture |
|---|---|---|---|
| Bot API | 5 | ~45 | Endpoints, auth, CORS, rate limiting |
| Decision logic | 2 | ~43 | Parite runtime/eval, seuils, cas limites |
| Analytics | 6 | ~52 | Emitter, observer, queries, dashboard |
| Training/ML | 2 | ~26 | Entrainement, classifier, calibration |
| End-to-end | 3 | ~95 | Protocole FSM, assistant, campagne |
| Securite | 4 | ~27 | Auth, secrets, guardrails, publish |
| Eval CLI | 2 | ~22 | Runner, sweep, 3-axis |
| Monitoring | 1 | ~12 | Prometheus metrics |
| Etat/Persistance | 3 | ~18 | Sessions, locks, train state |
| Manifest/Integrite | 1 | ~6 | Hash, schema, smoke test |
| **Total** | **56** | **~612** | |

Skips conditionnels: 2-3 (plateforme Windows, absence data/).
Marqueurs xfail: aucun.

## 7. Deploiement

| Composant | Statut | Detail |
|---|---|---|
| Dockerfile (3 stages) | FAIT | Frontend build + HF model download + backend |
| docker-compose.yml | FAIT | loko + prometheus + alertmanager |
| Prometheus | FAIT | Scrape /metrics chaque 15s, 30j retention |
| AlertManager | FAIT | 3 alertes (erreurs, latence, disponibilite) |
| SMTP alerting | CONFIG REQUISE | Placeholder auth_password a remplir |
| Volume persistant | FAIT | /home/loko/.loko monte depuis l'hote |

## 8. Points en attente (decision humaine)

| Item | Blocage | Action requise |
|---|---|---|
| LOT A4 — Mesure calibration | Execution in-container | Lancer campagne v1.3.4 pour mesurer l'effet |
| LOT D — Campagne v1.3.4 | Decision humaine | Decider si on lance la campagne avec les ameliorations |
| LOT E — Ameliorations profondes | Post G-3 | Latence, hors_perimetre comme OOD rejection |
| Desktop version sync | Intentionnel | desktop/package.json (0.1.0) != pyproject.toml (1.3.4) |
| SMTP AlertManager | Config prod | Remplir SMTP_PASSWORD et adresses email |

## 9. Historique des lots

| Lot | Date | Statut | Commit |
|---|---|---|---|
| LOT 0.1 — Basic-auth Caddy | 2026-08-01 | FAIT | Config serveur (hors repo) |
| LOT 0.2 — Inventaire donnees | 2026-08-01 | FAIT | eval/mission-obs/01_LOT0_INVENTAIRE.md |
| LOT 0.3 — Rotation secrets | 2026-08-01 | N/A | Pas de donnees tierces trouvees |
| LOT A1 — Temperature manifest | 2026-08-01 | FAIT | loko/bot/classifier/loader.py |
| LOT A2 — Calibration training | 2026-08-01 | FAIT | loko/bot/classifier/training.py, manifest.py |
| LOT A3 — Parite eval/runtime | 2026-08-01 | FAIT | loko/eval/cli.py |
| LOT B1 — adversarial.csv | 2026-08-01 | FAIT | eval/datasets/adversarial.csv (55 cas) |
| LOT B2 — Documents canari | 2026-08-01 | FAIT | eval/canary-documents/ (5 docs) |
| LOT B3 — CI guard adversarial | 2026-08-01 | FAIT | tools/make_datasets.py, HASHES.sha256 |
| LOT C — Audit completude | 2026-08-01 | FAIT | STATUS.md (ce fichier) |
| LOT F2 — STATUS.md | 2026-08-01 | FAIT | STATUS.md (ce fichier) |
