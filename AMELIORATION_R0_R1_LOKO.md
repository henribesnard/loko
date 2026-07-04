# 🔧 LOKO — Amélioration du code pour les phases R0+R1 & campagne de test ciblée

> **Version** : 1.0 — 4 juillet 2026
> **Objet** : instructions d'implémentation pour débloquer les phases **R0 (intégrité anti-mock)** et **R1 (entraînement réel + évaluation statistique)** du `PROTOCOLE_RECETTE_PRODUIT_LOKO_V2.md`, puis campagne de test courte validant exclusivement ces deux phases.
> **Entrées factuelles** : `RAPPORT_RECETTE_PRODUIT_LOKO_V2.md` (NO-GO du 4 juillet, version `v0.2.1`, commit `7969e365`), `AUDIT_REMEDIATION_LOKO_BOT.md`, `PLAN_REMEDIATION_V2_LOKO_BOT.md`.
> **Destinataire** : Claude Code. Règle d'exécution : un commit atomique + tests par item, aucun test existant ne régresse, fail-closed par défaut, déterminisme structurel préservé.

⚠️ **Collision de nommage** : le plan de remédiation v2 utilise des identifiants R1–R6 pour ses *items* ; le protocole de recette utilise R0–R9 pour ses *phases*. Dans ce document, « R0/R1 » désignent **les phases du protocole** ; les items de code sont identifiés **A-x, B-x, C-x**. L'item R2-a du plan v2 (image Docker ML) est **détaillé et remplacé** par le lot A ci-dessous ; les items R1, R3, R4, R5, R6 du plan v2 (rate limiting, SSRF, locks, timeout, crawler) restent valables mais **hors périmètre de ce lot** — ils conditionnent les phases R2+ du protocole, pas R0/R1.

---

## 0. État réel constaté → correspondance des correctifs

Chaque anomalie ci-dessous est un constat vérifié du rapport NO-GO, avec le fichier/mécanisme réellement en cause :

| # | Constat vérifié dans le code | Cause racine | Item |
|---|---|---|---|
| 1 | `import setfit` échoue in-container : `ImportError: cannot import name 'default_logdir' from transformers.training_args` | `setfit==1.1.3` incompatible `transformers==5.13.0` (symbole supprimé en transformers 5.x) ; versions non épinglées | **A1** |
| 2 | Chargement du modèle en `--network none` échoue : HEAD vers Hugging Face malgré le cache `/app/.hf_cache` | Chargement par identifiant de modèle (résolution hub, lookup `adapter_config.json` PEFT) au lieu d'un chemin local + variables offline absentes | **A2** |
| 3 | `_load_classifier(..., allow_mock=False)` retourne quand même `_MockClassifier()` si modèle absent ou SetFit inimportable | Fallback silencieux codé en dur ; aucun garde d'environnement sur les 4 mocks | **A3** |
| 4 | `/publish` accepte un `models/level1/config.json` **factice** ; runtime continue de servir après suppression du modèle | Validation = simple test d'existence de fichier ; aucun contrôle d'intégrité ni au publish ni au chargement | **A4**, **A5** |
| 5 | Suite complète : `252 passed, 3 failed` — les 3 tests SetFit `slow` échouent dans l'image | Conséquence de #1 ; tests `slow` absents de la CI | **A1**, **A6** |
| 6 | Entraînement API bloqué en `l1_training` ; aucune matrice finale exportée | Conséquence de #1 ; vérifications B à faire une fois débloqué | **B1–B3** |
| 7 | `train.csv`, `heldout_*.csv`, `pieges_T01-T15.csv` absents du dépôt | Prérequis E5 jamais livré | **C1** |
| 8 | `loko-eval` absent du dépôt | Prérequis E6 jamais livré | **C2** |

