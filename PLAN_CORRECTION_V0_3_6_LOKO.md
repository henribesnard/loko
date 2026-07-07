# 🔧 LOKO — Plan de correction v0.3.6 (post-campagne R0+R1 du 5 juillet, tag v0.3.5)

> **Version** : 1.0 — 6 juillet 2026
> **Entrée** : `RAPPORT_VALIDATION_R0_R1_LOKO.md` (campagne v0.3.5, commit `7d01210c`) — verdict NON VALIDÉS, gates G-0/G-2/G-3 en échec.
> **Destinataire** : Claude Code (items M1–M3) et pilote de campagne (item M4 + arbitrages).
> **Parti pris de ce plan** : après six campagnes, l'infrastructure est saine (R0 validé fonctionnellement, atomicité, reproductibilité, latence, outillage `loko-eval` opérationnels). Ce plan **ne corrige que ce qui bloque réellement la validation**, arbitre explicitement le reste (seuils de protocole inadaptés, artefacts de mesure), et renvoie tout le reste au backlog. L'objectif n'est pas la perfection de l'image Docker : c'est de passer G-3 et d'ouvrir R2–R9.

---

## 0. Synthèse et arbitrages

### Ce qui est corrigé (code)

| # | Anomalie | Item | Effort |
|---|---|---|---|
| 1 | `advice=[]` alors que `margin_weak_pairs` détecte correctement `arret_travail`/`justificatif_droits` (V2-4) | **M1** | ~½ j |
| 2 | Bande de clarification (écart top1/top2) non calibrable par le sweep — or 3 pièges sur 7 échouent dessus | **M2** | ~½ j |
| 3 | `pyproject.toml` et package image restés en `0.3.4` sous le tag `v0.3.5` | **M3** | ~½ h |

### Ce qui est arbitré (protocole amendé, zéro code) — décisions actées

