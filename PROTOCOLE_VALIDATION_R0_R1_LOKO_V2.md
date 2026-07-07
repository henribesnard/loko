# ✅ LOKO — Protocole de validation R0+R1 — version 2.1 (amendé W3)

> **Version** : 2.1 — 7 juillet 2026 — remplace la version 2.0 du 6 juillet 2026.
> **Objet** : protocole d'exécution de la campagne validant **R0 (intégrité anti-mock)** et **R1 (entraînement réel + évaluation statistique)**, après livraison du plan `PLAN_CORRECTION_V0_3_6_LOKO.md` (items M1–M3).
> **Références** : `PROTOCOLE_RECETTE_PRODUIT_LOKO_V2.md` (critères GNG du GO final), `PLAN_CORRECTION_V0_3_6_LOKO.md` (arbitrages A1–A6), `POSTULAT_TEST_E2E_LOKO.md` §2 (config MGEN), `FEUILLE_DE_ROUTE_VALIDATION_FINALE_R0_R1_LOKO.md` (chantiers W1–W5).
> **Ce que cette campagne décide** : l'ouverture des phases R2–R9. Elle ne décide **pas** le GO produit.
> **Ce qui change en v2.1** (amendements W3) : (1) **W3.1** — sélection Pareto contrainte (GNG-3 ≥ 80%, routes_directes ≤ 5, maximisation lexicographique GNG-1→GNG-2→pièges) ; (2) **W3.2** — V2-4/V2-5 sur bot jetable (`tools/clone_bot.py`), V3 mesure le modèle V2-1 figé (évite contamination train) ; (3) **W3.3** (non implémenté encore) — 3-seed CV pour V2-5 ; (4) **W3.4** (non implémenté encore) — hash dataset + manifeste dans report natif. Les seuils GNG-1/GNG-2/pièges sont **inchangés** : 85 %, 90 %, 12/15.

---

## 0. Règles d'exécution (inchangées, opposables)

1. **Aucun mock**, à l'exception explicite de `MockEscalationProvider` sous `LOKO_ESCALATION_PROVIDER=mock`. Tout test posant `RAGKIT_ENV=test` hors pytest est invalide.
2. **Toute exécution est in-container.** Les mesures depuis l'hôte sont irrecevables.
3. **Chaque test produit son artefact**, archivé dans `eval/campagne-R0R1/{date}/`. Une ligne non exécutée = FAIL au rapport, jamais absente.
4. **Version figée** : tag posé avant le premier test, digest consigné, aucun commit jusqu'au verdict. Toute correction → nouveau tag → reprise depuis V0-1. **Dérogation calibration** (V3-0) : le gel des seuils dans la config versionnée impose seulement un re-run rapide (V0-1, V1-1→V1-4) puis V3 complet — pas une campagne entière.
5. Un FAIL n'interrompt pas la campagne, **sauf** les éliminatoires V1-1 à V1-4.
6. **Nouveau** : un FAIL doit désigner un fait produit ou métier. Si l'exécutant suspecte un artefact de mesure ou un défaut du protocole lui-même, il le consigne en anomalie de protocole (annexe A, section dédiée) **sans** requalifier le verdict de son propre chef — l'amendement se décide entre campagnes, pas pendant.

---

## 1. Conditions d'entrée (checklist bloquante)

