# 🤖 LOKO Bot Service Client — Spécification du Parcours (Cadrage V1)

> **Version** : 1.0
> **Date** : 2 juillet 2026
> **Statut** : Cadrage validé
> **Base** : Fork du projet RAGKit Desktop (LOKO) existant
> **Cas de référence** : remplacement d'un callbot Odigo mono-intention (contexte MGEN)

---

## 1. Positionnement et périmètre

### 1.1 Objectif

Permettre à une entreprise de configurer, tester et déployer un **chatbot de service clientèle** (selfcare) en self-serve : configuration via l'application LOKO, exposition via un **mode serveur** (endpoints API + widget web embarquable).

### 1.2 Périmètre V1

- **Canal** : chatbot web (widget + API). Le vocal (callbot) est hors périmètre V1, mais l'architecture doit le rendre possible (minimisation des appels LLM).
- **Escalade** : fonction mockée en V1, avec contrat d'interface défini (§8).
- **LLM de génération** : provider API (démonstration de latence faible). Souveraineté totale (GPU on-prem) en option ultérieure.

### 1.3 Problèmes de référence à résoudre (retour d'expérience Odigo)

| # | Problème constaté | Réponse par construction |
|---|---|---|
| 1 | Le bot répond à côté, ne clarifie pas avant de chercher | Clarification structurelle avant retrieval : seuils de confiance + sous-motifs (§4) |
| 2 | Comportement imprévisible sur deux parcours identiques | Machine à états déterministe, templates fixes, SetFit, température 0 (§2) |
| 3 | Le RAG ramène des documents sans lien avec la requête | Tagging des documents par intention/sous-motif + retrieval filtré (§5) |
| 4 | FAQ web (iframes, contenu dynamique) impossible à ingérer | Connecteur crawl avec rendu JS et suivi d'iframes (§6) |
| — | Latence | Budget par étape, classification locale ~50 ms, streaming (§9) |

---

## 2. Principe directeur : déterminisme structurel

**Tout ce qui est structurel est du code déterministe. Le LLM ne génère que le contenu de la réponse.**

- Le parcours conversationnel est une **machine à états explicite**, pas un agent LLM.
- Les messages système (accueil, clarification, enquête, fin, escalade) sont des **templates fixes**, jamais générés.
- La classification d'intention est un modèle **SetFit local**, pas un prompt.
- Le seul appel non déterministe : la **génération de la réponse**, à température 0, sur contexte filtré, streamée.

Conséquences : comportement auditable et reproductible (argument commercial n°1), latence minimale, coût par conversation minimal.

---

## 3. Machine à états du parcours

```
                    ┌────────────────────────────────────────────┐
                    │  Sorties transverses (à tout moment) :      │
                    │  • Demande explicite de conseiller → ESCALADE│
                    │  • Timeout d'inactivité → message de clôture │
                    └────────────────────────────────────────────┘

ACCUEIL (template, annonce le périmètre des intentions)
   │
   ▼
CLASSIFICATION INTENTION (SetFit niveau 1)
   ├─ score ≥ seuil_haut ──────────────────────────► (suite)
   ├─ seuil_bas ≤ score < seuil_haut ─► CLARIFICATION INTER-INTENTIONS
   │                                     (choix fermé entre les 2 candidates)
   └─ score < seuil_bas ou intention "hors_périmètre"
                        ─► message hors périmètre → reformulation (1x) ou ESCALADE
   │
   ▼
CLASSIFICATION SOUS-MOTIF (SetFit niveau 2, si l'intention en déclare)
   ├─ sous-motif confiant ──► pas de question, suite directe
   ├─ aucun sous-motif confiant ─► CLARIFICATION INTRA-INTENTION
   │      (choix fermé : libellés des sous-motifs + « Autre »)
   │      • clic sur option → routage direct
   │      • réponse texte libre → re-classification niveau 2
   │        (requête initiale + réponse concaténées)
   │      • « Autre » → retrieval sur toute l'intention ;
   │        si scores trop bas → ESCALADE
   └─ Règle d'or : MAXIMUM 1 clarification par demande
   │
   ▼
RETRIEVAL FILTRÉ (§5) → GÉNÉRATION LLM (streaming, temp. 0)
   │
   ▼
ENQUÊTE DE SATISFACTION (template : « Ai-je répondu à votre demande ? »)
   ├─ Satisfait ─► « Avez-vous une autre demande ? »
   │       ├─ Oui → retour CLASSIFICATION (compteur max_demandes)
   │       └─ Non → MESSAGE DE FIN → fin de conversation
   └─ Non satisfait ─► MESSAGE D'ESCALADE (template avec {temps_attente})
                       + appel fonction d'escalade (mock) → fin
```