Hors périmètre R0/R1 (traités par le plan v2 en parallèle, non bloquants pour cette campagne) : provider LLM réel (`MockLLMProvider` instancié dans `bot_public.py` — le lot A le rend *impossible hors test*, l'implémentation réelle relève de la phase R2), crawler Playwright, traces non persistées, timer d'inactivité, rate limiting 429, audit npm.

---

## 1. Lot A — Environnement d'exécution & anti-mock (débloque R0)

### A1 — Épingler une matrice de versions ML compatible et la verrouiller

**Constat** : `pyproject.toml` déclare les extras `[ml]` sans borne supérieure sur `transformers` ; pip a résolu `transformers 5.13.0`, incompatible avec `setfit 1.1.3` qui importe `default_logdir` (supprimé en 5.x).

**Actions** :
1. Dans `pyproject.toml`, extras `[ml]` : borner explicitement — `setfit>=1.1.3,<1.2`, `transformers>=4.45,<5`, `sentence-transformers>=3.0,<4`, `torch>=2.4` (installé séparément en CPU-only, voir A6). La matrice exacte est **validée par le test d'import et le test d'entraînement canari** (A6), pas par supposition : si une combinaison plus récente passe ces tests, elle est admissible.
2. Ajouter `constraints-ml.txt` généré par `pip freeze` de l'environnement validé, référencé par le Dockerfile (`pip install -c constraints-ml.txt`) : le build devient reproductible, une résolution pip future ne peut plus casser silencieusement l'image.
3. Test unitaire permanent `tests/bot/test_ml_env.py::test_setfit_importable` : `import setfit`, `import sentence_transformers`, vérifie `torch.cuda.is_available() is False` en image CPU. Marqué non-slow : il doit tourner à **chaque** CI.

**Critère d'acceptation** : `docker run --rm loko:latest python -c "import setfit, sentence_transformers"` → code retour 0 ; suite complète `255 passed, 0 failed` in-container.

### A2 — Modèle de base réellement offline

**Constat** : le cache `/app/.hf_cache` existe mais le chargement passe par l'identifiant hub (`paraphrase-multilingual-MiniLM-L12-v2`), ce qui déclenche une résolution réseau (HEAD sur le repo + lookup `adapter_config.json`) même cache présent.

**Actions** :
1. Au build de l'image : stage dédié qui exécute `huggingface_hub.snapshot_download("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", local_dir="/app/models/base/minilm")` — le modèle vit dans l'image à un **chemin local figé**, plus dans un cache résolu dynamiquement.
2. Dans `model_store.py` / `setfit_service.py` : le modèle de base est chargé **par chemin** (`/app/models/base/minilm`, surchargé par `LOKO_BASE_MODEL_PATH`), jamais par identifiant hub quand le chemin existe.
3. Fixer dans l'image : `HF_HUB_OFFLINE=1` et `TRANSFORMERS_OFFLINE=1`. Tout accès hub résiduel devient une erreur franche au lieu d'un blocage réseau intermittent — cohérent fail-closed.
4. Même traitement pour le modèle embarqué `demande_conseiller` (spec dev §7) : vérifier qu'il est copié dans l'image et chargé par chemin.

**Critère d'acceptation** : `docker run --network none` → démarrage, entraînement complet des 9 intentions, inférence — zéro tentative réseau (vérifiable par l'absence d'erreur avec `HF_HUB_OFFLINE=1`).

### A3 — Supprimer le fallback mock et poser les gardes d'instanciation (GNG-10)

**Constat** : `_load_classifier(..., allow_mock=False)` contient encore une branche retournant `_MockClassifier()` si le répertoire modèle est absent ou l'import SetFit impossible — le paramètre `allow_mock` ment.

**Actions** :
1. Créer `loko/bot/errors.py` : `ComponentUnavailableError(component, bot_id, reason)`.
2. `_load_classifier` : supprimer **toute** branche de fallback. Modèle absent/corrompu ou SetFit inimportable → lever `ComponentUnavailableError("classifier_l1", ...)`. Le paramètre `allow_mock` disparaît de la signature (les tests injectent leurs mocks par le protocole d'injection de l'orchestrateur, pas par ce chemin).
3. Garde d'instanciation sur les 4 mocks (`_MockClassifier`, `MockLLMProvider`, `InMemorySearchBackend`, `MockEscalationProvider`) — dans `__init__` :
   ```python
   if os.environ.get("RAGKIT_ENV") != "test":
       raise RuntimeError(f"{type(self).__name__} interdit hors RAGKIT_ENV=test (GNG-10)")
   ```
   Exception unique et assumée : `MockEscalationProvider` reste instanciable si `LOKO_ESCALATION_PROVIDER=mock` est **explicitement** posé (il simule le SI client, admis par le protocole R4) — mais jamais par défaut silencieux.
4. `conftest.py` des suites de tests pose `RAGKIT_ENV=test` ; vérifier qu'aucun code de production ne le pose.

**Critères d'acceptation** : test paramétré sur les 4 classes — instanciation avec `RAGKIT_ENV=""` → `RuntimeError` ; `_load_classifier` sur répertoire vide → `ComponentUnavailableError` ; grep CI garantissant qu'aucun module hors `tests/` n'importe les mocks (test de lint dédié).

### A4 — Intégrité du modèle : manifeste signé à l'entraînement, vérifié à la publication

**Constat** : `/publish` vérifie la seule existence de `models/level1/config.json` ; un JSON factice publie un bot sans modèle.

**Actions** :
1. En fin d'entraînement réussi, `setfit_service` écrit `models/manifest.json` :
   ```json
   {
     "schema": 1, "created_at": "...", "base_model": "minilm@sha256:...",
     "levels": {"level1": {"files": {"model.safetensors": "sha256:...", "...": "..."},
                 "labels": ["services_en_ligne", "..."], "n_train_examples": 119},
                "level2_services_en_ligne": {"files": {...}, "labels": [...]}},
     "dataset_hash": "sha256 du jeu d'exemples au moment du train",
     "train_metrics": {...}, "inference_latency_ms": {"p50": 0, "p95": 0}
   }
   ```
2. Fonction `verify_model(bot_id) -> ModelVerification` dans `model_store.py` : (a) manifeste présent et schéma valide ; (b) hash SHA-256 de chaque fichier conforme ; (c) **chargement effectif** du modèle ; (d) inférence fumigène sur 3 verbatims canaris embarqués (un par famille : métier, conseiller, hors-scope) avec labels attendus — pas d'exigence de score, seulement que la prédiction s'exécute et retourne une des classes du manifeste.
3. `POST /publish` appelle `verify_model` : échec → 422 avec le détail (`manifest_missing`, `hash_mismatch`, `load_error`, `smoke_failed`). Le contournement par fichier factice devient impossible : il faudrait forger un modèle chargeable et cohérent avec les hashes.
4. Le `dataset_hash` du manifeste est comparé au hash courant des exemples à la publication : s'ils divergent (exemples modifiés après le dernier train), publication refusée avec « ré-entraînement requis » — ferme au passage un trou de cohérence exemples/modèle.

**Critères d'acceptation** : publish avec `config.json` factice → 422 `manifest_missing` ; corruption d'un octet de `model.safetensors` → 422 `hash_mismatch` ; modification d'un exemple après train sans retrain → 422.

### A5 — Fail-fast du runtime sur modèle indisponible

**Constat** : après suppression du répertoire modèle d'un bot publié, le runtime crée des sessions et répond (fallback `hors_perimetre`).

**Actions** :
1. `_get_orchestrator` (construction + cache) appelle `verify_model` avant toute instanciation de classifieur. `ComponentUnavailableError` → l'orchestrateur n'est **pas** construit ni mis en cache.
2. Endpoints runtime (`POST /sessions`, `POST /messages`) : capturer `ComponentUnavailableError` → **503** `{"error": "bot_unavailable", "detail": "classifier_l1 indisponible"}` — sans révéler de chemin disque. Aucune session créée, rien de persisté.
3. Au démarrage du serveur : boucle sur les bots `published`, `verify_model` sur chacun, log `CRITICAL` par bot défaillant (le serveur démarre — les autres bots servent — mais le bot cassé est fermé, pas dégradé).
4. L'invalidation de cache existante (update/publish) reste ; ajouter l'invalidation sur échec de `verify_model` pour éviter de servir un orchestrateur construit avant corruption.

**Critères d'acceptation** : publier un bot valide, supprimer `models/level1/`, redémarrer → `POST /sessions` → 503 explicite, 0 session en base ; le test du rapport NO-GO (« modèle supprimé → runtime sert en fallback ») passe désormais en refus.

### A6 — Image Docker et CI

1. Dockerfile multi-stage : `pip install torch --index-url https://download.pytorch.org/whl/cpu` **puis** `pip install -e ".[server,ml]" -c constraints-ml.txt` ; stage modèle (A2) ; cible ~1,2–1,5 Go. `LOKO_ML=on` par défaut ; `off` → `/train` répond 503 explicite (jamais un `ModuleNotFoundError` en cours de job).
2. CI : job standard = suite complète **dans l'image** (et non sur l'hôte Windows, source d'écarts constatée entre campagnes) ; les 3 tests ML `slow` sortent du skip et tournent dans un job `nightly` + sur tag de release. Ajouter un job `offline` : `docker run --network none` + entraînement canari 2 intentions × 8 exemples.
3. `npm audit` : corriger la vulnérabilité critique et la haute (mise à jour des paquets concernés) ; le build échoue si `npm audit --audit-level=high` retourne des findings — c'était un FAIL du rapport, à petit coût.

---

## 2. Lot B — Chaîne d'entraînement et d'inférence (débloque R1.a)

Ces items sont des **vérifications-corrections** : le code existe (`setfit_service.py`, job async, endpoints train/status) mais n'a jamais tourné en réel in-container — tout écart découvert est corrigé dans ce lot.

### B1 — Entraînement réel in-container
Vérifier une fois A1/A2 livrés : job L1 (9 classes, 119+ exemples du postulat) < 2 min CPU, progression restituée par `GET /train/status`, écriture du manifeste (A4). Vérifier le nettoyage en cas d'échec à mi-parcours (pas de répertoire modèle partiel sans manifeste — le manifeste écrit en dernier sert de commit atomique).

### B2 — Matrice de confusion et conseils
Vérifier que l'endpoint d'évaluation retourne la matrice L1 (validation croisée ou hold-out interne sur les exemples), exportable (JSON + CSV — **artefact exigé par la Règle 3 du protocole**). Vérifier le conseil actionnable sur paire confondue (`cotisations`↔`changement_coordonnees` attendue avec les exemples du postulat). Si l'export fichier n'existe pas : l'ajouter (`GET /api/bot/{id}/train/report` → JSON complet ; le front sait déjà l'afficher).

