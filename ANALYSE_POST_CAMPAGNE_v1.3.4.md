# Analyse post-campagne — v1.3.4 (runner 1.1.0) — 2026-08-01

**Version 1.1** — révisée après dépouillement des artefacts (V0-1, manifeste, seuils, distribution des erreurs GNG-3). La v1.0 raisonnait sur le seul rapport de campagne ; les corrections de raisonnement qu'elle a subies sont signalées en clair.

**Verdict runner (calculé) : NON VALIDE** — CE 9/9, G-1 **PASS 4/4 (éliminatoire)**, G-1b **PASS 1/1**, G-0 4/5, G-2 3/6, G-3 **2/7**.

> ⚠️ **CAMPAGNE NON OPPOSABLE** — mode diagnostic. L'**itération V3-7 2/2 n'est pas consommée** (compteur : 1/2). Le FAIL G-3 n'est pas définitif. Aucun chiffre de ce rapport n'est un résultat de recette.

---

## 1. Acquis maintenus

- **G-1 et G-1b PASS** : boot + health, garde no-mock au runtime, fail-fast du loader, CRITICAL au boot, service sous `--network none`. Le socle d'intégrité runtime ne régresse pas.
- **CE 9/9** : datasets figés vérifiés (6 fichiers depuis le lot B, hashes conformes), intersection train/held-out **vide**.
- **V2-3 atomicité PASS**, **V3-5 / V3-6 PASS** : manifeste gelé (`fcecf51ec47f9b1a…`), rejeu déterministe strictement identique. Le déterminisme structurel tient.
- **Lot A livré et vérifié** : `temperature: 0.6` et bloc `calibration` présents au manifeste ; parité runtime/éval en place ; les deux tests de calibration sont **PASS**.

---

## 2. Comparaison v1.3.3 → v1.3.4

| Métrique | Cible | v1.3.3 | v1.3.4 | Δ |
|---|---|---|---|---|
| GNG-1 métier | ≥ 85 % | 81,0 % | **81,0 %** | 0,0 |
| GNG-2 conseiller | ≥ 90 % | 88,8 % | **87,2 %** | −1,6 |
| GNG-3 hors-scope | ≥ 80 % | 80,0 % | **72,0 %** | **−8,0** |
| Pièges | ≥ 12/15 | 9/15 | **9/15** | 0 |
| Train | ≤ 300 s | 463 s | **573 s** | +110 s |
| P95 | ≤ 50 ms | 106 ms | **205 ms** | +99 ms |
| Gate G-3 | — | 3/7 | **2/7** | −1 |

**Seuils employés** : `haut=0,85 / bas=0,50 / écart=0,00` — **identiques à ceux de v1.3.3**, issus de la configuration pré-existante du bot et **non sélectionnés par le sweep** (V3-0 : `selected: null`).

---

## 3. Résolution des trois questions ouvertes de la v1.0

| Question v1.0 | Réponse (artefacts) |
|---|---|
| §4.1 — Avec quels seuils les GNG ont-ils été mesurés ? | **Seuils pré-existants**, non optimisés. V3-0 a échoué et le runner est retombé silencieusement sur la configuration du bot. |
| §4.3 — La calibration est-elle active ? | **Oui.** `T = 0,60`, ECE 3,14 % → 0,68 %, tests PASS. |
| V0-1 — Nature des échecs | **12 échecs** (6 fails, 6 errors) : fixtures `Intent` sous le minimum de 8 exemples, incompatibilité asyncio Python 3.12, emitter en lecture seule. **Aucun** lié à la calibration. Outillage/tests, pas produit fonctionnel. |

---

## 4. Analyse révisée

### 4.1 🔴 Correction majeure : T = 0,60 **aiguise** la confiance

La v1.0 posait une alternative binaire : *soit la calibration est inactive (L1), soit elle est active et la sur-confiance n'est pas la cause des pièges (L2)*. **Cette alternative était mal posée**, et la conclusion « L2 s'applique » doit être retirée.

L'hypothèse du lot A était que le modèle était **trop confiant** sur T04/T05 (scores 0,98) et qu'il fallait **aplatir** les probabilités — donc `T > 1`. La minimisation de l'ECE a retenu **`T = 0,60`**, soit l'inverse : le modèle était globalement **sous-confiant**, et la calibration a rendu tous les scores **plus tranchés**.

