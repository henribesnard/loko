# 🔧 LOKO — Plan de correction v0.3.5 (post-campagne R0+R1 du 5 juillet, tag v0.3.4)

> **Version** : 1.0 — 5 juillet 2026
> **Entrée** : `RAPPORT_VALIDATION_R0_R1_LOKO.md` (campagne propre v0.3.4, commit `892032a8`) — verdict NON VALIDÉS, gates G-0/G-2/G-3 en échec.
> **Destinataire** : Claude Code. Règles inchangées : un commit atomique + tests par item, aucun test existant ne régresse, fail-closed, déterminisme préservé.
> **Contexte** : franchissement majeur acté — G-1 éliminatoire PASS (gardes anti-mock, fail-fast, 422 codés, provider LLM réel), et le volet V3 a produit ses premiers chiffres GNG mesurés. Le mur n'est plus l'intégrité : c'est (a) l'outillage d'évaluation buggé, (b) la performance et l'utilité de l'entraînement/CV, (c) la calibration métier du modèle. Deux FAIL du rapport sont par ailleurs des artefacts de mesure ou de formalisme (V0-5, V3-6), pas des défauts produit.

---

## 0. Synthèse

| # | Anomalie du rapport | Nature | Item |
|---|---|---|---|
| 1 | V3-1/V3-3 : `loko-eval` plante à l'écriture d'`errors.csv` (`ValueError: dict contains fields not in fieldnames: 'correct'`) | Bug outillage | **L1** |
| 2 | V3-4 : mode pièges compare `decision.type` à la chaîne complète `route:intent` → score CLI 1/15 vs ~7/15 sémantique | Bug outillage | **L1** |
| 3 | V3-6 : diff non vide à cause du seul champ `duration_s` dans `report.json` | Formalisme rapport | **L1** |
| 4 | V2-1/V2-5 : train MGEN 1783 s (L1 764 s, L2 114 s, **éval 747 s**), seuil < 120 s | Performance | **L2** |
| 5 | V2-4/V2-5 : CV head-only accuracy 1.0, confusion attendue = 0, advice `[]` — matrice inutilisable | Défaut de conception (fuite CV, héritée de K3.2) | **L3** |
| 6 | V2-3 : après kill/restart, statut job = `idle` au lieu de `failed` persisté | Persistance d'état | **L4** |
| 7 | V2-6 : P95 manifeste 63,76 ms vs contre-mesure indépendante 34,59 ms | Méthodologie de mesure | **L5** |
| 8 | V0-5 : `docker images` 3,69 Go vs `docker inspect` 1,06 Go — K4.3 (mesure par digest) non appliqué en campagne | Application du protocole | **L6** |
| 9 | GNG-1 73 %, GNG-2 84,8 %, pièges ~7/15, GNG-3 avec 9 routes métier directes hors-scope | Calibration + qualité modèle | **L7** (campagne) |
| 10 | CE-1 : worktree non clean (livrables rapport/plan dans le repo) | Discipline de campagne | **L8** |

Ordre d'exécution recommandé : **L1 → L4 → L5 → L6 → L8** (correctifs bornés, ~1 jour), puis **L2+L3** (le gros morceau, imbriqués), puis campagne v0.3.5 avec **L7** comme protocole d'itération V3-7.

---

## 1. L1 — `loko-eval` : trois correctifs pour un outillage opposable

**Constat** : `loko-eval` est l'instrument de mesure des GNG. Tant qu'il plante et sous-compte, aucun chiffre V3 n'est opposable — c'est le bloquant n°1, et le moins cher.