### Paramètres exposés

| Paramètre | Défaut suggéré | Description |
|---|---|---|
| `seuil_haut` | 0.75 | Confiance intention : enchaînement direct |
| `seuil_bas` | 0.45 | En dessous : hors périmètre |
| `seuil_sous_motif` | 0.60 | Confiance niveau 2 pour sauter la clarification |
| `max_clarifications` | 1 | Par demande |
| `max_demandes` | 5 | Demandes successives dans une conversation |
| `timeout_inactivite` | 300 s | Avant message de clôture |
| `retrieval_min_score` | à calibrer | En dessous : fallback ou escalade |

---

## 4. Configuration des intentions (2 niveaux)

### 4.1 Intention (niveau 1)

- **Définition** : texte décrivant ce que couvre l'intention.
- **Exemples** : minimum 8 (few-shot SetFit), l'UI encourage 15-20.
- **Intention système obligatoire `hors_périmètre`** : exemples de demandes que le bot ne doit PAS traiter (classe de rejet explicite — sans elle, SetFit sur-classifie).
- **Intention système `demande_conseiller`** : pré-entraînée, sortie transverse vers l'escalade.

### 4.2 Sous-motifs (niveau 2, optionnels par intention)

- Libellé + courte définition + ~5 exemples chacun.
- Exemple : `service_en_ligne` → { identifiants_perdus, mot_de_passe_oublié, compte_bloqué, problème_affichage, première_connexion }.
- Section repliable « Sous-motifs (optionnel) » dans le formulaire d'intention — non imposé.
- Discrimination évaluée **uniquement entre sous-motifs de la même intention** (espace de décision réduit → fiable avec peu d'exemples).

### 4.3 Entraînement et évaluation immédiats

- À la fin de la saisie : entraînement SetFit + cross-validation sur les exemples.
- Affichage d'une **matrice de confusion simplifiée** avec conseils actionnables
  (« 'remboursement' et 'suivi_de_dossier' se confondent, ajoutez des exemples discriminants »).
- **Boucle d'amélioration continue** : depuis les logs de production, une requête mal classée → un clic → devient exemple d'entraînement.
- Suggestion automatique de sous-motifs : si une intention accumule feedbacks négatifs ou scores de retrieval dispersés, le dashboard suggère de la scinder.

---

## 5. Bases de connaissances et retrieval

### 5.1 Tagging des documents

- Chaque document est taggé (multi-tag) à une ou plusieurs **intentions**, et optionnellement à des **sous-motifs** précis.
- Tag intention = visible par tous les sous-motifs de l'intention.
- Réutilise le système de métadonnées existant de LOKO (domaine, confidentialité, etc.).
- **Filtre de confidentialité par canal** : le bot public ne voit que les documents « publique ».

### 5.2 Retrieval filtré (filtrage dur, pas de pondération en V1)

1. Recherche restreinte aux chunks du **sous-motif** détecté (ou de l'**intention** si pas de sous-motif / option « Autre »).
2. **Requête de retrieval = concaténation** « requête d'origine — libellé du sous-motif »
   (ex. « j'ai un problème avec mon compte — mot de passe oublié »).
   Rationale : garde le vocabulaire client (BM25) + ancre le sujet (vectoriel). ✅ Décision actée.
3. **Fallback configurable** : si < N chunks au-dessus de `retrieval_min_score` → élargir au corpus de l'intention, puis escalade si toujours insuffisant.
4. Le poids/boosting par intention est une optimisation V2 (moins prévisible, plus dur à régler).

### 5.3 Indicateur de couverture

- Dans l'UI : « l'intention 'résiliation' n'a que 2 documents associés » — signal qualité avant mise en production.

---

## 6. Connecteur FAQ web (feature de premier plan)

Cas de référence : https://www.mgen.fr/aide-et-contact (sous-pages en iframes contenant les articles).

- Suivi des `src` d'**iframes**.
- **Rendu JavaScript** (navigateur headless) pour accordéons et contenus dynamiques.
- Découverte via **sitemap.xml** + crawl de profondeur configurable.
- **Un document par article**, avec URL source en métadonnée → le bot **cite le lien de l'article** dans sa réponse.
- **Re-synchronisation planifiée** (la FAQ évolue), branchée sur l'ingestion incrémentale existante.

---

## 7. Messages templatisés

Bibliothèque de templates éditables, pré-remplis par profil de ton, avec variables :
`{nom_bot}`, `{intentions_gérées}`, `{temps_attente}`, `{lien_escalade}`…

| Template | Rôle | Note |
|---|---|---|
| Présentation | Accueil + **annonce du périmètre** | Réduit mécaniquement le hors-scope |
| Clarification inter-intentions | « Votre demande concerne-t-elle A ou B ? » | Choix fermé |
| Clarification intra-intention | Liste des sous-motifs + « Autre » | Boutons dans le widget |
| Hors périmètre | Redirection / reformulation | |
| Enquête de satisfaction | « Ai-je répondu à votre demande ? » | |
| Autre demande | « Avez-vous une autre demande ? » | |
| Fin de conversation | Clôture | |
| Mise en relation (escalade) | « Je vous passe un conseiller, temps d'attente moyen : {temps_attente} min. » | ✅ Décision actée |
| Timeout | Clôture pour inactivité | |

---

## 8. Escalade (mock V1, contrat défini)

**Déclencheurs** : enquête « non satisfait » (escalade immédiate, pas de boucle de ré-essai — décision actée), demande explicite de conseiller, hors périmètre après reformulation, retrieval insuffisant après fallback.

**Contrat de la fonction d'escalade** (mock en V1, mais interface figée) :

```json
{
  "conversation_id": "...",
  "transcript": [...],
  "intention": "service_en_ligne",
  "sous_motif": "mot_de_passe_oublié",
  "motif_escalade": "insatisfaction | demande_explicite | hors_perimetre | retrieval_insuffisant",
  "horodatage": "..."
}
```

**Retour attendu** : `{ "temps_attente_estime_min": 4 }` (injecté dans le template de mise en relation).

Le **transfert du contexte** au conseiller (transcript + qualification déjà faite) est un argument de vente : le client ne se répète pas.

---

## 9. Budget latence

Contrainte structurante. Le design minimise les appels LLM par construction.

| Étape | Technologie | Latence cible |
|---|---|---|
| Classification intention (niv. 1) | SetFit local (CPU) | ~20-50 ms |
| Classification sous-motif (niv. 2) | SetFit local (CPU) | ~20-50 ms |
| Messages templatisés (accueil, clarifications, enquête, fin) | Aucun LLM | ~0 ms |
| Retrieval filtré | Index réduit par intention | < 200 ms |
| Reranking | **Désactivé par défaut** (le filtrage fait le travail) | 0 ms |
| Génération LLM | **API provider**, streaming, temp. 0, max_tokens 500-800 | Premier token < 2 s, complet < 6-8 s |

**SLO affiché dans le dashboard** : latence décomposée par composant (réutilise le monitoring existant).

Principe : une clarification templatisée à ~0,1 s qui évite une mauvaise réponse LLM à 5 s est un gain net pour le client (anti-pattern Odigo inversé : qualifier en millisecondes avant de générer).

---

## 10. Parcours de configuration (wizard bot)

| Étape | Contenu |
|---|---|
| 1. Projet bot | Nom, canal (widget/API), langue, ton |
| 2. Intentions | Définition + exemples (min 8), sous-motifs optionnels, entraînement + matrice de confusion |
| 3. Bases de connaissances | Sources (dossier local, connecteur FAQ web), tagging par intention/sous-motif, indicateur de couverture |
| 4. Parcours | Paramètres de la machine à états (seuils, max clarifications/demandes, timeout) |
| 5. Messages | Templates éditables par état |
| 6. Simulation & publication | Playground avec **trace complète** (intention + score, chunks + pertinence, latence par étape), puis génération clé API + snippet widget |

Le playground avec trace visible est le différenciateur diagnostic : quand le bot répond à côté, on voit **pourquoi** (classification ? retrieval ? génération ?) — ce qu'Odigo ne donne pas.

---

## 11. Décisions actées

| Sujet | Décision |
|---|---|
| Réaction à « non satisfait » | Message d'escalade templatisé + escalade immédiate (pas de ré-essai) |
| LLM de génération V1 | Provider API (démonstration de latence faible) |
| Clarification intra-intention | Sous-motifs SetFit niveau 2, choix fermé, max 1 clarification |
| Requête de retrieval après clarification | Concaténation requête d'origine + libellé du sous-motif |
| Filtrage documents/intention | Filtrage dur en V1 ; pondération = V2 |
| Escalade V1 | Mockée, contrat d'interface figé |
| Canal V1 | Chatbot web uniquement ; architecture compatible callbot |

## 12. Points ouverts (à instruire ensuite)

- Choix du provider LLM API et du modèle (arbitrage latence/coût/qualité, hébergement UE possible ?).
- Modèle d'embedding SetFit pour le français (ex. base multilingue vs modèle FR dédié).
- Design du widget web (streaming, boutons de choix fermé, feedback 👍/👎).
- Architecture du mode serveur : headless/Docker, authentification, concurrence des conversations.
- Métriques cibles du dashboard bot : taux de selfcarisation par intention, taux d'escalade par motif, taux de clarification.