> **La calibration n'a donc jamais testé l'hypothèse des pièges. Elle a poussé dans le sens opposé.**

Le fil-tendeur A4 (« si les pièges ne bougent pas, la cause n'est pas la sur-confiance ») était valide **sous l'hypothèse T > 1**. Avec T = 0,60, il ne conclut rien. La question de la sur-confiance sur T04/T05 reste **entière**.

### 4.2 H3 — la régression GNG-3 est un effet mécanique de la calibration

Les seuils étant identiques à v1.3.3, **H2 (effet de seuils) tombe**. Et la distribution des 28 erreurs GNG-3 — dispersée sur 5 classes, `help_contact` 36 %, `help_documents` / `help_billing` / `help_transfer` 18 % chacune — **affaiblit fortement H1** : si M3 (+20 exemples `help_documents`) était en cause, les erreurs se concentreraient sur `help_documents`, ce qui n'est pas le cas.

**Hypothèse H3, désormais dominante.** Deux mécanismes, tous deux conséquences directes de `T = 0,60` :

1. **Moins de rejets.** Le rejet se déclenche sur `score < seuil_bas = 0,50`. Aiguiser pousse tous les top-1 vers le haut ; des hors-scope qui tombaient sous 0,50 passent désormais au-dessus et sont routés ou clarifiés au lieu d'être rejetés.
2. **Moins de clarifications, plus de routes directes.** L'aiguisage creuse l'écart top1 → top2 ; des cas auparavant en zone grise basculent en route directe. Ceci touche aussi le second critère de V3-3 (routes directes ≤ 5).

H3 explique quatre observations d'un seul mécanisme :

| Observation | Explication par H3 |
|---|---|
| GNG-3 −8 pts | Inflation globale des scores → moins de rejets |
| Erreurs **dispersées sur 5 classes** | Effet global et non spécifique à une classe → signature attendue d'un déplacement de seuil effectif |
| GNG-1 inchangé | Les items in-scope étaient déjà au-dessus des seuils : l'aiguisage ne change pas leur verdict |
| GNG-2 −1,6 | Effet de second ordre, même mécanisme |

**Conséquence de méthode, et c'est la leçon centrale de cette campagne** : *mesurer un modèle calibré avec des seuils choisis avant calibration n'est pas valide.* La calibration déplace la distribution des scores ; les seuils sont définis **sur** cette distribution. Ils sont couplés et ne peuvent pas être figés séparément. C'est précisément ce que V3-0 devait garantir — son échec a laissé passer un repli silencieux qui invalide l'interprétation des chiffres GNG.

**Contre-test H3** (1 h, hors campagne) : même modèle, `T = 1,0`, mêmes seuils. Si GNG-3 remonte vers 80 %, H3 est confirmée et la baseline réelle du projet n'est pas 72 % mais ~80 %.

### 4.3 Une tension à ne pas masquer : les pièges auraient dû se dégrader

Si H3 est exacte, l'aiguisage aurait dû **empirer** la plupart des pièges connus : T04/T05 (déjà routés à tort, encore plus tranchés), T06 (clarification à 2 voies au lieu de 3 — l'aiguisage réduit encore les candidats), T13 (attendu `reject`, déjà en clarification — risque de bascule en route). Or le total reste à 9/15.

Deux lectures possibles, **non tranchées** :
- **recomposition** : certains pièges basculent FAIL→PASS pendant que d'autres font l'inverse, à somme nulle ;
- **H3 incomplète** : le mécanisme n'agit pas uniformément selon les régions de l'espace de scores.

**Test discriminant** : comparer l'**identité** des 6 pièges en échec entre v1.3.3 et v1.3.4, pas leur nombre. Un total stable qui masque une recomposition est une information, un total stable à composition identique en est une autre.

> *Correction assumée* : j'avais avancé en discussion que T15 (échec à 0,49, juste sous `seuil_bas`) repasserait probablement en PASS. C'est inexact — sa classe top-1 était `help_contact` alors que l'attendu est `route:help_account` ; l'aiguisage le ferait passer de `reject` à `route:help_contact`, donc toujours FAIL. L'aiguisage change le **type** de décision, pas la **cible**.

