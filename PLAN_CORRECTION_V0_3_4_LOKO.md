# 🔧 LOKO — Plan de correction v0.3.4 (post-campagne R0+R1 du 5 juillet, tag v0.3.3)

> **Version** : 1.0 — 5 juillet 2026
> **Entrée** : `RAPPORT_VALIDATION_R0_R1_LOKO.md` (v0.3.3, commit `2f856f52`) — verdict NON VALIDÉS, gates G-0/G-1/G-2 en échec sur 4 anomalies bornées.
> **Destinataire** : Claude Code. Règles inchangées : un commit atomique + tests par item, aucun test existant ne régresse, fail-closed, déterminisme préservé.
> **Contexte** : l'environnement est désormais sain (preflight 7/7, offline OK, gardes anti-mock OK, 316 tests verts, audit npm purgé). Les 4 items ci-dessous sont les derniers obstacles identifiés avant le volet V3 — celui qui n'a encore jamais produit un chiffre GNG.

---

## 0. Synthèse

| ID | Anomalie du rapport | Nature | Item |
|---|---|---|---|
| 1 | V1-3 : refus de publication en `400` + texte au lieu de `422` + codes machines | Contrat API | **K1** |
| 2 | V1-4 : témoin positif impossible — `503 No LLM provider configured` | Fonction manquante (dette avancée de R3) | **K2** |
| 3 | V2-1 : L1 en 643,7 s (critère < 120 s) + `ValueError: invalid literal for int() with base 10: 'changement_coordonnees'` dans `cross_validate` | Bug + performance | **K3** |
| 4 | V0-5 : `docker images` = 3,69 Go vs CE-3 `docker inspect` = 1,06 Go | Mesure contradictoire à diagnostiquer | **K4** |
| 5 | Réserve V1-2 (manifeste corrompu sans code explicite) ; V2-3 non exécuté | Rattaché à K1 / consigne de campagne | **K1**, §5 |

---

## 1. K1 — Taxonomie d'erreurs de publication : contrat `422` + codes machines

**Constat** : les trois contournements sont refusés fonctionnellement (manifeste factice, hash mismatch, exemples modifiés sans retrain) — la logique A4 est correcte. Seul le contrat HTTP est non conforme : `400` + message humain.

