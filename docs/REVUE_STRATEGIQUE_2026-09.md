# LOKO — revue d'état et veille technologique

**Date de décision : 17 septembre 2026**  
**Horizon recommandé : 6 semaines avant nouvelle décision d'investissement**  
**Verdict : investir de façon conditionnelle, pas poursuivre à l'identique**

## 1. Résumé exécutif

LOKO possède un socle logiciel plus avancé qu'un prototype : moteur conversationnel déterministe, classification locale, RAG, garde-fous, multi-tenant, gestion de clés LLM, observabilité, évaluation et interface d'administration. Le dépôt contient 627 fichiers suivis et environ 45 700 lignes Python. Son avantage défendable n'est cependant **pas** de produire un chatbot généraliste : cette fonction est devenue une commodité chez les éditeurs de support et les fournisseurs de modèles.

L'investissement reste justifié uniquement si LOKO est repositionné comme **couche de contrôle auditable et déployable en environnement contraint** : décisions déterministes, données et modèles maîtrisés, compatibilité avec plusieurs fournisseurs, campagnes d'évaluation reproductibles et escalade humaine. Il ne faut pas tenter de battre les plateformes généralistes sur le nombre de connecteurs ou sur la qualité conversationnelle brute.

La décision proposée est un **GO conditionnel et plafonné** : un cycle de six semaines doit prouver simultanément une demande client et une qualité minimale. Sans deux pilotes payants ou lettres d'intention crédibles, et sans passage des seuils d'évaluation, le bon choix est de mettre le produit en maintenance plutôt que de poursuivre l'investissement.

## 2. Méthode et limites

Cette revue croise :

1. le code et la configuration présents sur la branche au 17 septembre 2026 ;
2. les résultats de campagne et le tableau de bord maintenus dans le dépôt ;
3. une veille sur les offres concurrentes, les standards de risque et la réglementation ;
4. des contrôles locaux reproductibles (`ruff`, collecte `pytest`, inventaire Git).

### Limite de fraîcheur de la veille

L'accès HTTP de l'environnement d'analyse a retourné `401` pour le moteur de recherche et `403` pour les pages externes. Les sources primaires ci-dessous sont donc une **liste de contrôle documentée**, mais leur contenu et les tarifs doivent être revalidés dans un navigateur avant tout engagement financier. Aucun prix concurrent n'est utilisé dans le calcul de décision. Cette réserve empêche de présenter la veille comme une photographie tarifaire certifiée au 17 septembre 2026, mais ne change pas les tendances structurelles ni les constats tirés du dépôt.

## 3. État réel du produit

### 3.1 Acquis solides

| Axe | État observé | Valeur stratégique |
|---|---|---|
| Orchestration | FSM, clarification, rejet, escalade et interruption SSE | Comportement explicable et testable |
| IA hybride | SetFit local, calibration, score OOD, retrieval et génération LLM optionnelle | Réduit la dépendance à un fournisseur unique |
| Sécurité | Anti-injection, détection de fuite, SSRF, CSRF/CSP, PII, rôles et quotas | Pertinent pour les secteurs contrôlés |
| Exploitation | Prometheus, Alertmanager, audit, analytics, backup/restore, maintenance | Base exploitable, au-delà de la démonstration |
| Cycle de vie | Publication, rollback, manifestes et vérification d'intégrité | Traçabilité rare dans les petits produits IA |
| Produit | Console React, wizard, playground, dashboard, widget | Parcours administrateur déjà matérialisé |
| Qualité | Jeux gelés, tests adverses, rejouabilité et protocole de campagne | Actif différenciant si les gates finissent par passer |

Le dépôt démontre en particulier une séparation nette entre API publique, administration, sécurité, classifieur, génération, connaissance, analytics et évaluation. Il intègre déjà plusieurs fonctions souvent repoussées après le MVP : BYO key, filtrage anti-SSRF, publication atomique, rollback, quotas, anonymisation et monitoring.

### 3.2 Signaux de maturité insuffisante

