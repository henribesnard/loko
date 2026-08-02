# LOKO — Tableau de bord projet

> Derniere mise a jour : 2026-08-02 (BLOC 1-4 + E2 mesure — N5/N6/N7/N8/N9/N10/N11/E2-M0:M5)
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
| Mesure effet calibration (A4) | FAIT | T=0.60, ECE 3.14%->0.68%. **H3 confirmee** : T=0.60 aiguise les scores, regression GNG-3 (-8 pts) est mecanique. Contre-test T=1.0 : GNG-3 remonte a 81% (+9 pts) |
| Manifest modele (A4/A5) | FAIT | SHA-256 fichiers, labels, metriques, calibration |
| Verification integrite modele | FAIT | verify_model(): manifest + hash + load + smoke test |
| Latence inference (B3/L5) | FAIT | measure_inference_latency(): P50/P95, warmup, GC |
| Rejet OOD hors_perimetre (E2) | MESURE | ood.py: centroids, scoring, calibration. M0-M5 complet. Meilleur point (ood=0.40): GNG-1=81%, GNG-2=86.4%, GNG-3=77%, pieges=10/15. Delta vs baseline: GNG-3 +5pts, pieges +1, hmean +1.8pts. Trade-off structurel: aucun point ne satisfait les 4 gates. Rapport: eval/lot-e2/RAPPORT_E2.md |

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
| Securite | 5 | ~44 | Auth, secrets, guardrails, adversarial (N9), V-corrections |
| OOD Rejection | 1 | 27 | Centroids, scoring, calibration, adapter, decision, trace, manifest (E2) |
| Eval CLI | 2 | ~22 | Runner, sweep, 3-axis, 4-axis (E2) |
| Monitoring | 1 | ~12 | Prometheus metrics |
| Etat/Persistance | 3 | ~18 | Sessions, locks, train state |
| Manifest/Integrite | 1 | ~6 | Hash, schema, smoke test |
| Backup/Restore | 1 | 5 | Cycle complet backup-restore (N10) |
| **Total** | **60** | **~690** | |

Skips conditionnels: 1 (plateforme Windows, emitter chmod).
Marqueurs xfail: 1 (couverture pre-filtre adversarial partielle).

## 7. Deploiement

| Composant | Statut | Detail |
|---|---|---|
| Dockerfile (3 stages) | FAIT | Frontend build + HF model download + backend |
| docker-compose.yml | FAIT | loko + prometheus + alertmanager |
| Prometheus | FAIT | Scrape /metrics chaque 15s, 30j retention |
| AlertManager | FAIT | 3 alertes (erreurs, latence, disponibilite) |
| SMTP alerting | CONFIG REQUISE | Placeholder auth_password a remplir |
| Volume persistant | FAIT | /home/loko/.loko monte depuis l'hote |

## 8. Campagne diagnostic v1.3.4 (2026-08-01)

**Verdict** : NON VALIDE (mode diagnostic, non opposable). V3-7 iter 2/2 non consommee.

| Gate | Resultat | Detail |
|---|---|---|
| CE | PASS 9/9 | Datasets, hashes, intersection vide |
| G-0 | FAIL 4/5 | V0-1 pytest : 6 fails (fixtures <8 ex, asyncio 3.12), 6 errors |
| G-1 | PASS 4/4 | Boot, no-mock, loader, CRITICAL |
| G-1b | PASS 1/1 | Offline mode (--network none) |
| G-2 | FAIL 3/6 | V2-1 train 573s, V2-5 accuracy degradee, V2-6 P95=205ms |
| G-3 | FAIL 2/7 | V3-0 sweep infaisable, GNG-1=81%, GNG-2=87.2%, GNG-3=72%, pieges=9/15 |

| Metrique | Cible | v1.3.3 | v1.3.4 | Delta |
|---|---|---|---|---|
| GNG-1 metier | >= 85% | 81.0% | 81.0% | 0 |
| GNG-2 conseiller | >= 90% | 88.8% | 87.2% | -1.6 |
| GNG-3 hors-scope | >= 80% | 80.0% | 72.0% | **-8.0** |
| Pieges | >= 12/15 | 9/15 | 9/15 | 0 |