**Actions** :
1. Dans `loko/bot/errors.py`, enrichir la hiérarchie : `ModelIntegrityError(ComponentUnavailableError)` portant un champ `code` normé parmi `manifest_missing`, `manifest_invalid`, `hash_mismatch`, `load_error`, `smoke_failed`, `retrain_required`. `verify_model` lève cette exception avec le code précis pour **chaque** branche d'échec — y compris le manifeste corrompu/illisible (`manifest_invalid`), ce qui lève la réserve V1-2.
2. Handler FastAPI sur `POST /publish` : `ModelIntegrityError` → **422** avec corps normé :
   ```json
   {"error": "model_integrity", "code": "hash_mismatch", "detail": "…", "bot_id": "…"}
   ```
   Aucun chemin disque dans `detail` (règle déjà appliquée au 503 runtime — l'étendre ici).
3. Ne pas généraliser aveuglément : les autres 400 existants (validation métier de la config) restent des 400. Seule l'intégrité modèle passe en 422 — c'est la distinction sémantique (requête bien formée, état du modèle non traitable).
4. Tests : paramétré sur les 6 codes (dont manifeste tronqué/JSON invalide) → 422 + code exact ; test de non-régression sur un 400 de validation classique.

**Critère d'acceptation** : rejouer la procédure V1-3 telle quelle (3 tentatives) → trois `422` avec `manifest_missing`, `hash_mismatch`, `retrain_required` ; V1-2 sans réserve (`manifest_invalid` explicite).

---

## 2. K2 — Provider LLM réel minimal (dette R3 avancée, exigée par V1-4)

**Constat** : le fail-fast fonctionne comme conçu — trop bien : sans provider LLM configuré, un bot publié répond `503 bot_unavailable: No LLM provider configured` et le témoin positif de V1-4 est irréalisable. Le report du provider réel à la phase R3 n'est plus tenable.

**Actions** :
1. Créer `loko/bot/llm/openai_compat.py` : client HTTP asynchrone **compatible API OpenAI** (`/v1/chat/completions`), couvrant en un seul code OpenAI, DeepSeek, Mistral, vLLM/Ollama et tout endpoint compatible. Configuration par variables d'env :
   - `LOKO_LLM_PROVIDER=openai_compat` (seule valeur réelle pour l'instant ; `mock` reste interdit hors test) ;
   - `LOKO_LLM_BASE_URL`, `LOKO_LLM_API_KEY`, `LOKO_LLM_MODEL` ;
   - `temperature=0` **codé en dur** (pas configurable — exigence de déterminisme du protocole), `max_tokens` et `timeout` configurables avec défauts raisonnables (800 / 30 s).
2. Factory `build_llm_provider(config)` dans le même esprit que le loader classifieur : variables absentes → `ComponentUnavailableError("llm", …)` → 503 explicite (comportement actuel conservé, mais désormais évitable en configurant).
3. Robustesse minimale : timeout → erreur de tour propre (template d'excuse + trace), pas de retry silencieux (déterminisme) ; erreur 401/429 du provider → log + 503 au tour suivant. Streaming : si le support SSE amont existe déjà dans le code de génération, brancher le mode `stream=true` ; sinon, réponse complète découpée en `generation_delta` — acceptable pour cette campagne, noter la dette.
4. Traçabilité : la trace de tour enregistre modèle, latence premier token/total, nombre de tokens — champs déjà prévus par le schéma de trace.
5. Tests : unitaires avec serveur HTTP factice local (pas un mock de classe — un vrai serveur `aiohttp` de test répondant au format OpenAI), couvrant nominal, timeout, 401 ; test que `temperature` envoyée vaut toujours 0 ; garde `RAGKIT_ENV` inchangée sur `MockLLMProvider`.
6. Campagne : documenter dans le README de campagne la section `.env` requise (`LOKO_LLM_*`), et ajouter au **preflight** une vérification CE-8 : appel réel de 1 token au provider configuré (« ping LLM ») — échec = campagne non ouverte, pas découverte en V1-4.

**Critère d'acceptation** : bot MGEN publié + `.env` renseigné → `POST /sessions` → 200 avec message d'accueil (témoin positif V1-4 réalisable) ; suppression du modèle + restart → `503 Level 1 classifier not trained` (comportement déjà validé conservé).

---

## 3. K3 — Entraînement : corriger `cross_validate` et tenir < 2 min

**Constat** : deux problèmes imbriqués. (a) Bug : `cross_validate` fait `int(p)` sur des prédictions SetFit qui sont des **labels string** → `ValueError`, job `failed`, pas de manifeste. (b) Performance : 643,7 s pour le L1 seul — la validation croisée réentraîne vraisemblablement le corps SetFit à chaque fold.

**Actions** :
1. **Bug labels** : normaliser une bonne fois la frontière — en interne, la tête travaille sur des indices (`LabelEncoder` explicite, mapping conservé dans le manifeste champ `labels`), les prédictions exposées sont toujours des strings. Supprimer tout `int(p)` ; le point de conversion unique est l'encodeur. Test unitaire : cross-validation sur 3 classes aux labels strings arbitraires (accents, underscores) → aucune exception, matrice indexée par labels.
2. **Architecture de la validation croisée — le vrai correctif de perf** : ne jamais croiser le corps SetFit. Procédure cible :
   - entraînement contrastif du corps **une seule fois** sur tout le train ;
   - encodage des 125 exemples en embeddings (une passe, ~1 s CPU) ;
   - validation croisée k=5 **de la tête seule** (régression logistique sur embeddings) → matrice de confusion en secondes ;
   - entraînement final de la tête sur tout le train.
   La matrice reste honnête pour son usage produit (détecter les paires confondues et guider les exemples discriminants) tout en ramenant le coût de k×train_corps à 1×train_corps + k×fit_logistique. Documenter dans le rapport d'entraînement que la CV porte sur la tête (mention dans `train/report`).
3. **Budget du corps** : exposer `num_epochs`/`num_iterations` SetFit dans une config d'entraînement interne avec des défauts calibrés pour ~125 exemples × 9 classes en < 90 s CPU in-container (mesurer, ajuster, consigner dans `constraints-ml.txt` adjacent ou la config par défaut). Si le budget < 2 min s'avère physiquement intenable sur le runner de campagne après optimisation, le signaler **avant** campagne — ne pas découvrir en V2-1.
4. **Atomicité (V2-3)** : le comportement observé en creux est le bon (échec → modèle partiel **sans** manifeste, statut `failed`, non publiable). Ajouter le nettoyage du répertoire partiel au démarrage du train suivant + le test unitaire kill-worker prévu par V2-3 (le rapport ne l'a pas exécuté ; l'automatiser rend le point incontestable).
5. Vérifier au passage le L2 (`services_en_ligne`) avec la même mécanique labels/CV — il n'a jamais tourné (V2-2 bloqué).

**Critères d'acceptation** : train MGEN complet (L1 9 classes + L2 5 sous-motifs) in-container **< 120 s**, statut `completed`, manifeste complet (hashes, labels strings, latences), matrice 9×9 exportée avec conseil ; le test kill-worker passe ; inférence P95 ≤ 50 ms confirmée sur le bot MGEN (le 37,6 ms du bot jetable est encourageant mais non opposable).

---

## 4. K4 — Taille d'image : diagnostiquer la contradiction avant de corriger

**Constat** : CE-3 (`docker inspect`, même image id `fe173c…`) donne **1,06 Go** ; V0-5 (`docker images`) donne **3,69 Go**. Ces deux mesures désignent normalement la même chose — corriger à l'aveugle serait reproduire les erreurs des campagnes passées.

**Actions** :
1. **Diagnostic d'abord** (script `tools/diag_image.py` ou procédure documentée) :
   - `docker images --digests` + `docker inspect --format '{{.Size}}'` sur le **même** tag : si les tailles divergent, identifier quelle image `docker images` liste réellement (tag flottant `latest` vs tag versionné — hypothèse la plus probable : une image de build antérieure, pré-optimisation, porte encore le tag mesuré) ;
   - `docker history loko-r0r1-codex:v0.3.3 --no-trunc` : chercher les couches > 300 Mo dupliquées — suspect n°1 : le snapshot du modèle (~500 Mo) copié dans une couche puis déplacé/re-chowné dans une autre (chaque modification re-crée la couche entière) ;
   - noter l'environnement de mesure (Docker Desktop/WSL2 affiche parfois la taille décompressée vs compressée).
2. **Correction selon diagnostic** : si duplication de couches → réordonner le Dockerfile (le `COPY` du modèle en dernière couche stable, `--chown` directement sur le COPY, pas de `RUN mv/chmod` postérieur) ; si tag flottant → corriger la procédure de build de campagne pour construire et mesurer le tag versionné uniquement.
3. **Ajuster le protocole de mesure** : V0-5 mesure désormais par `docker inspect --format '{{.Size}}'` sur le digest consigné en CE-3 (une seule source de vérité), cible inchangée ≤ 1,6 Go. Ajouter cette mesure au preflight.
4. Si, après diagnostic, la taille réelle est bien 1,06 Go : V0-5 était un artefact de mesure — le consigner, aucune « optimisation » à faire.

**Critère d'acceptation** : une seule taille, mesurée sur digest, ≤ 1,6 Go, cohérente entre CE-3, V0-5 et preflight ; explication de l'écart 3,69/1,06 consignée dans le commit.

---

## 5. Consignes pour la campagne v0.3.4

1. **Préparation** : items K1→K4 mergés, tag `v0.3.4`, preflight étendu (CE-8 ping LLM, mesure taille par digest) → PASS intégral avant ouverture.
2. **Reprise depuis V0-1**, protocole `PROTOCOLE_VALIDATION_R0_R1_LOKO.md` inchangé sur le fond ; deux précisions d'exécution actées (sans changer les seuils) : V0-5 mesuré par inspect/digest (K4.3) ; V1-4 exige désormais le témoin positif (rendu possible par K2).
3. **V2-3 doit être exécuté** cette fois (kill worker) — il était NON EXECUTE au rapport ; l'automatisation K3.4 le rend trivial.
4. Point d'attention V3 : ce sera la **première exécution réelle** de `loko-eval` sur un modèle entraîné. Prévoir du temps d'analyse pour `errors.csv` (classement des erreurs exigé par V3-1) et ne pas paniquer si GNG-1/2/3 ne passent pas du premier coup : la boucle V3-7 est prévue pour ça — 3 itérations maximum avant retour au postulat.

## 6. Definition of done

1. K1–K4 verts en CI (nouveaux tests : 6 codes 422, provider openai_compat avec serveur factice, CV labels strings, kill-worker, mesure image).
2. Preflight v0.3.4 : 8/8 PASS (CE-1→CE-8).
3. Campagne rejouée depuis V0-1, rapport au gabarit, et — objectif de cette itération — **le volet V3 atteint et exécuté**, quels que soient les chiffres : après cinq campagnes, produire enfin GNG-1/2/3 mesurés serait en soi le franchissement décisif, même si une boucle V3-7 s'avère nécessaire ensuite.