| # | Condition | Vérification | ✔ |
|---|---|---|---|
| CE-1 | Items M1–M3 mergés sur `main`, CI verte, worktree **clean** (`untracked=0`) | Preflight + lien runs CI | ☐ |
| CE-2 | Tag posé, commit consigné, **triple version identique** : `git describe --tags` == `pyproject.toml` == `pip show loko` in-container | Sortie preflight (les 3 valeurs) | ☐ |
| CE-3 | Image construite depuis le tag ; digest consigné ; **taille par `docker inspect --format '{{.Size}}'` ≤ 1,6 Go** (valeur `docker images` consignée à titre informatif uniquement) | `CE-3_image_inspect.txt` | ☐ |
| CE-4 | Datasets figés conformes : `train=125`, `heldout_metier=100`, `heldout_conseiller=125`, `heldout_horsscope=100`, `pieges=15` | `sha256sum -c eval/datasets/HASHES.sha256` | ☐ |
| CE-5 | Intersection train/held-out vide | `python tools/make_datasets.py --check` → exit 0 | ☐ |
| CE-6 | `loko-eval` opérationnel dans l'image, **option `--sweep` 3 axes présente** | `loko-eval --help` | ☐ |
| CE-7 | Répertoire d'artefacts créé, gabarit annexe A copié | `eval/campagne-R0R1/{date}/` | ☐ |
| CE-8 | Ping LLM réel (1 token) via `.env` mappé en `LOKO_LLM_*`, aucun secret archivé | `CE-8_llm_ping.txt` | ☐ |

Toute case non cochée : la campagne ne démarre pas.

---

## 2. Préparation de l'environnement

```bash
docker volume create loko-r0r1
docker run -d --name loko-campagne \
  -e LOKO_ADMIN_TOKEN=$(openssl rand -hex 24) \
  -e RAGKIT_MODE=server \
  --env-file <(grep -E '^LOKO_LLM_' .env) \
  -v loko-r0r1:/data -e LOKO_DATA_DIR=/data \
  -p 127.0.0.1:18001:8000 loko:{tag}
curl -fsS http://127.0.0.1:18001/health
```

Consigner : digest, env effectives (`env | grep -E 'LOKO|RAGKIT|HF_'`), versions Python et ML (`pip freeze | grep -E 'setfit|transformers|sentence|torch'`) — conformité `constraints-ml.txt`, tout écart = FAIL CE-3.

Bot de campagne : config MGEN du postulat §2 (7 intentions métier + `hors_perimetre` + 5 sous-motifs `services_en_ligne`) chargée depuis `train.csv` via `tools/load_postulat.py`. Vérifier : 9 intentions, ≥ 8 exemples chacune, statut `draft`.

---

## 3. Volet V0 — Recevabilité technique

| ID | Procédure | Attendu | Artefact |
|---|---|---|---|
| V0-1 | Suite complète in-container : `pytest -m "" --tb=short -q` (`slow` inclus) | `0 failed`, skips justifiés (≤ 1) | `V0-1_pytest.txt` |
| V0-2 | Imports ML : `python -c "import setfit, sentence_transformers, torch; …"` | OK, `+cpu`, CUDA `False` | `V0-2_imports.txt` |
| V0-3 | Grep anti-mock hors `tests/` (exception documentée : `MockEscalationProvider` dans `bot_public.py` sous `LOKO_ESCALATION_PROVIDER=mock`) | 0 occurrence hors exception | `V0-3_grep.txt` |
| V0-4 | `npm audit --audit-level=high` | 0 finding high/critical | `V0-4_audit.txt` |
| V0-5 | **Taille par `docker inspect --format '{{.Size}}'` sur le digest CE-3** (amendement A1) | ≤ 1,6 Go | `V0-5_image_size.txt` (inspect + `docker images` informatif) |

---

## 4. Volet V1 — Phase R0 : intégrité (éliminatoires) — mode confirmation

R0 a été intégralement validé en campagne v0.3.5 (V1-1→V1-5 PASS). Les critères sont inchangés ; l'exécution est la re-passe des mêmes procédures, sans exploration nouvelle.

