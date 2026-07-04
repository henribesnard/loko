# ✅ LOKO — Protocole de validation R0+R1 (post-lot d'amélioration)

> **Version** : 1.0 — 4 juillet 2026
> **Objet** : protocole d'exécution complet et détaillé de la campagne courte validant les phases **R0 (intégrité anti-mock)** et **R1 (entraînement réel + évaluation statistique)** du protocole de recette v2, immédiatement après livraison du lot d'amélioration `AMELIORATION_R0_R1_LOKO.md` (lots A, B, C).
> **Références** : `PROTOCOLE_RECETTE_PRODUIT_LOKO_V2.md` (règles et critères GNG), `AMELIORATION_R0_R1_LOKO.md` (items A1–A6, B1–B4, C1–C3), `POSTULAT_TEST_E2E_LOKO.md` §2 (config MGEN).
> **Ce que cette campagne décide** : l'ouverture des phases R2–R9. Elle ne décide **pas** le GO produit.

---

## 0. Règles d'exécution (héritées du protocole v2, rappel opposable)

1. **Aucun mock** dans les tests de cette campagne, à l'exception explicite de `MockEscalationProvider` activé par `LOKO_ESCALATION_PROVIDER=mock` (hors périmètre R0/R1 de toute façon). Tout test qui poserait `RAGKIT_ENV=test` hors des suites pytest est invalide.
2. **Toute exécution est in-container.** Les mesures faites depuis l'hôte (latence, imports, entraînement) sont irrecevables — écart constaté entre les campagnes précédentes (hôte Windows vs image).
3. **Chaque test produit son artefact**, archivé dans `eval/campagne-R0R1/{date}/`. Une ligne du plan non exécutée = FAIL, pas absente du rapport.
4. **Version figée** : tag posé avant le premier test, digest d'image consigné, aucun commit jusqu'au verdict. Toute correction en cours de campagne → nouveau tag → **la campagne repart du test V0-1**.
5. Un test FAIL n'interrompt pas la campagne (on collecte tout), **sauf** les éliminatoires V1-1 à V1-4 : leur échec invalide mécaniquement le volet statistique (un modèle dont l'intégrité n'est pas garantie ne produit pas de chiffres opposables).

---

## 1. Conditions d'entrée (checklist bloquante avant V0)

| # | Condition | Vérification | ✔ |
|---|---|---|---|
| CE-1 | Lots A, B, C mergés sur `main`, CI verte (jobs standard + nightly + offline) | Lien vers les runs CI | ☐ |
| CE-2 | Tag posé (ex. `v0.3.0`), commit consigné | `git describe --tags` | ☐ |
| CE-3 | Image construite depuis le tag, digest consigné | `docker inspect --format='{{index .RepoDigests 0}}' loko:v0.3.0` | ☐ |
| CE-4 | Datasets figés présents et conformes | `sha256sum -c eval/datasets/HASHES.sha256` → 5 fichiers OK (`train.csv`, `heldout_metier.csv` = 100 lignes, `heldout_conseiller.csv` = 126, `heldout_horsscope.csv` = 100, `pieges.csv` = 15) | ☐ |
| CE-5 | Intersection train/held-out vide | `python tools/make_datasets.py --check` → exit 0 | ☐ |
| CE-6 | `loko-eval` installé dans l'image | `docker run --rm loko:v0.3.0 loko-eval --version` | ☐ |
| CE-7 | Répertoire d'artefacts créé, gabarit de rapport (annexe A) copié | `eval/campagne-R0R1/2026-07-XX/` | ☐ |

Toute case non cochée : la campagne ne démarre pas.

---

## 2. Préparation de l'environnement d'exécution

```bash
# Conteneur de campagne : volume de données dédié, vierge
docker volume create loko-r0r1
docker run -d --name loko-campagne \
  -e LOKO_ADMIN_TOKEN=$(openssl rand -hex 24) \
  -e RAGKIT_MODE=server \
  -v loko-r0r1:/data -e LOKO_DATA_DIR=/data \
  -p 127.0.0.1:18001:8000 loko:v0.3.0
curl -fsS http://127.0.0.1:18001/health
```

