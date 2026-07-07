# 🎯 LOKO — Feuille de route de validation finale R0+R1 (post-campagne v0.3.6, protocole v2.0)

> **Version** : 1.0 — 6 juillet 2026
> **Entrée** : `RAPPORT_VALIDATION_R0_R1_LOKO_V2.md` (campagne v0.3.6, commit `dff31616`) — verdict NON VALIDÉS.
> **Objet** : document unique et exhaustif de **tout ce qui reste à faire** pour valider R0+R1 et ouvrir R2–R9. Il remplace tout plan de correction antérieur.
> **État de départ acté** : l'infrastructure a convergé (G-0 PASS pour la première fois, train 222 s, latence P95 28,5 ms, atomicité, reproductibilité stricte, sweep 3 axes opérationnel). R0 est à une ligne de log du PASS. Le sweep de 240 points a **falsifié l'hypothèse calibration** : aucun jeu de seuils n'atteint le triplet GNG — le plafond est dans le modèle et ses données d'entraînement, plus dans la couche de décision ni dans l'outillage.
> **Principe directeur** : il reste exactement **une cartouche d'ingénierie** (l'itération V3-7 jamais réellement engagée en six campagnes). Tout le reste est soit une correction bornée < 1 h, soit une retouche de protocole, soit — si la cartouche échoue — une décision métier sur le postulat. Ce document couvre les trois branches.

---

## 0. Vue d'ensemble — les 4 chantiers restants

| Chantier | Contenu | Effort | Responsable | Bloque |
|---|---|---|---|---|
| **W1** | Corrections bornées R0 : CE-1 (worktree), V1-4 (log CRITICAL) | < 1 h | Claude Code | G-1 |
| **W2** | Contre-épreuve du plateau : re-mesure V3 sur modèle non contaminé, seuils v0.3.5 | ~1 h, avant tout le reste | Pilote | Lecture correcte de l'état réel |
| **W3** | Retouches protocole v2.1 : sélection Pareto du sweep, V3 sur modèle V2-1, V2-5 sur bot jetable, 2 clarifications mineures | ~½ j (code sweep) + amendements | Claude Code + pilote | G-2, G-3 (mesures honnêtes) |
| **W4** | L'itération V3-7 réelle : enrichissement du train par verbatims réalistes, ciblé par les 28 erreurs classées | 2–4 j (dont production de données) | Claude Code + **métier** | G-3 — le verrou final |
| **W5** (conditionnel) | Retour au postulat métier si W4 échoue | Décision, pas ingénierie | Métier + pilote | — |

Ordre strict : **W2 d'abord** (il conditionne la lecture de tout le reste), puis W1+W3 en parallèle, puis campagne v0.3.7 intégrant W4. W5 n'est instruit que sur échec constaté de W4.

---

## 1. W1 — Solder R0 : deux corrections < 1 heure

R0 est fonctionnellement démontré depuis v0.3.5 (fail-fast : 503, zéro session créée, zéro `hors_perimetre`, publication intègre en 422, offline OK). Deux points le maintiennent artificiellement en FAIL :

### W1.1 — CE-1 : worktree définitivement propre
**Constat** : troisième campagne invalidée à l'entrée par des fichiers Markdown de gestion de projet (cette fois 5 **suppressions** suivies par Git, non committées).
**Actions** :
1. Committer la réorganisation documentaire (suppressions comprises) **avant** de poser le tag — décision de rangement déjà actée : rapports de campagne dans `eval/campagne-R0R1/` (artefacts), plans et protocoles versionnés normalement.
2. Ajouter au preflight l'affichage de `git status --porcelain` complet avec message d'aide (« committer ou déplacer avant tag ») — le preflight le détecte déjà, il doit maintenant rendre l'erreur impossible à ignorer avant d'avoir posé le tag.

**Critère** : `git describe --tags --dirty` == tag exact, `git status --porcelain` vide, au preflight de la campagne v0.3.7.

### W1.2 — V1-4 : log CRITICAL au boot
**Constat** : le comportement de sécurité est correct ; il manque uniquement le log `CRITICAL` identifiant le bot défaillant au démarrage (exigence du protocole : l'exploitant doit voir l'incident sans attendre la première requête).
**Actions** :
1. Au boot serveur : scan des bots publiés → pour chaque bot dont le modèle ne charge pas, log `CRITICAL` avec bot_id et code d'erreur (`classifier_l1 unavailable: …`), sans chemin disque. Le serveur démarre quand même (comportement actuel conservé — fail-fast par requête, pas crash du serveur multi-bots).
2. Test : suppression du modèle + restart → capture des logs de boot → assertion sur la présence du CRITICAL et l'absence de chemin disque.