| ID | Procédure (identique v1.0) | Attendu | Artefact |
|---|---|---|---|
| V1-1 | Tests gardes mock + contre-épreuve manuelle hors pytest (`RAGKIT_ENV=`) | `RuntimeError` ×4 ; seule l'exception escalade autorisée | `V1-1_mock_guard.txt` |
| V1-2 | `load_classifier` sur modèle absent / factice / corrompu | `ComponentUnavailableError`, jamais d'instance | `V1-2_loader.txt` |
| V1-3 | 3 contournements publication (manifeste factice, octet corrompu, exemple modifié sans retrain) | `422` : `manifest_missing`, `hash_mismatch`, `retrain_required` | `V1-3_publish.http.json` |
| V1-4 | Témoin positif (session `201`) → `rm -rf models/level1` → restart → sessions/messages | `503 bot_unavailable`, 0 session nouvelle, aucun `hors_perimetre` généré, log CRITICAL au boot | `V1-4_failfast.json` |
| V1-5 | Conteneur `--network none`, bot 2 intentions ×8, train + 3 inférences | Succès, offline env présent | `V1-5_offline.txt` |

**Porte intermédiaire** : V1-1→V1-4 PASS sans réserve, sinon arrêt (règle 5).

---

## 5. Volet V2 — Phase R1.a : entraînement réel

### V2-1 — Entraînement MGEN complet
**Procédure** : `POST /train` sur le bot de campagne, suivi `GET /train/status` toutes les 5 s.
**Attendu** : progression monotone ; durée totale (L1 + L2 + évaluation + manifeste) **≤ 300 s** in-container (amendement A2 — le 120 s reste un objectif backlog non bloquant) ; **profil par phase archivé** (contrastif, fit tête, encodage, CV, latence) ; manifeste complet (schéma, hashes, 9 labels strings, `dataset_hash`, `train_metrics`, `inference_latency_ms` avec méthodologie).
**Artefact** : `V2-1_train_run.txt`, `V2-1_manifest.json`.

### V2-2 — Niveau 2 `services_en_ligne`
**Attendu** : manifeste avec `level2_services_en_ligne` et les 5 labels exacts : `compte_bloque`, `identifiants_perdus`, `mot_de_passe_oublie`, `premiere_connexion`, `probleme_technique`.
**Artefact** : `V2-1_manifest.json`.

### V2-3 — Atomicité (kill worker)
**Procédure** : interrompre le train pendant `l1_training` (kill), restart.
**Attendu** : pas de manifeste partiel ; statut persisté `failed/interrupted` (pas `idle`) ; retrain suivant `completed`.
**Artefact** : `V2-3_atomicity.json`.

### V2-4 — Matrice, paires faibles et conseil (amendement A3 + W3.2)
**Isolation V2-4/V2-5** (protocole v2.1) : cloner le bot de campagne post-V2-1 vers un **bot jetable** (`tools/clone_bot.py {bot_id} v2-disposable`). V2-4 et V2-5 s'exécutent sur ce clone. Le bot de campagne reste figé à V2-1 et sera mesuré par V3. Ceci évite la contamination méthodologique (V2-5 ajoutant des exemples juste avant mesure V3).