**Actions** :
1. **`errors.csv`** : le dict d'erreur contient un champ `correct` absent des `fieldnames` du `csv.DictWriter`. Corriger en alignant les fieldnames sur le schéma prévu par C2 (`text,true,predicted,decision,score_top1,score_top2`) — soit en ajoutant `correct` aux fieldnames si le champ est utile, soit en le filtrant avant écriture. Décision recommandée : l'ajouter (utile au tri), et figer le schéma dans un test.
2. **Mode pièges** : parser `expected_behavior` correctement. Grammaire : `route:{intent}` → succès si `decision.type == "route"` **et** `decision.intent == intent` ; `clarification_intra:{intent}` / `clarification_inter:{a}/{b}[/{c}]` → succès si type clarification et candidats attendus présents ; `escalate` / `reject` → sur le type (et l'intent transverse pour escalade). Écrire la fonction de comparaison comme fonction pure testée sur les 15 cas du rapport (T01–T15 ont maintenant des attendus/observés documentés — en faire les fixtures).
3. **Déterminisme (V3-6)** : sortir `duration_s` (et tout champ de durée) de `report.json` vers un fichier `meta.json` adjacent, explicitement hors périmètre du diff de reproductibilité. `report.json` ne contient plus que des données déterministes (métriques, verdicts, hashes datasets, version modèle). Alternative rejetée : amender le protocole — c'est le rapport qui doit être déterministe, pas la règle qui doit s'assouplir.
4. **Code retour** : vérifier que l'exit 1 provient bien des `--threshold-check` en échec et non du crash `errors.csv` — après correctif 1, un run sous seuil doit sortir 1 **avec** tous ses artefacts écrits (le crash actuel produit exit 1 sans `errors.csv`, ce qui rend V3-1 inauditable).
5. Tests : paramétrés sur les 5 formes d'`expected_behavior` ; run complet sur un mini-dataset avec erreurs → `report.json` + `confusion.csv` + `errors.csv` tous écrits, exit code correct ; double run → `report.json` binaire-identique.

**Critère d'acceptation** : rejouer V3-4 sur les mêmes décisions archivées (`V3-4_pieges_decisions.json`) → score CLI = score sémantique (~7/15) ; V3-1 produit `errors.csv` complet ; deux runs V3-6 → diff vide sur `report.json` sans exclusion.

---

## 2. L2 — Performance d'entraînement : tenir < 120 s pour de vrai

**Constat** : la décomposition du rapport est parlante — L1 764 s, L2 114 s, évaluation 747 s. Deux gisements distincts : le corps SetFit L1 (K3.3 visait < 90 s, on est à 8× au-dessus) et l'évaluation qui coûte 42 % du total pour produire une matrice inutile (voir L3).

**Actions** :
1. **Profiler avant d'optimiser** : instrumenter le job de train (temps par phase : contrastif corps, fit tête, encodage éval, CV) et archiver ce profil dans `train/report`. Le 764 s du corps sur 125 exemples × 9 classes suggère un `num_iterations` SetFit par défaut (20) générant ~O(n²) paires — vérifier.
2. **Calibrer le budget contrastif** : exposer `num_iterations`/`num_epochs`/`batch_size` dans la config d'entraînement (prévu par K3.3, visiblement non appliqué ou défauts trop hauts). Cible : `num_iterations` 5–10, batch 16–32, mesurer la précision held-out interne à chaque palier et retenir le plus petit budget sans perte > 1 pt. Consigner les défauts retenus et la mesure dans le commit.
3. **Supprimer les ré-encodages** : une seule passe d'encodage des exemples après fine-tuning du corps, embeddings mis en cache et réutilisés par le fit de tête, la CV (selon architecture L3) et la mesure de latence du manifeste. Aujourd'hui l'éval à 747 s indique très probablement des ré-encodages par fold.
4. **L2 est déjà dans les clous** (114 s seul) mais le budget total L1+L2+éval doit tenir < 120 s : si après optimisation le total réel est 120–180 s, le signaler **avant** campagne avec le profil à l'appui pour arbitrage (ajustement du seuil protocole vs optimisation supplémentaire) — ne pas re-découvrir en V2-1.

**Critère d'acceptation** : train MGEN complet (L1 9 classes + L2 5 sous-motifs + évaluation + manifeste) in-container < 120 s, profil par phase archivé, précision interne non dégradée (> 1 pt) vs budget précédent.

---

## 3. L3 — CV, matrice et advice : mesurer une difficulté réelle

**Constat** : l'architecture K3.2 (corps fine-tuné une fois sur tout le train, CV k=5 de la tête seule sur ses embeddings) produit une accuracy de 1.0 et une matrice vide de confusions. Cause structurelle : le corps a vu **tous** les exemples pendant le contrastif — les embeddings des folds de validation sont déjà séparés par construction. C'est une fuite, la matrice ne peut par conception révéler aucune paire confondue. K3.2 doit être révisé, pas rafistolé.

**Actions** :
1. **CV sur embeddings du modèle de base** (pré-fine-tuning) : encoder les 125 exemples avec le MiniLM gelé (une passe, quelques secondes), CV k=5 de la tête logistique sur ces embeddings. La matrice mesure alors la séparabilité intrinsèque des intentions — c'est exactement l'usage produit visé (détecter `cotisations`↔`changement_coordonnees` et guider les exemples discriminants), et c'est quasi gratuit en temps.
2. **Compléter par les marges du modèle final** : sur le modèle réellement entraîné, calculer pour chaque exemple de train l'écart top1−top2 ; les paires d'intentions concentrant les faibles marges alimentent la matrice « douce » et l'advice, même quand l'argmax est correct.
3. **Advice** : générer un conseil dès que (a) une case hors-diagonale de la CV base ≥ 2, ou (b) une paire concentre ≥ 3 exemples à marge < seuil configurable. Format : paire, exemples concernés, suggestion (« ajouter des exemples discriminants côté X mentionnant … »). Documenter dans `train/report` que la CV porte sur le modèle de base et pourquoi (honnêteté méthodologique exigée par le protocole).
4. Test : dataset synthétique avec deux classes volontairement chevauchantes → la case hors-diagonale est non nulle et un conseil est produit ; ajout de 3 exemples discriminants → la confusion CV diminue mesurablement (c'est le scénario V2-5 en unitaire).

**Critère d'acceptation** : sur le train MGEN, la matrice exportée montre la paire `cotisations`↔`changement_coordonnees` (case > 0 ou marges faibles reportées) et un conseil actionnable non vide ; le cycle V2-5 (+6 exemples) produit une réduction mesurable sur la paire.

---

## 4. L4 — Atomicité : persister `failed`, pas retomber en `idle`

**Constat** : le comportement en creux est bon (pas de manifeste partiel, retrain suivant OK) mais l'état du job interrompu n'est pas persisté — après restart, le statut revient à `idle`, ce qui masque l'incident.

**Actions** :
1. Persister l'état du job (`running`, bot_id, phase, timestamp) sur disque au démarrage du train, le passer à `completed`/`failed` en fin.
2. Au boot du serveur : tout job trouvé en `running` est requalifié `failed` avec motif `interrupted` (+ log WARNING), le répertoire partiel est nettoyé (mécanique K3.4 déjà en place).
3. Étendre le test kill-worker existant : après restart, `GET /train/status` renvoie `failed`/`interrupted`, pas `idle` ; un nouveau train reste possible et repart propre.

**Critère d'acceptation** : rejouer V2-3 tel quel → statut `failed` explicite après restart, retrain suivant `completed`.

---

## 5. L5 — Latence manifeste : une méthodologie, pas deux chiffres

**Constat** : la contre-mesure indépendante passe largement (P50 26,3 / P95 34,6 ms) ; le chiffre du manifeste échoue (P95 63,8 ms). La mesure manifeste est prise immédiatement après l'entraînement, machine chargée (GC, caches froids, threads BLAS encore configurés pour le train) — elle mesure l'environnement, pas le modèle.

**Actions** :
1. Aligner la mesure manifeste sur le protocole de la contre-mesure : warm-up de 10 inférences non comptées, puis 100 inférences mesurées, après libération des ressources d'entraînement (et `torch.set_num_threads` ramené à la valeur runtime si le train l'a modifié).
2. Consigner dans le manifeste la méthodologie (warm-up, n, conditions) pour que V2-6 compare des mesures comparables.
3. Test : sur un modèle entraîné en CI, P95 manifeste et P95 d'une re-mesure indépendante divergent de < 30 % (le critère exact de V2-6).

**Critère d'acceptation** : manifeste post-train MGEN avec P95 ≤ 50 ms, écart avec la contre-mesure indépendante < 30 %.

---

## 6. L6 — V0-5 : appliquer K4.3 et clore le diagnostic 3,69/1,06

**Constat** : le rapport v0.3.4 a de nouveau mesuré V0-5 par `docker images` (3,69 Go) alors que K4.3 avait acté la mesure par `docker inspect` sur le digest (1,06 Go consigné en CE-3, sous la cible 1,6 Go). Le diagnostic K4.1 (history, tag flottant, décompressé WSL2) n'apparaît pas dans les artefacts.

**Actions** :
1. Exécuter le diagnostic K4.1 une bonne fois et l'archiver : `docker history --no-trunc` sur l'image de campagne, `docker images --digests` vs `inspect --format '{{.Size}}'` sur le même id `8aefddc…`, note sur l'environnement (Docker Desktop/WSL2 affiche la taille décompressée). L'hypothèse dominante — 3,69 Go = taille décompressée de la même image de 1,06 Go compressée — se confirme ou s'infirme en dix minutes.
2. Outiller pour rendre l'erreur impossible : script `tools/measure_image.sh <tag>` qui sort **une** taille (inspect sur digest) + verdict vs 1,6 Go ; l'intégrer au preflight (CE-3) et au mode d'emploi de V0-5 dans le protocole.
3. Si le diagnostic confirme l'artefact de mesure : consigner, V0-5 devient PASS mécanique — aucune « optimisation » d'image à faire (interdit n°4 de l'annexe B : ne pas corriger à l'aveugle).

**Critère d'acceptation** : une seule taille mesurée sur digest, ≤ 1,6 Go, identique en CE-3, preflight et V0-5 ; explication de l'écart archivée.

---

## 7. L7 — Calibration et boucle V3-7 : le protocole métier de la prochaine campagne

**Constat** (pas un item de code — la feuille de route V3 de la campagne v0.3.5) : le profil d'erreurs pointe la calibration avant le modèle. GNG-1 : 17 faux rejets sur 27 erreurs. GNG-2 : 16 rejets-au-lieu-d'escalade sur 19. Pièges T01–T06 : routes directes là où des clarifications inter étaient attendues. Symptômes convergents de seuils (`seuil_bas` trop haut → faux rejets ; écart top1/top2 pour clarification trop étroit → tranchage prématuré). GNG-3 inverse la contrainte : 9 routes métier directes hors-scope = échec aggravé, donc baisser `seuil_bas` aveuglément aggraverait GNG-3.

**Séquence imposée** (dans l'ordre, avec L1 livré au préalable) :
1. **Itération 1 — sweep C3** : `loko-eval --sweep seuil_haut=0.6:0.9:0.05,seuil_bas=0.3:0.6:0.05` (+ balayage de l'écart de clarification si paramétré) sur les 4 jeux. Choisir le point de Pareto GNG-1/GNG-2/GNG-3 (le sweep révélera si un point satisfait les trois seuils — c'est possible vu que GNG-3 a de la marge à 81 %). Figer les seuils dans la config versionnée, re-run complet des 4 jeux (règle R1.10). Aucun nouvel exemple à cette itération : isoler l'effet calibration.
2. **Itération 2 — exemples ciblés** (si GNG-1 ou pièges restent sous seuil) : exploiter `errors.csv` (enfin exploitable grâce à L1) — classer les erreurs résiduelles, ajouter des exemples de train ciblés sur les faux rejets récurrents et les pièges T01–T06 (formulations ambiguës services_en_ligne / coordonnées / cotisations). Retrain, re-run des 4 jeux.
3. **Itération 3 — réserve**, même mécanique sur les résidus.
4. **Butée** : si après 3 itérations GNG-1/GNG-2/pièges ne passent pas, retour au postulat métier (frontières d'intentions), conformément au protocole — pas d'itération 4.
5. Chaque itération remplit le tableau « Itérations V3-7 » du gabarit (action, GNG-1/2/3, pièges).

**Point de vigilance** : T13 (rejet attendu, clarification produite) et les 9 routes hors-scope de GNG-3 sont les contre-forces du sweep — les surveiller à chaque itération pour ne pas améliorer GNG-1 en dégradant GNG-3.

---

## 8. L8 — Discipline CE-1 : livrables hors worktree

**Constat** : le worktree sale au preflight venait des livrables eux-mêmes (`RAPPORT_…`, `PLAN_…`) — pas du code, mais la règle CE-1 est binaire.

**Actions** :
1. Décision de rangement, au choix (à trancher, une fois) : (a) déplacer rapports et plans de campagne dans `eval/campagne-R0R1/` déjà couvert par la procédure d'artefacts, ou (b) les committer systématiquement **avant** de poser le tag de campagne. Recommandé : (a) pour les rapports (artefacts de campagne), (b) pour les plans (documents de référence versionnés).
2. Ajouter au script de preflight un message d'aide listant les fichiers non clean pour trancher immédiatement (commit vs déplacement) au lieu de découvrir le BLOCKED en cours de route.

**Critère d'acceptation** : preflight v0.3.5 CE-1 PASS, `git describe` = tag exact sans `-dirty`.

---

## 9. Consignes pour la campagne v0.3.5

1. **Préparation** : L1–L6 + L8 mergés, tag `v0.3.5`, preflight 8/8 (CE-1→CE-8, taille par digest) → PASS intégral avant ouverture.
2. **Reprise depuis V0-1** (règle 4 : les correctifs touchent le moteur d'entraînement et l'évaluateur), protocole inchangé sur le fond ; précisions d'exécution actées : V0-5 par inspect/digest (L6), diff V3-6 sur `report.json` seul (`meta.json` hors périmètre, L1.3).
3. **V3 est le cœur de cette campagne** : dérouler L7 comme protocole d'itération, budgéter le temps d'analyse d'`errors.csv` à chaque itération. Objectif réaliste : GNG-1/GNG-2 aux seuils par calibration + 1 itération d'exemples ; les pièges (12/15) sont le point le plus incertain — chaque écart résiduel doit être commenté cas par cas comme l'exige V3-4.
4. Ne pas retoucher les CSV held-out ni committer pendant la campagne (annexe B).

## 10. Definition of done

1. L1–L6, L8 verts en CI (nouveaux tests : schéma `errors.csv`, parseur `expected_behavior` sur les 15 fixtures T01–T15, `report.json` déterministe, profil de train < 120 s, CV base avec confusion synthétique détectée, kill-worker → `failed`, mesure image sur digest).
2. Preflight v0.3.5 : 8/8 PASS, `git describe` propre.
3. Campagne rejouée depuis V0-1, rapport au gabarit, boucle V3-7 documentée itération par itération.
4. **Objectif de sortie** : G-0, G-1, G-1b, G-2 PASS, et G-3 PASS aux seuils ou, à défaut après 3 itérations, un dossier d'erreurs résiduelles suffisamment classé pour instruire le retour au postulat — plus jamais un chiffre GNG non opposable faute d'outillage.