**Seuils utilises** : seuil_haut=0.85, seuil_bas=0.50, seuil_ecart=0.0 (config bot pre-existante, pas sweep-selectionnee).
**Calibration** : active (T=0.60, ECE 0.0314->0.0068). Tests PASS.
**Conclusion v1.1** : la conclusion "L2 s'applique" (v1.0) est retiree. Hypothese H3 dominante : la regression GNG-3 (-8 pts) est un effet mecanique de l'aiguisage (T<1 pousse les scores vers le haut, reduisant les rejets avec les seuils pre-calibration).
**GNG-3 erreurs** : dispersees sur 5 classes (help_contact 36%, help_documents/billing/transfer 18% chacun).
**Analyse** : `ANALYSE_POST_CAMPAGNE_v1.3.4.md` (v1.1, corrections signalees en clair)
**Artefacts** : `eval/recette-integrale/2026-08-01-v1.3.4/`

### 8b. Re-sweep post-calibration (Action 1, 2026-08-02)

Grille etendue (594 points) : seuil_haut=0.6:0.98:0.02, seuil_bas=0.3:0.85:0.05, seuil_ecart=0.0:0.20:0.10.
ECART_MIN relaxe a 0.00 (seuil_ecart inoperant avec calibration).

**9 points faisables** (GNG-3>=80%, routes<=5). Selection Pareto : seuil_haut=0.98, seuil_bas=0.75, seuil_ecart=0.00.

| Metrique | Cible | Seuils bot (0.85/0.50) | Re-sweep (0.98/0.75) |
|---|---|---|---|
| GNG-1 metier | >= 85% | 81.0% | **73.0%** |
| GNG-2 conseiller | >= 90% | 87.2% | 87.2% |
| GNG-3 hors-scope | >= 80% | 72.0% | **81.0%** |
| Routes directes | <= 5 | 13 | **4** |
| Pieges | >= 12/15 | 9/15 | 8/15 |

**Conclusion** : avec T=0.60, aucun jeu de seuils ne satisfait GNG-1>=85% ET GNG-3>=80% simultanement. Trade-off irreconciliable.

### 8c. Contre-test H3 (Action 2, 2026-08-02)

Temperature forcee a T=1.0 (calibration desactivee), seuils inchanges (0.85/0.50/0.00).

| Metrique | T=0.60 (calibre) | T=1.0 (neutre) | Delta |
|---|---|---|---|
| GNG-1 metier | 81.0% | **77.0%** | -4.0 |
| GNG-2 conseiller | 87.2% | 87.2% | 0 |
| GNG-3 hors-scope | 72.0% | **81.0%** | **+9.0** |
| Pieges | 9/15 | 8/15 | -1 |

**H3 CONFIRMEE.** La regression GNG-3 est entierement mecanique : desactiver la calibration restaure GNG-3 a 81%. Cause racine : T=0.60 pousse les scores hors-perimetre au-dessus de seuil_bas=0.50, empechant le rejet.
**Artefacts** : `eval/recette-integrale/2026-08-01-v1.3.4-resweep/`, `eval/recette-integrale/2026-08-01-v1.3.4-H3/`

### 8d. Lot E2 — Mesure OOD rejection (M0-M5, 2026-08-02)

Re-entrainement 8 classes (hors_perimetre exclu du train, utilise comme OOD validation).
OOD = rejet par distance cosinus au centroide le plus proche. Seuil calibre par F1 max.

**M1** : Entrainement 247 exemples, 26 OOD. CV accuracy=93.1%, T=0.60, seuil_ood=0.317, F1_ood=0.902.

**M2** : Mesure au seuil calibre (0.317, trop agressif) :

| Metrique | Baseline | OOD (0.317) | Delta |
|---|---|---|---|
| GNG-1 | 81.0% | 77.0% | -4.0 |
| GNG-2 | 87.2% | 80.0% | -7.2 |
| GNG-3 | 72.0% | **82.0%** | **+10.0** |
| Pieges | 9/15 | 8/15 | -1 |

**M3** : Sweep 4 axes (2120 points). seuil_ood domine les 3 autres seuils.

**Meilleur equilibre** (ood=0.40, haut=0.70, bas=0.55, ecart=0.00) :

| Metrique | Baseline | OOD best | Delta |
|---|---|---|---|
| GNG-1 | 81.0% | 81.0% | 0 |
| GNG-2 | 87.2% | 86.4% | -0.8 |
| GNG-3 | 72.0% | **77.0%** | **+5.0** |
| Pieges | 9/15 | **10/15** | **+1** |
| Hmean | 79.5% | **81.3%** | **+1.8** |

**M4** : Rejeu deterministe x2 — 0 differences (bit-exact).

**Conclusion** : OOD = amelioration nette (+5pts GNG-3, +1 piege) mais les 4 gates restent non satisfaites. Cause racine : corpus trop petit (145 exemples) + textes vagues proches d'aucun centroide. Axes : enrichir donnees, multi-centroides, fine-tuning contrastif.

**Rapport complet** : `eval/lot-e2/RAPPORT_E2.md`