**Procédure** : `GET /train/report` du **bot jetable** → matrice 9×9, `margin_weak_pairs`, `advice`.
**Attendu** : matrice exportée (CV `base_model_frozen`, méthode consignée) ; **`advice` non vide dès qu'au moins une paire faible est détectée** (par CV hors-diagonale ou par marges), la première entrée désignant la paire la plus faible avec une suggestion actionnable citant des verbatims à faible marge. La paire n'est **pas prescrite** par le protocole — c'est la détection par l'outil qui est testée. (Si aucune paire faible n'est détectée nulle part, `advice=[]` est un PASS, mais V2-5 devient inexécutable et doit être déclaré tel avec la preuve.)
**Artefact** : `V2-4_confusion.csv`, `V2-4_advice.json`.

### V2-5 — Cycle d'amélioration mesuré, sur la paire détectée (amendement A3 + W3.2 + W3.3)
**Procédure** : prendre la **première paire de `advice`** (état actuel attendu : `arret_travail`/`justificatif_droits`). Ajouter 3 exemples discriminants de chaque côté via l'API admin **au bot jetable**, retrain, ré-exporter rapport et matrice.

**Critère de réduction (W3.3 — protocole v2.1)** : PASS si **au moins UN** des deux signaux diminue :
  1. Case CV de la paire (moyenne sur **3 seeds** de partition CV pour réduire variance)
  2. Nombre d'exemples à faible marge sur la paire (`margin_weak_pairs`)

**Attendu** : réduction ≥ 1 sur au moins un signal ; `cv_method=base_model_frozen_3seeds` dans le rapport ; `dataset_hash` modifié ; durée du retrain ≤ 300 s. Valeurs avant/après consignées pour les deux signaux.

**Artefact** : `V2-5_comparison.json`, `V2-5_matrices_avant_apres.csv`.
**Nettoyage** : après V2-6, supprimer le bot jetable (`rm -rf data/bots/{clone_id}` ou via API `DELETE /api/bot/{clone_id}`).

### V2-6 — Latence d'inférence
**Procédure** : `inference_latency_ms` du manifeste post-V2-5 (warm-up + 100 inférences au repos) + contre-mesure indépendante (100 verbatims held-out, `perf_counter`).
**Attendu** : **P95 ≤ 50 ms** sur les deux ; écart < 30 %.
**Artefact** : `V2-6_latency.json`.

---

## 6. Volet V3 — Phase R1.b : calibration puis évaluation statistique

**Modèle mesuré** (protocole v2.1) : **bot de campagne figé post-V2-1** (PAS le bot jetable V2-4/V2-5). Ceci garantit que les métriques GNG mesurent le train de référence, exempt de contamination V2-5. Seule la boucle V3-7 tracée peut enrichir ce train.

Tout s'exécute in-container sur ce modèle. Chaque `report.json` embarque hash du dataset et référence du manifeste. Les durées vivent dans `meta.json`, hors périmètre des diffs.

### V3-0 — Calibration obligatoire (amendement A4, remplace l'ancien V3-5 optionnel)
**Procédure** :
```bash
loko-eval --bot-dir /data/bots/{id} --mode sweep \
  --sweep seuil_haut=0.60:0.90:0.05,seuil_bas=0.30:0.60:0.05,seuil_ecart=0.05:0.25:0.05 \
  --datasets eval/datasets/heldout_metier.csv,heldout_conseiller.csv,heldout_horsscope.csv,pieges.csv \
  --out eval/campagne-R0R1/{date}/sweep/
```
**Sélection** : le point de Pareto satisfaisant simultanément GNG-1 ≥ 85 %, GNG-2 ≥ 90 %, GNG-3 ≥ 80 % **avec ≤ 5 routes directes/100** (amendement A5), pièges maximisés. Si aucun point ne satisfait le triplet : retenir le point minimisant la distance aux seuils, consigner la grille, et savoir dès maintenant que la boucle V3-7 sera nécessaire.
**Gel** : seuils figés dans la config versionnée du bot → dérogation règle 4 (re-run rapide V0-1 + V1-1→V1-4, puis V3-1→V3-6 complet). **Interdit** : présenter des chiffres obtenus avec des seuils différents entre les 4 jeux, ou re-balayer après avoir vu les chiffres finaux sans nouvelle itération V3-7 tracée.
**Artefact** : la grille complète + le point retenu et sa justification.

### V3-1 — GNG-1 : précision métier (mode décision)
```bash
loko-eval --dataset heldout_metier.csv --mode decision --threshold-check gng1:0.85 …
```
**Attendu** : ≥ 85 % (route directe correcte ou intention vraie dans les candidats de clarification), exit 0. **Analyse obligatoire** : chaque erreur d'`errors.csv` classée (verbatim ambigu / manque d'exemples / seuil).

### V3-2 — GNG-2 : détection `demande_conseiller`
**Attendu** : ≥ 90 % des 125 verbatims → décision `transverse:demande_conseiller`.