### 4.4 V2-4 / V2-5 : troisième signal indépendant sur `hors_perimetre`

Inchangé par rapport à la v1.0, et non affecté par H3. Le cycle d'amélioration a désigné en autonomie la paire de plus faible F1 — **`hors_perimetre` → `help_leave`** — y a ajouté +10 exemples, ré-entraîné, et la précision a **baissé** (0,911 → 0,900).

Trois signaux convergents obtenus par trois voies indépendantes : erreurs GNG-1 (aspiration vers `hors_perimetre` : 12/22 puis 11/19), erreurs GNG-2 (6/14 des `parler_conseiller` manqués), et l'outil `advice` en autonomie. **L'enrichissement sur l'axe `hors_perimetre` ne converge pas** : il déplace l'erreur sans la réduire.

Point théorique qui renforce E2 : le *temperature scaling* est une transformation **monotone** — il ne modifie jamais l'ordre des candidats. Si T04 route vers `help_contact` avec `help_billing` loin derrière, aucun réglage de température **ni de seuil** ne fera émerger la clarification attendue. Le défaut est dans la **représentation**, pas dans la géométrie de décision.

### 4.5 Temps : toujours non interprétable

Train +24 %, latence +94 %, alors que M4 et M5 visaient l'inverse. La contre-mesure V2-6 affiche un **écart de 0 %** (contre 78 % en v1.3.2) : la méthode est désormais cohérente, la valeur de 205 ms est fiable *pour cette exécution*. Mais la **machine de référence n'est pas déclarée** ; ces mesures ne sont comparables à aucune campagne antérieure. Défaut de protocole, pas résultat.

---

## 5. État de la boucle corrective V3-7

| Itération | Statut |
|---|---|
| 1/2 | consommée (v1.3.3) |
| 2/2 | **disponible — non consommée** |

**Recommandation maintenue et renforcée : suspendre.** La baseline actuelle (72 % GNG-3) est probablement un artefact de couplage calibration/seuils. Engager la dernière itération sur une baseline fausse la dépenserait sans information.

---

## 6. Actions, dans l'ordre

| # | Action | Effort | Débloque |
|---|---|---|---|
| 1 | Relâcher `ECART_MIN` à 0,00 et **re-sweeper avec la calibration active** | 1 h | Baseline légitime |
| 2 | **Contre-test H3** : T = 1,0, mêmes seuils, re-mesure GNG-3 | 1 h | Confirme/infirme H3 |
| 3 | Comparer l'**identité** des 6 pièges en échec v1.3.3 vs v1.3.4 | 20 min | §4.3 |
| 4 | Ajouter la **température comme axe du sweep**, ou imposer un re-sweep systématique après calibration | ½ j | Corrige la cause de fond |
| 5 | Faire échouer V3-0 de façon **bloquante** : plus de repli silencieux sur les seuils du bot | 1 h | Protocole |
| 6 | Corriger les 12 échecs V0-1 (fixtures 8 exemples, asyncio 3.12, emitter) | ½ j | G-0 |
| 7 | Déclarer la **machine de référence** en conditions d'entrée | 15 min | V2-1, V2-6 |
| 8 | Corriger les 3 défauts de reporting du runner | 1 h | Qualité |

🛑 **Points d'arrêt humains** : (a) itération V3-7 2/2 — *recommandation : suspendre* ; (b) ouverture du **lot E2**, à instruire **après** l'action n°1 afin que la règle de décision E2-A1 (≥ 84 %) s'applique à une baseline valide.

---

## 7. Ce que cette campagne a réellement appris

Elle n'a pas mesuré la qualité du modèle v1.3.4 — les seuils employés n'étaient plus les siens. Elle a mis au jour un **défaut de protocole** qui aurait faussé toutes les campagnes suivantes : la calibration et les seuils de décision sont couplés, et rien n'empêchait de les figer indépendamment. C'est un résultat de valeur, obtenu au prix d'un run diagnostic non opposable — exactement l'usage pour lequel ce mode existe.

---

*Analyse rédigée sans requalification (interdits n°8 et n°9). Les verdicts de gates sont ceux calculés par le runner. Les hypothèses de la §4 sont marquées comme non établies et assorties de leur test discriminant. Les corrections apportées à la v1.0 de cette analyse sont signalées explicitement.*