## 9. Points en attente (decision humaine)

| Item | Blocage | Statut |
|---|---|---|
| ~~Re-sweep avec calibration active~~ | ~~Action 1~~ | **FAIT** — 9/594 faisables, GNG-1/GNG-3 irreconciliables (section 8b) |
| ~~Contre-test H3~~ | ~~Action 2~~ | **FAIT — H3 CONFIRMEE** — T=1.0 restaure GNG-3 a 81% (section 8c) |
| ~~V3-0 repli bloquant~~ | ~~Action 5~~ | **FAIT** — V3-1/2/3/4 SKIP si V3-0 FAIL (commit 3ea5a25) |
| ~~Calibration + seuils co-optimises~~ | ~~Decision humaine~~ | **DOCUMENTE (N5)** — voir section 9a ci-dessous |
| ~~LOT E2 — hors_perimetre en rejet OOD~~ | ~~Decision humaine~~ | **MESURE (M0-M5)** — Meilleur point: GNG-3 +5pts vs baseline, hmean +1.8pts. Trade-off structurel: 4 gates non satisfaites simultanement. Rapport: eval/lot-e2/RAPPORT_E2.md |
| ~~V3-7 iteration 2/2~~ | ~~Decision humaine~~ | **SUSPENSION RECOMMANDEE (V3-7)** — voir section 9b ci-dessous |
| ~~V0-1 fixtures pytest~~ | ~~Bug produit~~ | **FAIT** — fixtures 8 exemples, asyncio await, emitter close_db (N7) |
| ~~Runner reporting bugs~~ | ~~Outillage~~ | **FAIT** — verdicts uniques, manifest_hash propage, CE bypass conditionnel (N7) |
| Desktop version sync | Intentionnel | desktop/package.json (0.1.0) != pyproject.toml (1.3.4) |
| SMTP AlertManager | Config prod | Remplir SMTP_PASSWORD et adresses email |

### 9a. N5 — Decision calibration/seuils : options et recommandation

**Constat etabli** : la calibration (T=0.60) et les seuils de decision (seuil_haut/seuil_bas) sont **couples**. Mesurer un modele calibre avec des seuils choisis avant calibration n'est pas valide. La calibration deplace la distribution des scores ; les seuils sont definis sur cette distribution. Ils ne peuvent pas etre figes separement.

**Evidence** :
- Re-sweep 594 points (Action 1) : aucun jeu de seuils ne satisfait GNG-1>=85% ET GNG-3>=80% simultanement avec T=0.60.
- Contre-test H3 : T=1.0 restaure GNG-3=81% mais degrade GNG-1 a 77%.
- Identite pieges N3 : les 6 echecs sont identiques quelle que soit la temperature, confirmant un probleme de representation, pas de seuils.

**Options** :

| # | Option | GNG-1 | GNG-3 | Condition |
|---|---|---|---|---|
| A | **Desactiver calibration** (T=1.0, seuils 0.85/0.50) | 77% | 81% | Aucune — applicable immediatement |
| B | **Calibration + seuils re-sweepas** (T=0.60, seuils 0.98/0.75) | 73% | 81% | Aucune — applicable immediatement |
| C | **Lot E2 — OOD rejection** (supprimer la classe hors_perimetre apprise, utiliser un score OOD) | cible >=85% | cible >=84% | Necessite implementation E2, re-entrainement, nouvelle campagne |
| D | **Re-entrainement avec co-optimisation** (sweep post-calibration integre dans le pipeline training) | inconnu | inconnu | Necessite nouvelles donnees ou augmentation |

**Recommandation** : poursuivre avec **option C (Lot E2)**. Les options A et B ne satisfont aucune des deux gates simultanement. L'option D n'ameliore pas la situation sans donnees supplementaires ou un changement d'architecture. Le lot E2 est deja specifie (`SPEC_LOT_E2_HORS_PERIMETRE_OOD_LOKO.md`) et attaque la cause racine : la classe `hors_perimetre` apprise entre en competition avec les classes metier dans l'espace de probabilites, rendant le couplage calibration/seuils insoluble.

**En attendant E2** : maintenir la calibration active (T=0.60) et les seuils actuels (0.85/0.50). La campagne v1.3.4 reste non-opposable. La prochaine campagne opposable sera post-E2.

### 9b. V3-7 — Suspension iteration 2/2

**Contexte** : V3-7 prevoit une deuxieme iteration de la campagne pour confirmer les resultats. L'iteration 1/2 (campagne diagnostic v1.3.4) a ete executee en mode diagnostic.