### B3 — Latence d'inférence instrumentée
À la fin du train, mesurer 100 inférences L1 + L2 in-container, écrire P50/P95 dans le manifeste (champ prévu en A4). Exposer dans `train/report`. Budget : P95 ≤ 50 ms CPU. Si dépassement : c'est un résultat de campagne (FAIL R1.5), pas un ajustement silencieux.

### B4 — Modèle `demande_conseiller` embarqué
Vérifier sa présence dans l'image, son chargement par chemin (A2), et son intégration dans la décision (sortie transverse). S'il s'avère absent du dépôt (le rapport ne l'a pas testé) : l'entraîner une fois sur les verbatims génériques prévus par la spec, le versionner comme asset de l'image avec son propre manifeste.

---

## 3. Lot C — Outillage d'évaluation statistique (débloque R1.b)

### C1 — Datasets figés (prérequis E5)

1. Script `tools/make_datasets.py`, entrée `dataset.csv` (6 062 verbatims MGEN), sorties dans `eval/datasets/` :
   - `train.csv` — exactement les exemples du postulat §2 (7 intentions + hors_périmètre + sous-motifs), colonnes `text,intent,sub_intent` ;
   - `heldout_metier.csv` — 100 verbatims des 7 intentions retenues, tirés du dataset, **disjoints de train.csv** (vérification d'intersection vide programmée), stratifiés proportionnellement ;
   - `heldout_conseiller.csv` — les 126 verbatims `parler_conseiller` ;
   - `heldout_horsscope.csv` — 100 verbatims stratifiés sur les 32 intentions non retenues ;
   - `pieges.csv` — les 15 cas T01–T15 avec colonne `expected_behavior` (`route:intent`, `clarify_intra:intent`, `clarify_inter:i1|i2`, `reject`, `escalate:motif`).
2. Tirage **déterministe** (`seed=42` consigné) ; le script écrit `eval/datasets/HASHES.sha256`. Les CSV et le fichier de hashes sont **committés** : le protocole exige des jeux figés, pas régénérables à la volée pendant la campagne.
3. Test CI : intersection train/held-out vide ; comptes exacts (100/126/100/15) ; hashes conformes.

### C2 — CLI `loko-eval` (prérequis E6)

Entrée console `loko-eval` (`pyproject.toml [project.scripts]`), module `loko/eval/`.

```
loko-eval --bot-dir ~/.loko/bots/{id} --dataset eval/datasets/heldout_metier.csv \
          --mode decision --out eval/reports/metier/ [--threshold-check gng1:0.85]
```

1. **Deux modes** :
   - `raw` : accuracy argmax du classifieur seul (diagnostic) ;
   - `decision` (mode du GO) : rejoue la **couche de décision réelle** — charge `seuil_haut`, `seuil_bas`, `seuil_sous_motif` depuis la config du bot et applique la même logique que l'orchestrateur (route directe / clarification inter si top-2 proches / rejet). Impératif d'implémentation : **importer la fonction de décision de l'orchestrateur** (l'extraire en fonction pure `decide(scores, config) -> Decision` si elle est aujourd'hui inline) — pas de réimplémentation parallèle qui divergerait.
2. **Métrique GNG-1** conforme au protocole : succès = intention vraie routée directement **ou** présente dans les candidats de clarification. GNG-2 : décision `transverse:demande_conseiller`. GNG-3 : décision `reject` ou `escalate` — et comptage explicite des « réponses à côté » (route directe vers une intention métier = échec aggravé, reporté séparément).
3. **Sorties** (artefacts Règle 3) : `report.json` (métriques globales + par classe P/R/F1, verdicts GNG avec seuils, config et hashes des datasets utilisés, version du modèle via manifeste), `confusion.csv`, `errors.csv` (`text,true,predicted,decision,score_top1,score_top2`).
4. **Code retour** : 0 si tous les `--threshold-check` passent, 1 sinon → utilisable en **gate CI**.
5. Mode `pieges` : lit `expected_behavior` et produit un verdict cas par cas avec commentaire obligatoire par écart.

### C3 — Calibration des seuils
`loko-eval` accepte `--sweep seuil_haut=0.6:0.9:0.05,seuil_bas=0.3:0.6:0.05` : produit la grille précision/taux de clarification. Règle du protocole R1.10 rappelée dans la sortie : si les seuils changent, **re-run complet des 4 jeux** avec seuils figés dans la config versionnée avant tout verdict.

---

## 4. Campagne de test R0+R1 (courte, ciblée)

**Conditions d'entrée** : lots A, B, C livrés et mergés ; tag `v0.3.0` ; image construite, digest consigné ; `HASHES.sha256` vérifié ; **aucun commit pendant la campagne**. Toutes les exécutions **in-container**.

### Volet R0 — Intégrité (tous éliminatoires sauf CA-05/06)

| ID | Test | Attendu | Preuve |
|---|---|---|---|
| CA-01 | Instanciation des 4 mocks avec `RAGKIT_ENV` vide | `RuntimeError` ×4 ; variante `MockEscalationProvider` + `LOKO_ESCALATION_PROVIDER=mock` explicite → OK | Sortie pytest |
| CA-02 | Publier bot valide → supprimer `models/level1/` → redémarrer conteneur | `POST /sessions` → **503** explicite, 0 session créée, log CRITICAL au boot | Transcript HTTP + logs |
| CA-03 | `/publish` avec `config.json` factice ; puis avec modèle corrompu (1 octet) ; puis exemple modifié sans retrain | 422 `manifest_missing` / `hash_mismatch` / `retrain_required` | Réponses HTTP |
| CA-04 | `docker run --network none` : démarrage + entraînement canari + inférence | Succès sans accès réseau | Log du job |
| CA-05 | Suite complète in-container, **3 tests `slow` inclus** | `255 passed, 0 failed, 0 skipped` (ML) | Rapport pytest |
| CA-06 | `npm audit --audit-level=high` | 0 finding high/critical | Sortie audit |

### Volet R1.a — Entraînement

| ID | Test | Attendu | Preuve |
|---|---|---|---|
| CA-10 | Train L1 9 classes (train.csv) via API | < 2 min CPU, progression, manifeste écrit | `train/report` + manifest |
| CA-11 | Train L2 `services_en_ligne` (5 sous-motifs) | Discrimination limitée aux 5 classes | `train/report` |
| CA-12 | Matrice de confusion exportée | Paire `cotisations`↔`changement_coordonnees` visible + conseil | `confusion.csv` |
| CA-13 | Cycle amélioration : +3 exemples discriminants/côté, retrain | Amélioration mesurée sur la paire | 2 matrices comparées |
| CA-14 | Latence 100 inférences L1+L2 in-container | **P95 ≤ 50 ms** | Champ manifeste + rapport |

### Volet R1.b — Évaluation statistique (les chiffres du GO)

| ID | Commande | Seuil | Critère |
|---|---|---|---|
| CA-20 | `loko-eval --dataset heldout_metier.csv --mode decision` | **≥ 85 %** (route correcte ou clarification pertinente) | GNG-1 |
| CA-21 | `loko-eval --dataset heldout_conseiller.csv` | **≥ 90 %** transverse détecté | GNG-2 |
| CA-22 | `loko-eval --dataset heldout_horsscope.csv` | **≥ 80 %** rejet/escalade, **0 route directe métier non signalée** | GNG-3 |
| CA-23 | `loko-eval --dataset pieges.csv --mode pieges` | ≥ 12/15, chaque écart commenté | R1.9 |
| CA-24 | Si seuils ajustés (`--sweep`) : re-run CA-20→23 avec seuils figés | Mêmes seuils de succès | R1.10 |
| CA-25 | Rejouer CA-20 deux fois, même image, même modèle | `report.json` **identiques** (hors horodatage) | Avant-goût GNG-4 |

### Porte de sortie de campagne

**PASS campagne R0+R1** = CA-01→04 verts (éliminatoires), CA-05/06 verts, CA-10→14 verts, CA-20→22 aux seuils, CA-23 ≥ 12/15 commenté, CA-25 identique — chaque ligne avec son artefact archivé (`eval/reports/` + logs, joints au rapport).

- **Si FAIL sur CA-20→22** : ce n'est pas un bug logiciel mais un résultat ML — actions correctives légitimes : enrichissement des exemples (postulat §2 amendé), calibration (CA-24), scission de sous-motifs. Chaque itération = retrain + re-run **complet** du volet R1.b, datasets inchangés.
- **Si PASS** : les phases R2–R9 du protocole deviennent exécutables ; la suite immédiate est le plan v2 items R6 (crawler) et R2-b (knowledge branchée) pour ouvrir R2, puis le provider LLM réel pour R3. Ne pas relancer une recette intégrale avant : c'est la leçon des trois campagnes.

---

## 5. Definition of done du lot

1. Tous les critères d'acceptation A1–A6, B1–B4, C1–C3 verts en CI (jobs standard + nightly + offline).
2. Campagne R0+R1 exécutée sur tag figé, rapport avec artefacts joints, verdict par ligne — une ligne non exécutée vaut FAIL (Règle 3 du protocole).
3. README + `docker-compose.yml` documentent : `LOKO_ML`, `LOKO_BASE_MODEL_PATH`, `HF_HUB_OFFLINE`, `RAGKIT_ENV`, `LOKO_ESCALATION_PROVIDER`, la matrice de versions ML et la procédure `loko-eval`.
4. GNG-10 démontrable : la phrase « un mock qui répond ressemble à un bot vivant » ne peut plus se produire par construction — c'est l'acquis principal attendu de ce lot.