**Critère** : rejouer V1-4 tel quel → les 4 attendus PASS, y compris le log au boot. **G-1 devient PASS sans réserve.**

---

## 2. W2 — Contre-épreuve : mesurer le vrai plateau avant de décider quoi que ce soit

**Pourquoi c'est le premier geste** : la campagne v0.3.6 affiche une régression (GNG-1 74→72, GNG-2 85,6→82,4, GNG-3 83→72, pièges 8→6) qui a deux explications méthodologiques candidates — le point de sweep retenu est un coin de grille aberrant, et V3 a mesuré le modèle post-V2-5 contaminé par 6 exemples touchant `hors_perimetre`. Si la régression est un artefact, l'état réel est un **plateau ~74/86/83** et W4 part de là ; si elle est réelle, il y a un problème plus profond à investiguer avant W4. Une heure de mesure évite de piloter à l'aveugle.

**Procédure** (hors campagne, purement diagnostique, artefacts archivés quand même) :
1. Reconstruire le bot de campagne, entraînement V2-1 **sans** l'ajout V2-5.
2. Rejouer V3-1→V3-4 aux seuils par défaut de la campagne v0.3.5.
3. Comparer au triplet v0.3.5 (74 / 85,6 / 83, pièges 8/15).

**Lecture** :
- Chiffres ≈ v0.3.5 → régression = artefact confirmé (coin de sweep + contamination V2-5). W3 corrige les deux causes, W4 part du plateau 74/86/83 avec ~11 points à gagner sur GNG-1 et ~4 sur GNG-2.
- Chiffres ≈ v0.3.6 (72/82/72) → régression réelle : suspendre W4, bissecter ce qui a changé entre les deux tags côté modèle/décision (le diff est petit : M1/M2/M3), corriger, puis revenir ici.

---

## 3. W3 — Protocole v2.1 : trois corrections de méthode + deux clarifications

La campagne v0.3.6 a révélé deux défauts de conception du protocole v2.0 (dont un le mien : la fonction de sélection du sweep) et l'exécutant a remonté deux ambiguïtés légitimes. Amendements pour v2.1 :

### W3.1 — Sélection du sweep : Pareto contraint, pas distance pondérée
**Constat** : le point retenu (haut 0.90 / bas 0.30 / écart 0.05) est un coin de grille — symptôme classique d'une fonction de distance dominée par un axe (ici la contrainte routes directes, écrasée à 2/100 en sacrifiant GNG-3 : 83→72, le modèle clarifie au lieu de rejeter).
**Actions** (code `loko-eval`, ~½ journée) :
1. Sélection en deux temps : (a) filtrer les points satisfaisant les **contraintes dures** (GNG-3 ≥ 80 % et routes directes ≤ 5) ; (b) parmi eux, maximiser lexicographiquement GNG-1 puis GNG-2 puis pièges. Si l'ensemble (a) est vide : reporter les 5 points les plus proches de chaque contrainte **sans en figer aucun automatiquement** — le pilote choisit et justifie.
2. Sortir la frontière de Pareto complète dans la grille (colonne `pareto=true`) pour rendre l'arbitrage visible.
3. Garde-fou coin de grille : si le point retenu est sur un bord de la grille, WARNING explicite (« optimum en bord — étendre la grille ou suspecter la fonction de sélection »).

### W3.2 — V3 mesure le modèle V2-1 ; V2-5 déporté sur bot jetable
**Constat** : mesurer les GNG sur le modèle post-V2-5 fait dépendre les chiffres du GO d'une démo d'outillage qui, en v0.3.6, a touché des exemples impliquant `hors_perimetre` juste avant de mesurer le rejet.
**Amendement** : V2-4/V2-5 s'exécutent sur un **bot jetable** dédié (clone du bot de campagne) ; le bot de campagne reste sur son train V2-1 figé, et **V3-0→V3-6 mesurent ce modèle-là**. Toute évolution du train du bot de campagne ne passe que par la boucle V3-7 tracée.