### V3-3 — GNG-3 : rejet hors-scope
**Attendu** : ≥ 80 % en `reject`/`escalate` **et ≤ 5 routes directes métier/100** (amendement A5 — le sous-compte devient un critère, plus une réserve). Le « 0 route directe » reste le critère du GO final (recette v2), pas de cette campagne.

### V3-4 — Les 15 pièges
**Attendu** : ≥ 12/15 conformes à `expected_behavior` (comparaison sémantique type+intent), **chaque écart commenté individuellement** — un écart non commenté vaut FAIL. Vigilance : T01/T02/T15 (frontière `services_en_ligne`↔`changement_coordonnees`), T04/T05/T06 (clarifications inter attendues), T13 (rejet franc attendu).

### V3-5 — supprimé (absorbé par V3-0). Numéro réservé pour la traçabilité inter-campagnes.

### V3-6 — Reproductibilité
**Procédure** : rejouer V3-1 deux fois, `docker restart` entre les deux.
**Attendu** : `report.json` strictement identiques (diff brut vide — les durées sont dans `meta.json`).

### V3-7 — Boucle corrective normée (max 2 itérations d'exemples après V3-0)
Un échec GNG est un résultat, pas un bug. La calibration ayant déjà eu lieu (V3-0), les actions admises sont, dans l'ordre : (1) enrichissement d'exemples de train ciblé par `errors.csv` (amendement tracé du postulat §2), (2) re-calibration V3-0 complète si les nouveaux exemples déplacent les distributions de scores, (3) scission d'une intention hétérogène. Chaque itération : retrain → re-run **complet** V3-1→V3-4 et V3-6 → held-out **intouchés**. Tableau des itérations au rapport (action, GNG-1/2/3, routes directes, pièges).
**Butée** : 2 itérations d'exemples maximum. Au-delà → FAIL G-3 définitif de la campagne → retour au postulat métier avant tout nouveau code.

---

## 7. Porte de sortie et verdict

| Gate | Contenu | Verdict requis |
|---|---|---|
| G-0 | V0-1 → V0-5 (V0-5 par inspect/digest) | PASS |
| G-1 **éliminatoire** | V1-1 → V1-4 | PASS sans réserve |
| G-1b | V1-5 offline | PASS |
| G-2 | V2-1 → V2-6 (V2-1 ≤ 300 s ; V2-4/V2-5 sur paire détectée ; V2-6 P95 ≤ 50 ms) | PASS |
| G-3 | V3-1 ≥ 85 %, V3-2 ≥ 90 %, V3-3 ≥ 80 % avec ≤ 5 routes directes, V3-4 ≥ 12/15 commenté, V3-6 diff vide — le tout aux seuils figés en V3-0 | PASS |

**Verdict « R0+R1 VALIDÉS »** = G-0 à G-3 PASS, rapport au gabarit (annexe A), artefacts archivés, version figée (dérogation V3-0 admise et tracée).

Conséquences :
- **PASS** → ouverture des phases R2–R9. Le modèle, les **seuils figés en V3-0** et le manifeste sont gelés : tout retrain avant la recette intégrale impose de rejouer V3-1→V3-6.
- **FAIL G-1** → correction, nouveau tag, campagne complète depuis V0-1.
- **FAIL G-3 après V3-0 + 2 itérations** → retour au postulat métier (choix ou frontières des intentions). Aucune campagne supplémentaire avant révision du postulat.

**Travaux parallèles autorisés pendant et après cette campagne** (clarification demandée après v0.3.5) : le **développement** des chantiers R2–R9 (ingestion/knowledge, dashboard, sécurité runtime) peut démarrer sans attendre le PASS, à condition de ne toucher ni au classifieur, ni à la couche de décision, ni aux seuils, ni à `loko-eval`. Seules leurs **recettes** restent conditionnées au PASS de cette campagne. Est en revanche gelé jusqu'au PASS G-3 : tout ce qui dépend de la qualité du routage (recette humaine R9, engagements de selfcarisation).

---

## Annexe A — Gabarit du rapport de campagne