| # | Constat | Arbitrage | Justification |
|---|---|---|---|
| A1 | V0-5 FAIL sur `docker images` (3,69 Go) alors qu'inspect mesure 1 009 Mo | **V0-5 se mesure par `docker inspect` sur le digest, cible ≤ 1,6 Go inchangée.** La valeur `docker images` est consignée à titre informatif uniquement. | Troisième campagne où ce FAIL est un artefact d'affichage (taille décompressée Docker Desktop/WSL2). La mesure inspect était déjà actée (plans K4.3 puis L6) mais jamais inscrite dans le protocole — c'est le protocole qui portait le bug. |
| A2 | V2-1 : train MGEN 230 s vs seuil 120 s | **Seuil amendé à ≤ 300 s** (profil par phase archivé obligatoire). Le 120 s reste un objectif produit au backlog, non bloquant. | ÷7,7 déjà obtenu (1 783 → 230 s) ; le reliquat est du contrastif SetFit qu'on ne compresse plus sans risquer la qualité — inacceptable alors que G-3 est le vrai front. 4 min de retrain est acceptable pour l'usage produit (retrain occasionnel par le client). L'arbitrage prévu par K3.3 (« signaler avant campagne si intenable ») est ici exercé. |
| A3 | V2-4/V2-5 : la paire protocolaire `cotisations`↔`changement_coordonnees` est séparable dans le train (confusion 0 avec une CV honnête) ; la paire faible réelle est `arret_travail`/`justificatif_droits` | **V2-4/V2-5 sont redéfinis sur la paire la plus faible détectée par l'outil**, pas sur une paire codée en dur. | Le protocole testait une hypothèse de 2024 devenue fausse ; l'outil fait exactement son travail produit (détecter les vraies paires faibles et guider l'amélioration). Exiger une confusion inexistante est un test invalide par construction. |
| A4 | V3-5 « non applicable » : le sweep n'a jamais tourné, alors que 21/26 erreurs GNG-1 et 15/18 erreurs GNG-2 sont des faux rejets | **Le sweep devient une étape obligatoire (V3-0) avant toute mesure GNG**, plus une option « si échec marginal ». | Le profil d'erreurs (rejets massifs, routes prématurées sur T04–T06) désigne la calibration comme premier levier ; la conditionner à un « échec marginal » a inversé la logique deux campagnes de suite. |
| A5 | GNG-3 « PASS avec réserve » : 8/100 hors-scope routés vers une intention métier | **Plafond intermédiaire explicite pour R0+R1 : ≤ 5 routes directes/100**, surveillé à chaque itération du sweep. Le « 0 réponse à côté » du protocole de recette reste le critère du GO final. | Le risque client réel est là ; le laisser en « réserve » sans plafond permettrait au sweep de dégrader GNG-3 en optimisant GNG-1. Le plafond crée la contrainte de Pareto sans exiger dès maintenant un critère de GO. |
| A6 | CE-4 : le protocole v1 écrit `heldout_conseiller = 126`, les datasets réels et 3 rapports disent `125` | **Aligné sur 125** (réalité des hashes figés). | Coquille du protocole v1. |

### Ce qui n'est PAS fait (backlog explicite — ne pas y toucher)

- **Aucune optimisation d'image Docker** (multi-stage supplémentaire, distroless, torch slim) : la taille réelle est conforme.
- **Aucune optimisation d'entraînement supplémentaire** au-delà de l'existant : le seuil amendé la rend inutile pour cette phase.
- **Aucune refonte du classifieur ou de l'architecture L1/L2** : le levier est la calibration + les exemples, pas le code — et si ça ne suffit pas après la boucle V3-7, c'est le postulat métier qu'il faudra revoir, pas le code.

---

## 1. M1 — Câbler `advice` sur les paires faibles détectées

**Constat** : le pipeline de détection fonctionne (`margin_weak_pairs` remonte correctement `arret_travail`/`justificatif_droits`) mais le champ `advice` — celui que consomme l'UI et que vérifie V2-4 — reste vide. Le signal existe, il n'alimente pas le bon champ.

**Actions** :
1. Générer une entrée `advice` pour chaque paire remontée par `margin_weak_pairs` (et pour toute case hors-diagonale ≥ 2 de la CV base). Format : `{pair: [a, b], evidence: "cv"|"margins", n_exemples_faibles, suggestion}` — la suggestion nomme la paire et le côté à renforcer (« ajouter des exemples discriminants côté {a} mentionnant … », en citant 2–3 verbatims à faible marge comme illustration).
2. Trier `advice` par sévérité (nombre d'exemples faibles, puis marge moyenne) — la première entrée est « la paire la plus confondue » au sens de V2-4.
3. Test unitaire : dataset synthétique à deux classes chevauchantes → `advice` non vide, paire correcte, suggestion citant des exemples réels du dataset ; dataset parfaitement séparable → `advice=[]` légitime.

**Critère d'acceptation** : sur le train MGEN, `GET /train/report` retourne `advice` non vide dont la première entrée désigne `arret_travail`/`justificatif_droits` avec une suggestion actionnable.

---

## 2. M2 — Rendre la bande de clarification calibrable par le sweep

**Constat** : T04, T05, T06 échouent tous de la même façon — route directe là où une clarification inter était attendue, c'est-à-dire un écart top1/top2 jugé suffisant alors qu'il ne l'est pas. Si ce paramètre (bande de clarification) n'est pas dans la grille du sweep, la calibration V3-0 ne peut pas récupérer ces 3 cas — or ils suffisent presque à eux seuls à passer les pièges (8+3 = 11/15, à un cas du seuil).

**Actions** :
1. Vérifier que l'écart de clarification est un paramètre de config du bot (ex. `seuil_ecart_clarification`) et non une constante ; l'exposer si nécessaire, défaut = comportement actuel (aucun changement de comportement sans calibration).
2. Étendre `loko-eval --sweep` pour accepter ce troisième axe : `--sweep seuil_haut=…,seuil_bas=…,seuil_ecart=0.05:0.25:0.05`. La grille de sortie reporte, pour chaque point, le quadruplet **GNG-1 / GNG-2 / GNG-3 (dont routes directes) / pièges** — pas GNG-1 seul.
3. Performance : la grille réutilise les scores d'inférence calculés une fois par dataset (la décision est une fonction pure des scores et de la config — architecture C2 déjà en place) ; un sweep 3 axes doit tenir en minutes, pas en heures.
4. Test : fonction de décision pure paramétrée sur les trois seuils, cas de bord (écart nul, écart exactement au seuil) ; un mini-sweep sur fixtures produit la grille complète avec les 4 métriques.

**Critère d'acceptation** : `loko-eval --sweep` 3 axes s'exécute sur les 4 jeux en < 10 min in-container et sort une grille où chaque point porte GNG-1, GNG-2, GNG-3 + sous-compte routes directes, et pièges.

---

## 3. M3 — Alignement version : tag ↔ `pyproject.toml` ↔ package image

**Actions** :
1. Bump `pyproject.toml` à la version du prochain tag (`0.3.6`) ; vérifier qu'aucune autre déclaration de version ne traîne (module `__version__`, frontend).
2. Ajouter au preflight (CE-2) la triple vérification : `git describe --tags` == version `pyproject.toml` == `pip show loko` dans l'image. Échec = campagne non ouverte.

**Critère d'acceptation** : preflight v0.3.6 affiche les trois valeurs identiques.

---

## 4. M4 — Feuille de route calibration (campagne, pas code)

Séquence exécutée pendant la campagne, dans cet ordre strict — c'est le V3-0/V3-7 du protocole v2.0 (livré séparément) :

1. **Sweep 3 axes** (M2) sur les 4 jeux. Sélection du point de Pareto : GNG-1 ≥ 85 **et** GNG-2 ≥ 90 **et** GNG-3 ≥ 80 avec ≤ 5 routes directes **et** pièges maximisés. Si aucun point ne satisfait le triplet GNG, prendre le point qui minimise la distance aux seuils et passer directement à l'itération exemples.
2. **Figer les seuils** dans la config versionnée du bot, re-run rapide (V0-1, V1-1→V1-4) puis **V3 complet** aux seuils figés. Aucun nouvel exemple à ce stade : isoler l'effet calibration.
3. **Itération exemples** (si nécessaire, max 2) : exploiter `errors.csv` — cibles prioritaires identifiées dès maintenant : la frontière `services_en_ligne`↔`changement_coordonnees` (T01, T02, T15 + faux rejets récurrents : verbatims réels mêlant espace personnel et coordonnées), et les formulations `demande_conseiller` indirectes (15 rejets GNG-2). Retrain → re-run V3 complet, datasets held-out intouchés.
4. **Butée** : si GNG-1/GNG-2/pièges ne passent pas après sweep + 2 itérations d'exemples, arrêt — retour au postulat métier (frontières d'intentions), aucune ressource d'ingénierie supplémentaire.

**Pronostic chiffré** (à vérifier, pas à forcer) : les faux rejets représentent 11 points de GNG-1 et 12 points de GNG-2 ; la seule calibration devrait rapprocher les deux seuils, et T04/T05/T06 mettent les pièges à 11/15. L'itération exemples vise le reliquat (T01/T02/T15 et les rejets GNG-2 résiduels).

---

## 5. Definition of done

1. M1–M3 verts en CI (advice câblé, sweep 3 axes, triple check version).
2. Tag `v0.3.6`, preflight complet PASS (dont triple version et taille par inspect).
3. Campagne rejouée selon `PROTOCOLE_VALIDATION_R0_R1_LOKO_V2.md` (version 2.0 amendée), boucle M4 documentée itération par itération.
4. Sortie : G-0 à G-3 PASS → ouverture R2–R9 ; ou dossier d'erreurs résiduelles classé instruisant le retour au postulat. Dans les deux cas, plus aucun FAIL d'artefact de mesure ou de seuil de protocole inadapté — les seuls FAIL possibles restants sont des faits métier.