**Recommandation : suspendre V3-7 iteration 2/2.** Justification :
1. Le contre-test H3 a demontre que la baseline v1.3.3 est un artefact (seuils pre-calibration appliques a un modele non calibre).
2. Re-executer la campagne avec les memes seuils reproduirait les memes resultats — aucune information nouvelle.
3. Le lot E2 (OOD rejection) modifiera l'architecture du rejet et rendra les comparaisons v1.3.3/v1.3.4 obsoletes.
4. La prochaine campagne opposable doit etre post-E2, avec seuils co-optimises.

**Statut** : suspension en attente de validation humaine. Reprendre V3-7 iter 2/2 uniquement si E2 est abandonne et qu'une campagne avec seuils re-sweepas (option B) est souhaitee.

## 10. Historique des lots

| Lot | Date | Statut | Commit |
|---|---|---|---|
| LOT 0.1 — Basic-auth Caddy | 2026-08-01 | FAIT | Config serveur (hors repo) |
| LOT 0.2 — Inventaire donnees | 2026-08-01 | FAIT | eval/mission-obs/01_LOT0_INVENTAIRE.md |
| LOT 0.3 — Rotation secrets | 2026-08-01 | N/A | Pas de donnees tierces trouvees |
| LOT A1 — Temperature manifest | 2026-08-01 | FAIT | loko/bot/classifier/loader.py |
| LOT A2 — Calibration training | 2026-08-01 | FAIT | loko/bot/classifier/training.py, manifest.py |
| LOT A3 — Parite eval/runtime | 2026-08-01 | FAIT | loko/eval/cli.py |
| LOT A4 — Mesure calibration | 2026-08-01 | FAIT | Campagne diagnostic v1.3.4, T=0.60 active |
| LOT B1 — adversarial.csv | 2026-08-01 | FAIT | eval/datasets/adversarial.csv (55 cas) |
| LOT B2 — Documents canari | 2026-08-01 | FAIT | eval/canary-documents/ (5 docs) |
| LOT B3 — CI guard adversarial | 2026-08-01 | FAIT | tools/make_datasets.py, HASHES.sha256 |
| LOT C — Audit completude | 2026-08-01 | FAIT | STATUS.md (ce fichier) |
| LOT D — Campagne diagnostic | 2026-08-01 | FAIT | eval/recette-integrale/2026-08-01-v1.3.4/ |
| LOT E2 — OOD rejection | 2026-08-02 | MESURE (M0-M5) | ood.py, training, loader, eval. Best: ood=0.40 GNG-3+5pts hmean+1.8pts. 27 tests PASS. Rapport eval/lot-e2/RAPPORT_E2.md |
| LOT F2 — STATUS.md | 2026-08-01 | FAIT | STATUS.md (ce fichier) |
| Action 1 — Re-sweep post-calibration | 2026-08-02 | FAIT | ECART_MIN=0.00, grille 594pts, 9 faisables |
| Action 2 — Contre-test H3 | 2026-08-02 | FAIT | H3 confirmee, T=1.0 restaure GNG-3=81% |
| Action 5 — V3-0 bloquant | 2026-08-02 | FAIT | run_campaign.py: V3-1/2/3/4 SKIP si V3-0 FAIL |
| N2 — ECART_MIN configurable | 2026-08-02 | FAIT | --ecart-min CLI (defaut 0.05), runner.py parametrise |
| N3 — Identite pieges v1.3.3/v1.3.4 | 2026-08-02 | FAIT | 6/6 identiques, rapport eval/diagnostic-calibration/ |
| N6 — Machine reference CE-10 | 2026-08-02 | FAIT | exec_ce10() CPU/RAM/OS/Docker, artifact JSON |
| N7 — Corrections V0-1 + reporting | 2026-08-02 | FAIT | fixtures 8ex, asyncio await, verdicts uniques, manifest propage |
| N9 — Harnais adversarial | 2026-08-02 | FAIT | test_adversarial_harness.py: GF-A1/A2/A3/A5 mesures |
| N10 — Preuve backup/restore | 2026-08-02 | FAIT | test_backup_restore.py: 5 tests cycle complet |
| N11 — C-V1/C-V2/C-V3 | 2026-08-02 | FAIT | Tests existants OK — fuite streaming, SSRF, rotation |
| N5 — Decision calibration/seuils | 2026-08-02 | DOCUMENTE | Options A-D formalisees, recommandation E2 (section 9a) |
| N8 — Coherence version/tag | 2026-08-02 | FAIT | __init__.py fallback=1.3.4, openapi_w2.json=1.3.4, pip install -e . |
| V3-7 — Suspension iter 2/2 | 2026-08-02 | RECOMMANDE | Suspension formalisee (section 9b) |