```
# Rapport campagne R0+R1 — {date} — protocole v2.0
Version : tag {…}, commit {…}, digest {…}, triple version vérifiée : {…}
Datasets : HASHES.sha256 vérifié le {…}
Environnement : pip freeze ML + env vars (joints)

## Tableau de synthèse
| ID | Verdict | Artefact |   ← V0-1 … V3-7, AUCUNE omission (V3-5 : « supprimé v2.0 »)

## Calibration V3-0
Grille jointe — point retenu : seuil_haut={…}, seuil_bas={…}, seuil_ecart={…} — justification

## Chiffres GNG (aux seuils figés)
GNG-1 : {…}% (85) — GNG-2 : {…}% (90) — GNG-3 : {…}% (80), routes directes : {…}/100 (≤5)
Pièges : {…}/15, écarts commentés : §…

## Itérations V3-7
| Itération | Action | GNG-1 | GNG-2 | GNG-3 (routes directes) | Pièges |

## Anomalies produit hors périmètre / Anomalies de protocole suspectées (règle 6)

## Verdict : R0+R1 VALIDÉS / NON VALIDÉS — gates G-0…G-3
```

## Annexe B — Interdits ayant invalidé les campagnes précédentes (inchangés + ajouts)

1. Requalifier un test unitaire ou un exemple isolé en pourcentage GNG (v0.2.0).
2. Mesurer depuis l'hôte au lieu du conteneur.
3. Omettre une phase du tableau de synthèse.
4. Valider un critère « structurellement » sans exécution.
5. Toucher aux CSV held-out, ou entraîner avec.
6. Committer pendant la campagne sans repartir de V0-1 (hors dérogation V3-0 tracée).
7. **Nouveau** : présenter des chiffres GNG obtenus avec des seuils non figés ou différents entre jeux (v0.3.4/v0.3.5 : sweep jamais exécuté, seuils par défaut jamais interrogés).
8. **Nouveau** : requalifier un FAIL en artefact de mesure pendant la campagne sans l'amendement inter-campagnes correspondant (v0.3.4/v0.3.5 : V0-5 mesuré trois fois au mauvais instrument).

## Annexe C — Amendements v2.0 et leur justification (traçabilité)

| Amdt | Ancien (v1.0) | Nouveau (v2.0) | Justification |
|---|---|---|---|
| A1 | V0-5 par `docker images`, ≤ 1,6 Go | V0-5 par `docker inspect` sur digest, ≤ 1,6 Go | 3 campagnes de FAIL sur la taille décompressée affichée par Docker Desktop/WSL2 ; la taille réelle (1 009 Mo) est conforme depuis v0.3.3. |
| A2 | V2-1 < 120 s | V2-1 ≤ 300 s + profil obligatoire | ÷7,7 déjà obtenu ; le reliquat est du contrastif utile à la qualité. 120 s reste au backlog produit, non bloquant pour R2–R9. |
| A3 | V2-4/V2-5 sur la paire prescrite `cotisations`↔`changement_coordonnees` | Sur la paire la plus faible **détectée par l'outil** | La paire prescrite est séparable dans le train figé (confusion 0 en CV honnête) : le test était invalide par construction. C'est la capacité de détection+amélioration qui est l'exigence produit. |
| A4 | V3-5 calibration optionnelle « si échec marginal » | V3-0 sweep 3 axes obligatoire avant toute mesure | Deux campagnes où 80 % des erreurs GNG-1/GNG-2 sont des faux rejets sans qu'aucun seuil n'ait jamais été interrogé. |
| A5 | Routes directes hors-scope : sous-compte « reporté » | Critère : ≤ 5/100 pour R0+R1 (0 reste le critère du GO final) | Empêche le sweep d'améliorer GNG-1 en dégradant le risque client réel ; borne intermédiaire réaliste (8/100 constaté). |
| A6 | `heldout_conseiller = 126` | `= 125` | Alignement sur les datasets figés réels (hashes) et les rapports. |