Consigner dans le rapport : digest image, variables d'environnement effectives (`docker exec loko-campagne env | grep -E 'LOKO|RAGKIT|HF_'`), version Python et versions ML (`pip freeze | grep -E 'setfit|transformers|sentence|torch'`). Attendu conforme à `constraints-ml.txt` — tout écart est un FAIL de CE-3.

Création du bot de campagne : POST de la configuration MGEN complète du postulat §2 (7 intentions métier + `hors_périmètre` + 5 sous-motifs de `services_en_ligne`), directement depuis `train.csv` via le script `tools/load_postulat.py` (ou l'API admin). Vérifier : 9 intentions, chaque intention ≥ 8 exemples, statut `draft`.

---

## 3. Volet V0 — Recevabilité technique de l'image

| ID | Procédure | Attendu | Artefact |
|---|---|---|---|
| V0-1 | Suite complète in-container : `docker exec loko-campagne pytest -m "" --tb=short -q` (les marqueurs `slow` **inclus**) | `255+ passed, 0 failed, 0 skipped` sur les tests ML | `V0-1_pytest.txt` |
| V0-2 | Imports ML : `python -c "import setfit, sentence_transformers, torch; print(torch.__version__, torch.cuda.is_available())"` | Import OK, version CPU (`+cpu`), CUDA `False` | `V0-2_imports.txt` |
| V0-3 | Lint anti-mock : job CI dédié (grep) — aucun module hors `tests/` n'importe `_MockClassifier`, `MockLLMProvider`, `InMemorySearchBackend`, `MockEscalationProvider` | 0 occurrence | Log CI |
| V0-4 | Audit front : `npm audit --audit-level=high` | 0 finding high/critical | `V0-4_audit.txt` |
| V0-5 | Taille d'image | ≤ 1,6 Go (cible 1,2–1,5) | `docker images` |

---

## 4. Volet V1 — Phase R0 : intégrité anti-mock (GNG-10) — éliminatoires

### V1-1 — Gardes d'instanciation des mocks
**Procédure** : exécuter le test paramétré `tests/bot/test_no_mock_guard.py` in-container, puis contre-épreuve manuelle hors pytest :
```bash
docker exec -e RAGKIT_ENV= loko-campagne python -c \
  "from loko.bot.classifier.mock import _MockClassifier; _MockClassifier()"
```
**Attendu** : `RuntimeError … interdit hors RAGKIT_ENV=test (GNG-10)` pour les 4 classes ; la variante `LOKO_ESCALATION_PROVIDER=mock` n'autorise **que** `MockEscalationProvider`.
**Artefact** : `V1-1_mock_guard.txt` (les 4 tracebacks + le cas autorisé).

### V1-2 — Plus de fallback dans `_load_classifier`
**Procédure** : sur un répertoire modèle vide puis sur un répertoire au manifeste corrompu :
```bash
docker exec loko-campagne python - <<'PY'
from loko.bot.classifier.loader import _load_classifier
_load_classifier(bot_id="bot-inexistant")
PY
```
**Attendu** : `ComponentUnavailableError("classifier_l1", …)` — jamais une instance. Vérifier par inspection (`git grep allow_mock`) que le paramètre a disparu de la signature.
**Artefact** : `V1-2_loader.txt`.

### V1-3 — Publication : intégrité du modèle (3 contournements testés)
**Procédure** — trois tentatives successives sur un bot jetable :
1. Créer `models/level1/config.json` factice à la main dans le volume, `POST /publish` ;
2. Entraîner réellement le bot, puis corrompre 1 octet de `model.safetensors` (`printf '\x00' | dd of=… bs=1 seek=100 conv=notrunc`), `POST /publish` ;
3. Restaurer le modèle, modifier un exemple d'entraînement via l'API admin **sans retrain**, `POST /publish`.
**Attendu** : 422 avec détail respectivement `manifest_missing`, `hash_mismatch`, `retrain_required`. Aucun des trois ne publie.
**Artefact** : `V1-3_publish_integrity.http` (les 3 requêtes/réponses complètes).

### V1-4 — Fail-fast runtime sur modèle supprimé (le test qui a fait tomber la v0.2.1)
**Procédure** : entraîner + publier le bot de campagne (avec clé API runtime générée) → vérifier qu'une session se crée (témoin positif) → `docker exec loko-campagne rm -rf /data/bots/{id}/models/level1` → `docker restart loko-campagne` → tenter `POST /sessions` puis `POST /messages` sur une session antérieure.
**Attendu** :
- au boot : log `CRITICAL` identifiant le bot défaillant, serveur démarré ;
- `POST /sessions` → **503** `{"error":"bot_unavailable"}`, sans chemin disque dans la réponse ;
- table sessions : **0 ligne nouvelle** (`sqlite3 /data/bots/{id}/sessions.db 'select count(*)…'` avant/après identiques) ;
- aucun message `hors_perimetre` généré nulle part.
**Artefact** : `V1-4_failfast.txt` (logs boot + transcripts HTTP + comptes SQLite).

### V1-5 — Fonctionnement hors réseau
**Procédure** : conteneur neuf `docker run --network none loko:v0.3.0` (volume vierge) → création bot 2 intentions × 8 exemples via exec local → entraînement → 3 inférences par appel direct du service.
**Attendu** : succès complet, zéro erreur réseau ; `HF_HUB_OFFLINE=1` et `TRANSFORMERS_OFFLINE=1` présents dans l'env.
**Artefact** : `V1-5_offline.txt`.

**Porte intermédiaire** : V1-1 → V1-4 tous PASS, sinon arrêt de campagne (règle 5).

---

## 5. Volet V2 — Phase R1.a : entraînement réel

### V2-1 — Entraînement L1 complet
**Procédure** : `POST /api/bot/{id}/train` sur le bot de campagne (9 classes, exemples de `train.csv`). Suivre `GET /train/status` toutes les 5 s.
**Attendu** : progression monotone restituée ; durée totale **< 2 min** CPU ; à l'issue, `models/manifest.json` présent et complet (schéma, hashes de tous les fichiers, labels = les 9 classes, `dataset_hash`, `train_metrics`, `inference_latency_ms` renseigné).
**Artefact** : `V2-1_train.json` (statuts horodatés + manifeste).

### V2-2 — Entraînement L2 `services_en_ligne`
**Attendu** : modèle `level2_services_en_ligne` au manifeste, labels = exactement les 5 sous-motifs.
**Artefact** : section dédiée du manifeste.

### V2-3 — Atomicité en cas d'échec
**Procédure** : lancer un train puis tuer le worker à mi-parcours (`docker exec … pkill -f train_job` ou arrêt du conteneur pendant `l1_training`).
**Attendu** : au redémarrage, pas de répertoire modèle partiel *avec* manifeste (le manifeste écrit en dernier fait office de commit) ; statut du job = `failed` explicite ; un nouveau train repart proprement.
**Artefact** : `V2-3_atomicity.txt`.

### V2-4 — Matrice de confusion et conseil
**Procédure** : `GET /api/bot/{id}/train/report` → export JSON + CSV.
**Attendu** : matrice 9×9 ; confusion non nulle attendue sur `cotisations`↔`changement_coordonnees` ; conseil actionnable affiché pour la paire la plus confondue.
**Artefact** : `V2-4_confusion.csv` + capture du conseil.

### V2-5 — Cycle d'amélioration mesuré
**Procédure** : ajouter 3 exemples discriminants de chaque côté de la paire (ex. « contestation du prélèvement de ma cotisation » / « je change d'agence bancaire ») via l'API admin, retrain, ré-exporter la matrice.
**Attendu** : réduction mesurable de la confusion sur la paire (valeur avant/après consignée) ; le `dataset_hash` du nouveau manifeste diffère de l'ancien.
**Artefact** : `V2-5_matrices_avant_apres.csv`.

### V2-6 — Latence d'inférence
**Procédure** : le champ `inference_latency_ms` du manifeste (100 inférences L1+L2 mesurées in-container à la fin du train) ; contre-mesure indépendante par script (100 appels, verbatims du held-out, chronométrage `perf_counter`).
**Attendu** : **P95 ≤ 50 ms** sur les deux mesures ; écart entre les deux < 30 %.
**Artefact** : `V2-6_latence.json` (P50/P95 des deux séries).

---

## 6. Volet V3 — Phase R1.b : évaluation statistique (les chiffres du GO)

Toutes les commandes s'exécutent in-container, sur le modèle issu de **V2-5** (post-cycle d'amélioration), seuils de la config du bot. `report.json` de chaque run embarque le hash du dataset et la référence du manifeste — c'est ce qui rend les chiffres opposables.

### V3-1 — GNG-1 : précision métier (mode décision)
```bash
loko-eval --bot-dir /data/bots/{id} --dataset eval/datasets/heldout_metier.csv \
          --mode decision --out eval/campagne-R0R1/{date}/metier/ --threshold-check gng1:0.85
```
**Attendu** : ≥ 85 % de succès (route directe correcte **ou** intention vraie présente dans les candidats de clarification), exit code 0.
**Analyse obligatoire** : lecture de `errors.csv` — chaque erreur classée (verbatim ambigu / manque d'exemples / seuil) dans le rapport.

### V3-2 — GNG-2 : détection `demande_conseiller`
```bash
loko-eval --dataset eval/datasets/heldout_conseiller.csv --threshold-check gng2:0.90 …
```
**Attendu** : ≥ 90 % des 126 verbatims → décision `transverse:demande_conseiller`.

### V3-3 — GNG-3 : rejet hors-scope
```bash
loko-eval --dataset eval/datasets/heldout_horsscope.csv --threshold-check gng3:0.80 …
```
**Attendu** : ≥ 80 % en `reject`/`escalate` ; le rapport isole les **routes directes vers une intention métier** (réponse à côté) — ce sous-compte est reporté même si le seuil global passe, c'est lui qui mesure le risque client réel.

### V3-4 — Les 15 pièges
```bash
loko-eval --dataset eval/datasets/pieges.csv --mode pieges …
```
**Attendu** : ≥ 12/15 conformes à `expected_behavior` ; **chaque écart commenté individuellement** dans le rapport (un écart non commenté vaut FAIL du test). Attention particulière à T04 (« RIB coordonnées bancaires » → clarification inter attendue), T06 (« attestation de paiement »), T14 (« Noemie » mot unique), T15 (cas piège IBAN/carte vitale).

### V3-5 — Calibration éventuelle (R1.10)
Si un seuil GNG échoue de peu et que la distribution des scores le justifie :
```bash
loko-eval --dataset eval/datasets/heldout_metier.csv --mode decision \
          --sweep seuil_haut=0.60:0.90:0.05,seuil_bas=0.30:0.60:0.05 …
```
Choisir le couple, **figer dans la config du bot (commit sur nouveau tag → retour V0-1 selon la règle 4, dérogation admise : re-run V0-1, V1-1→V1-4 en mode rapide + V3 complet)**, puis re-run V3-1 → V3-4 intégral. Interdit : présenter des chiffres obtenus avec des seuils différents entre les 4 jeux.

### V3-6 — Reproductibilité des chiffres (avant-goût GNG-4)
**Procédure** : rejouer V3-1 deux fois, avec `docker restart` entre les deux.
**Attendu** : `report.json` strictement identiques hors horodatage (`diff <(jq 'del(.timestamp)' r1.json) <(jq 'del(.timestamp)' r2.json)` vide).
**Artefact** : le diff vide.

### V3-7 — Boucle corrective si un GNG échoue (procédure normée)
Un échec V3-1/2/3 n'est **pas un bug** : c'est un résultat. Actions admises, dans l'ordre : (1) enrichissement des exemples d'entraînement (amendement du postulat §2, tracé), (2) calibration V3-5, (3) scission d'une intention hétérogène en sous-motifs. Chaque itération impose : retrain → re-run **complet** V3-1→V3-4 → datasets **inchangés** (les held-out ne sont jamais retouchés, jamais utilisés en entraînement). Nombre d'itérations et delta par itération consignés au rapport — c'est aussi une mesure de la maturité de l'outillage d'amélioration.

---

## 7. Porte de sortie et verdict

| Gate | Contenu | Verdict requis |
|---|---|---|
| G-0 | V0-1 → V0-5 | PASS (V0-4/V0-5 : PASS ou dérogation motivée) |
| G-1 **éliminatoire** | V1-1 → V1-4 | PASS sans réserve |
| G-1b | V1-5 offline | PASS |
| G-2 | V2-1 → V2-6 | PASS (V2-6 : P95 ≤ 50 ms) |
| G-3 | V3-1 ≥ 85 %, V3-2 ≥ 90 %, V3-3 ≥ 80 %, V3-4 ≥ 12/15 commenté, V3-6 diff vide | PASS aux seuils |

**Verdict « R0+R1 VALIDÉS »** = G-0 à G-3 PASS, rapport complet selon le gabarit (annexe A), artefacts archivés, version figée inchangée (ou re-run conforme après calibration V3-5).

Conséquences du verdict :
- **PASS** → ouverture des phases R2–R9 du protocole de recette v2. Prochaines dépendances de code : plan v2 items R6 (fetcher Playwright/miroir figé) et R2-b (ingestion + retriever persistant) pour R2 ; provider LLM réel pour R3. Le modèle, les seuils et le manifeste validés ici sont **gelés** : tout retrain ultérieur avant la recette intégrale impose de rejouer V3.
- **FAIL G-1** → correction du lot A, nouveau tag, campagne rejouée depuis V0-1.
- **FAIL G-3 après 3 itérations V3-7** → retour au postulat métier (revoir le choix d'intentions ou leurs frontières) avant tout nouveau code : le problème serait alors de conception du périmètre, pas d'implémentation.

---

## Annexe A — Gabarit du rapport de campagne

```
# Rapport campagne R0+R1 — {date}
Version : tag {…}, commit {…}, image digest {…}
Datasets : HASHES.sha256 vérifié le {…} (sortie jointe)
Environnement : sortie pip freeze ML + env vars (jointe)

## Tableau de synthèse
| ID | Verdict | Artefact |   ← une ligne par test V0-1 … V3-6, AUCUNE omission

## Chiffres GNG
GNG-1 : {…}% (seuil 85) — GNG-2 : {…}% (90) — GNG-3 : {…}% (80), dont routes à côté : {…}
Pièges : {…}/15, écarts commentés : §…

## Itérations V3-7 (le cas échéant)
| Itération | Action | GNG-1 | GNG-2 | GNG-3 |

## Anomalies hors périmètre découvertes
(consignées, non corrigées pendant la campagne)

## Verdict : R0+R1 VALIDÉS / NON VALIDÉS — gates G-0…G-3
```

## Annexe B — Rappel des interdits qui ont invalidé les campagnes précédentes

1. Requalifier un test unitaire ou un exemple isolé en pourcentage GNG (v0.2.0).
2. Mesurer depuis l'hôte au lieu du conteneur (écarts Windows/image).
3. Omettre une phase du tableau de synthèse (P2/P8 absents du rapport v0.2.0).
4. Valider un critère « structurellement » sans exécution.
5. Toucher aux CSV held-out, ou entraîner avec.
6. Committer pendant la campagne sans repartir de V0-1.