1. **La qualité métier n'est pas validée.** La campagne v1.3.4 est non opposable. Les résultats documentés restent sous les quatre objectifs : GNG-1 à 81 % pour une cible de 85 %, GNG-2 à 86,4 % au meilleur compromis OOD pour une cible de 90 %, GNG-3 à 77 % pour une cible de 80 %, et pièges à 10/15 pour une cible de 12/15.
2. **L'amélioration OOD ne résout pas le compromis structurel.** Elle apporte +1,8 point de moyenne harmonique, sans point satisfaisant toutes les gates. Ajouter des seuils ne corrigera probablement pas un espace de représentation trop pauvre.
3. **Les données sont trop petites pour porter seules la différenciation.** Le corpus d'entraînement de référence ne contient que 145 exemples, et le rapport E2 attribue explicitement une partie du plafond à ce volume.
4. **Les performances ne sont pas contractualisables.** Le dernier protocole signale 573 s d'entraînement et 205 ms de P95 sur une machine non déclarée. Il faut une machine de référence et des mesures de bout en bout.
5. **L'état affiché dérive.** `STATUS.md` annonce environ 690 tests, alors que la collecte locale voit 515 tests avant 12 erreurs d'import ; un comptage par fonctions trouve 661 tests. Le statut doit être généré, non maintenu manuellement.
6. **La validation locale n'est pas prête à l'emploi.** L'environnement courant n'a pas les extras serveur (`fastapi`, `httpx`, `prometheus_client`) ni `pytest-asyncio`. Ce n'est pas un défaut du code, mais cela augmente le coût d'onboarding.
7. **Le stockage fichier/SQLite et les caches processus limitent l'échelle horizontale.** Cette architecture est cohérente pour des pilotes isolés, pas encore pour un SaaS multi-réplicas à forte charge.
8. **La version produit est ambiguë.** Le backend est en 1.3.4 et le package desktop en 0.1.0. Même si cela peut être intentionnel, le discours de release doit distinguer clairement protocole, backend et interface.

### 3.3 Dette à traiter avant croissance

| Priorité | Dette | Décision |
|---|---|---|
| P0 | Gates métier non atteintes | Enrichir avec données pilotes ; ne pas lancer une nouvelle optimisation de seuils seule |
| P0 | Absence de preuve commerciale dans le dépôt | Obtenir deux design partners avec cas d'usage et métriques convenues |
| P0 | Campagne non opposable | Exécuter une campagne propre sur environnement déclaré |
| P1 | Persistance/caches locaux | Documenter le plafond mono-instance ; ne migrer qu'après preuve de charge |
| P1 | Statut/test count divergent | Générer un rapport CI machine-readable |
| P1 | Conformité incomplètement matérialisée | Produire registre des risques, politique de conservation et dossier de transparence |
| P2 | Versions frontend/backend séparées | Formaliser une matrice de compatibilité plutôt que forcer un numéro unique |

## 4. Veille technologique et concurrentielle

### 4.1 Ce qui est devenu une commodité