### W3.3 — V2-5 : critère de réduction réaliste
**Constat** : en v0.3.6, +6 exemples n'ont pas réduit le signal (8→8 confusions croisées, advice 2→2) — FAIL. Deux lectures possibles : les exemples ajoutés étaient mal ciblés, ou le critère « réduction mesurable » est trop binaire sur des petits effectifs (une case de CV k=5 sur 125+6 exemples a une variance élevée).
**Amendement** : V2-5 exige la réduction d'**au moins un** des deux signaux (case CV de la paire, ou nombre d'exemples à faible marge sur la paire), mesurée sur **3 seeds de CV moyennées** (le train reste déterministe ; seule la partition CV varie) ; les exemples ajoutés doivent être générés depuis la suggestion `advice` elle-même (c'est la boucle produit complète qu'on teste : détection → suggestion → ajout → amélioration). Si après cela le signal ne bouge toujours pas, c'est un vrai FAIL produit de la chaîne advice.

### W3.4 — Clarifications demandées par l'exécutant (anomalies de protocole v0.3.6)
1. **V0-4 (`npm audit`)** : acté — s'exécute dans un conteneur Node dédié sur le lockfile du frontend ; l'image runtime finale n'a pas à embarquer npm (c'est même souhaitable). Le protocole le dit désormais explicitement.
2. **Hash dataset + référence manifeste dans les rapports** : acté — le sidecar `V3_summary.json` est recevable pour v0.3.7, mais `loko-eval` doit embarquer ces champs nativement dans `report.json` (petit item de code, à faire avec W3.1 : c'est ce qui rend chaque chiffre opposable sans fichier annexe).

---

## 4. W4 — La cartouche finale : l'itération V3-7 qui n'a jamais eu lieu

**Le constat central après six campagnes** : la boucle d'amélioration métier n'a **jamais été engagée**. Aucune campagne n'a ajouté un seul exemple d'entraînement ciblé par l'analyse des erreurs. Le train est resté figé à 125 exemples propres (~14/classe) face à des held-out en verbatims réels — et le sweep a prouvé qu'aucun réglage de seuils ne comble cet écart. C'est ici, et uniquement ici, que se joue G-3.

### W4.1 — Analyse des erreurs (déjà à moitié faite)
Matière première disponible : `V3-1_errors_classified.csv` (28 erreurs classées), les erreurs GNG-2 (rejets au lieu d'escalade), les 9 commentaires de pièges. Produire la synthèse par pattern :
- **Frontière `services_en_ligne`↔`changement_coordonnees`** (T01/T02/T15 + faux rejets récurrents) : verbatims mêlant espace personnel et coordonnées.
- **`demande_conseiller` indirect** (l'essentiel des erreurs GNG-2) : formulations sans le mot « conseiller » (« je veux parler à quelqu'un », « on peut m'appeler ? »).
- **Bande de clarification** (T04/T05/T06) : paires `changement_coordonnees`/`cotisations` et `arret_travail`/`cotisations`/`justificatif_droits`.
- **Faux rejets GNG-1** : verbatims réels (fautes, tournures orales, contexte parasite) trop éloignés des exemples propres du train.

### W4.2 — Production des exemples (le vrai travail, avec le métier)
**Règle absolue** : les held-out ne sont **jamais** consultés pour rédiger, jamais utilisés en entraînement — on travaille à partir des *patterns* de W4.1, pas des verbatims d'évaluation.
1. **Volume cible** : passer de ~14 à **25–30 exemples/classe** (train ~125 → ~230–270), en priorisant les 4 patterns ci-dessus. C'est le levier dont l'effet est le plus documenté pour SetFit en few-shot.
2. **Nature des exemples** : verbatims **réalistes** — tournures orales, fautes courantes, formulations indirectes, contexte parasite (« bonjour, alors voilà, en fait… ») — rédigés avec quelqu'un qui connaît les vraies sollicitations adhérents (le métier), pas des paraphrases propres.
3. **Traçabilité** : chaque exemple ajouté est tagué par le pattern qu'il cible (amendement tracé du postulat §2, exigence V3-7).
4. **Budget temps de train** : ~250 exemples × contrastif SetFit restera sous les 300 s (le coût croît en O(n·iterations) paires ; à surveiller au profil, marge disponible : 222 s à 131 exemples).

### W4.3 — Exécution de l'itération (dans la campagne v0.3.7)
1. Retrain sur le train enrichi → V2 complet sur le nouveau modèle.
2. **Re-sweep V3-0** (les distributions de scores auront bougé) avec la sélection Pareto W3.1.
3. V3-1→V3-4 et V3-6 aux nouveaux seuils figés.
4. Si un ou deux critères échouent **de peu** (< 3 points) : une **seconde et dernière** itération d'exemples ciblés sur les erreurs résiduelles, même mécanique. C'est la butée du protocole (2 itérations max).

**Pronostic honnête** : l'objectif est +11 points GNG-1 et +4 GNG-2 depuis le plateau (si W2 le confirme). Un doublement du train avec des verbatims réalistes est le levier le plus puissant disponible, mais le résultat n'est pas garanti — c'est précisément pour ça que W5 doit être préparé en parallèle, pas découvert en cas d'échec.

---

## 5. W5 — La branche d'échec : retour au postulat métier (à préparer dès maintenant)

Si après W4 (2 itérations max) GNG-1/GNG-2/pièges ne passent pas, le protocole est formel : le problème est de **conception du périmètre**, pas d'implémentation, et aucune ressource d'ingénierie supplémentaire n'est justifiée. Pour ne pas perdre deux semaines le moment venu, préparer dès maintenant (½ journée, métier + pilote) :

1. **Hypothèses de révision candidates**, instruites par les patterns d'erreurs : fusion d'intentions difficiles à séparer en few-shot (`cotisations` absorbe-t-elle `justificatif_droits` ? `changement_coordonnees` doit-elle être un sous-motif de `services_en_ligne` ?) ; requalification de `demande_conseiller` en détection dédiée (mots-clés + modèle) plutôt qu'intention concurrente.
2. **Critère de déclenchement** : W5 s'ouvre si, après la 2e itération W4, il manque > 3 points sur un GNG ou > 2 pièges.
3. **Conséquence assumée** : réviser le postulat = re-figer les datasets held-out (les frontières changent) = les chiffres repartent de zéro. C'est le coût d'un périmètre honnête — le consigner noir sur blanc pour que la décision soit prise en connaissance.

---

## 6. Campagne v0.3.7 — séquence de validation finale

1. **Pré-campagne** : W2 (contre-épreuve) → lecture actée. W1 + W3 mergés, protocole v2.1 publié (amendements W3, annexe C mise à jour). W4.1/W4.2 : exemples produits et revus par le métier, taggés. Tag `v0.3.7` posé sur worktree clean, triple version vérifiée.
2. **Campagne** (protocole v2.1) : CE complet → V0 → V1 (confirmation, avec W1.2) → V2 sur train enrichi (V2-4/V2-5 sur bot jetable) → V3-0 sweep Pareto → V3-1→V3-6 → si nécessaire, itération 2 (dérogation tracée) → verdict.
3. **Sorties possibles** :
   - **G-0→G-3 PASS** → **R0+R1 VALIDÉS** → ouverture R2–R9 ; modèle, seuils et manifeste gelés ; tout retrain ultérieur rejoue V3.
   - **Échec marginal** (< 3 points / < 2 pièges) après itération 2 → arbitrage pilote : itération supplémentaire dérogatoire **ou** W5 — mais tracé, pas improvisé.
   - **Échec net** → W5, datasets re-figés, nouveau cycle court de validation sur le postulat révisé.

Rappel : pendant tout ce temps, le **développement** R2–R9 (ingestion/knowledge, dashboard, sécurité) avance en parallèle tant qu'il ne touche ni classifieur, ni décision, ni seuils, ni `loko-eval`. Seules les recettes et tout ce qui dépend de la qualité de routage attendent le PASS.

---

## 7. Definition of done globale

1. **W1** : rejouer V1-4 → PASS sans réserve ; preflight v0.3.7 CE-1 PASS.
2. **W2** : note de contre-épreuve archivée avec le triplet mesuré et la lecture actée (plateau ou régression).
3. **W3** : protocole v2.1 publié ; sweep Pareto + garde-fou bord de grille + hash/manifeste natifs dans `report.json` verts en CI ; V2-5 3-seeds testé.
4. **W4** : train enrichi taggé par pattern, ≥ 25 exemples/classe sur les classes en erreur ; itération(s) V3-7 documentée(s) au tableau du gabarit.
5. **Verdict v0.3.7** : soit R0+R1 VALIDÉS et R2–R9 ouverts, soit dossier W5 complet (patterns résiduels, hypothèses de fusion, coût du re-figeage) posé sur la table métier — dans les deux cas, **plus aucun sujet d'ingénierie R0/R1 ouvert**.