- Les suites de support vendent déjà des agents IA intégrés aux tickets, bases de connaissance, handoff humain et analytics. Intercom Fin et Zendesk AI sont les comparables directs à surveiller via leurs pages officielles de [tarification Intercom](https://www.intercom.com/pricing) et de [tarification Zendesk](https://www.zendesk.com/pricing/).
- Les API de modèles incorporent désormais recherche, appels d'outils, traces et briques d'agents. La page officielle OpenAI sur les [outils de construction d'agents](https://openai.com/index/new-tools-for-building-agents/) illustre la baisse du coût de construction d'un agent généraliste.
- Les frameworks open source couvrent graphes d'exécution, mémoire, interruptions et human-in-the-loop. [LangGraph](https://docs.langchain.com/oss/python/langgraph/overview) représente cette catégorie. Une FSM seule ne constitue donc plus un fossé concurrentiel.
- Le RAG de base, les widgets web et le support multilingue sont attendus. Ils restent nécessaires, mais ne justifient pas à eux seuls une plateforme propriétaire.

**Conséquence :** un positionnement « créez votre chatbot FAQ » n'est plus investissable sans distribution exceptionnelle ou verticalisation forte.

### 4.2 Ce qui prend de la valeur

- **Évaluation continue et observabilité.** Les agents deviennent plus autonomes ; la capacité à rejouer, comparer, tracer et bloquer une régression devient plus importante que l'orchestration elle-même.
- **Contrôle de fournisseur.** Le BYO LLM et une interface compatible OpenAI permettent arbitrage coût/confidentialité et recours à des modèles locaux. Il faut préserver cette neutralité plutôt que coupler LOKO à un modèle vedette.
- **Déploiement souverain ou isolé.** Le mode hors réseau, la classification locale et les manifestes vérifiés répondent à un besoin que les offres SaaS généralistes couvrent moins naturellement.
- **Sécurité applicative spécifique aux LLM.** L'OWASP maintient un [Top 10 pour les applications LLM](https://owasp.org/www-project-top-10-for-large-language-model-applications/). Les gardes anti-injection, contrôle de sortie et documents canari de LOKO vont dans le bon sens, à condition de les relier explicitement à un modèle de menaces.
- **Gouvernance du risque.** Le [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework) structure les activités de gouvernance, cartographie, mesure et maîtrise. LOKO possède déjà une partie de la couche « mesure », mais doit produire les artefacts organisationnels associés.
- **Conformité européenne.** Le calendrier, les responsabilités et les exceptions doivent être vérifiés sur la page officielle de la Commission consacrée au [cadre réglementaire de l'IA](https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai). La transparence envers l'utilisateur, la supervision humaine, la journalisation et la documentation sont des exigences de conception à traiter comme des fonctions produit, pas comme une annexe juridique.

### 4.3 Lecture « construire ou acheter »

| Besoin | Acheter/intégrer | Continuer LOKO |
|---|---|---|
| FAQ standard, faible contrainte, CRM déjà équipé | Oui | Non |
| Temps de mise en production minimal | Oui | Non |
| Parcours stricts et décisions auditables | Partiellement | Oui |
| Hébergement isolé/souverain | Rarement | Oui |
| Choix ou changement fréquent de modèle | Partiellement | Oui |
| Preuve reproductible avant publication | Variable | Oui, si les gates sont réparées |
| Très grand catalogue de connecteurs | Oui | Non, intégrer plutôt que reconstruire |

## 5. Thèse d'investissement recommandée

### Positionnement

> **LOKO est une couche de contrôle conversationnelle pour organisations qui ne peuvent pas déléguer leurs décisions, leurs traces et leurs données à une boîte noire SaaS.**

Le client cible n'est pas « toute entreprise ayant un support ». Il doit réunir au moins trois contraintes : parcours délimités, exigences d'audit ou de résidence, besoin d'escalade humaine, coût élevé d'une mauvaise réponse, ou volonté d'utiliser plusieurs modèles.

### Ce qu'il faut cesser de financer

- le rattrapage horizontal des suites de support ;
- de nouveaux connecteurs sans pilote demandeur ;
- l'optimisation répétée de seuils sur les mêmes 145 exemples ;
- une couche agentique généraliste alors que des SDK spécialisés existent ;
- le passage prématuré à une architecture distribuée ;
- les fonctions marketing ou billing avant validation de la qualité et de la demande.

### Ce qu'il faut financer

1. **Données verticales réelles**, labellisées avec deux partenaires, en séparant entraînement, validation et test aveugle.
2. **Évaluation comme produit** : gates par client, rapport signé, comparaison de release, coûts et latences, export d'audit.
3. **Interface de modèles stable** : capacités déclarées, timeouts, coûts, fallback explicite et tests de contrat.
4. **Sécurité démontrable** : threat model OWASP, red-team rejouable, conservation, effacement et preuves de non-divulgation.
5. **Packaging de déploiement isolé** : procédure de mise à jour, SBOM, sauvegarde testée, matrice des versions et objectifs de reprise.

## 6. Plan de validation en six semaines

### Semaine 1 — preuve de marché

- sélectionner un vertical et un seul problème coûteux ;
- conduire au moins 8 entretiens avec décideurs ou opérateurs ;
- obtenir 2 design partners avec données accessibles et sponsor nommé ;
- fixer avant développement le coût de l'erreur, le volume et le processus de reprise humaine.

### Semaines 2–3 — données et baseline honnête

- constituer au moins 500 requêtes représentatives par pilote, dont cas hors périmètre et attaques ;
- geler un test aveugle jamais utilisé pour choisir modèle ou seuils ;
- comparer LOKO à deux baselines : RAG génératif simple et solution du marché/stack existante ;
- mesurer qualité, couverture, taux d'escalade, coût par résolution et P95 de bout en bout.

### Semaines 4–5 — durcissement utile

- corriger d'abord les classes révélées par les données pilotes ;
- matérialiser dossier de risque, politiques PII/rétention et rapport de release ;
- tester restauration, interruption fournisseur, saturation, rotation de clé et rollback ;
- faire relire le parcours de supervision humaine par les opérateurs pilotes.

### Semaine 6 — décision

| Gate | GO | STOP / maintenance |
|---|---|---|
| Demande | 2 pilotes payants ou lettres d'intention avec budget, échéance et sponsor | Intérêt verbal seulement |
| Qualité | Toutes les gates historiques atteintes **et** aucun incident critique sur test aveugle | Compromis GNG inchangé |
| Valeur | Gain mesuré d'au moins 20 % sur coût ou délai du processus ciblé | Parité avec la solution existante |
| Exploitation | P95 et disponibilité conformes au SLO du pilote sur machine déclarée | Résultat non reproductible |
| Différenciation | Un partenaire choisit LOKO pour auditabilité, souveraineté ou contrôle multi-modèle | Choix motivé seulement par le prix |

Les cinq gates sont cumulatives. En cas d'échec, conserver le dépôt, les jeux d'évaluation et le moteur déterministe en maintenance ; ne pas engager une refonte générale.

## 7. Décision financière

### Recommandation

**Oui, il est encore pertinent d'investir, mais uniquement sous forme d'une tranche bornée de découverte et de validation.** Le patrimoine technique justifie de ne pas arrêter immédiatement. En revanche, la campagne non validée et la commoditisation des agents interdisent un investissement de croissance.

La prochaine tranche doit financer **la preuve**, pas davantage de surface fonctionnelle. Le jalon de six semaines transforme la question abstraite « LOKO est-il techniquement intéressant ? » en deux preuves falsifiables : des clients paient pour son contrôle/auditabilité, et le système atteint leurs seuils sur données aveugles. À défaut, l'option rationnelle est l'arrêt actif du développement produit.

## 8. Registre des hypothèses à revalider

| Hypothèse | Niveau de confiance | Test |
|---|---|---|
| L'auditabilité/souveraineté déclenche un budget | Faible à moyen | 2 engagements écrits |
| 500 exemples réels suffisent à franchir les gates | Faible | Courbe d'apprentissage par pilote |
| L'architecture mono-instance suffit aux pilotes | Moyen | Test de charge au volume contractuel |
| BYO LLM réduit effectivement le coût ou le risque | Moyen | Comparatif sur mêmes requêtes |
| La couche déterministe réduit les incidents critiques | Moyen | Baseline A/B sur test aveugle |
| Les sources concurrentes et réglementaires sont à jour | Non vérifié dans cet environnement | Revue navigateur, juridique et achats |

## 9. Dépendances pour reproduire les contrôles

Ne pas modifier `requirements.txt`. Installer le projet avec ses extras déclarés dans `pyproject.toml`, par exemple les extras **server** et **dev** ; ajouter l'extra **ml** uniquement pour les campagnes classifieur, et **crawler** pour les tests de collecte web. L'environnement utilisé pour cette revue ne disposait pas des dépendances serveur et asyncio nécessaires à la collecte complète.
