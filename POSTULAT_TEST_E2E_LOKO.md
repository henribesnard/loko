# 🧪 LOKO Bot Service Client — Postulat & Protocole de test de bout en bout

> **Version** : 1.0 — 3 juillet 2026
> **Base** : dataset MGEN fourni (6 062 verbatims, 39 intentions, fr_FR) + spec de cadrage v1.0 + spec dev
> **Objectif** : valider LOKO de bout en bout (wizard → entraînement → connaissances → parcours → runtime → dashboard) sur un cas réaliste, avec des verbatims réels du callbot Odigo à remplacer.

---

## 1. Postulat de test

**Le bot** : « Assistant MGEN », chatbot selfcare web (widget + API), langue FR, ton neutre, adossé à une base de connaissances issue du crawl de la FAQ https://www.mgen.fr/aide-et-contact (cas de référence du connecteur `faq_web_crawler`).

**Le pari testé** : plutôt que les 39 intentions du callbot d'origine, on configure un **échantillon de 7 intentions métier + 2 intentions système**, choisi pour exercer *chaque branche* de la machine à états :

| Critère de représentativité | Intention(s) qui le porte(nt) |
|---|---|
| Intention à **sous-motifs** (clarification intra, exemple canonique de la spec §4.2) | `services_en_ligne` |
| **Paire confondable** → clarification inter-intentions + matrice de confusion | `cotisations` ↔ `changement_coordonnees` (le RIB/prélèvement est dans les deux) |
| **Deuxième paire confondable** sur le mot « attestation » | `justificatif_droits` ↔ `arret_travail` ↔ `cotisations` |
| Vocabulaire **très distinctif** (classe facile, contrôle positif) | `teletransmission_noemie` |
| Intention **volumineuse et hétérogène** (candidate à la suggestion de scission) | `arret_travail` |
| Intention citée par la spec pour l'**indicateur de couverture** | `resiliation` |
| **Sortie transverse** vers l'escalade (pré-entraînée, à valider) | `demande_conseiller` (validée avec les 126 verbatims `parler_conseiller` du dataset) |
| **Classe de rejet** explicite | `hors_périmètre` (construite avec les verbatims des 32 intentions NON retenues : dentaire, optique, décès, cure thermale, accident, habitat, maternité…) |

Ce choix est le cœur du postulat : les intentions non retenues ne sont pas perdues, elles deviennent le **jeu d'exemples `hors_périmètre`** et le **jeu de test du rejet**. C'est exactement le scénario réel d'un déploiement progressif (on selfcarise 7 motifs, le reste part en escalade propre).

**Paramètres de parcours** : défauts de la spec (`seuil_haut` 0.75, `seuil_bas` 0.45, `seuil_sous_motif` 0.60, `max_clarifications` 1, `max_demandes` 5, `timeout` 300 s, `retrieval_min_score` 0.35, `retrieval_min_chunks` 2). Ils seront calibrés en phase P3.

---

## 2. Configuration des intentions retenues

Format : définition (à saisir dans le wizard, étape 2) + verbatims d'entraînement extraits tels quels du dataset (15–18 par intention, conformément à l'encouragement UI ; minimum 8 respecté partout).

### 2.1 `services_en_ligne` — avec 5 sous-motifs

**Définition** : « L'adhérent rencontre un besoin lié à son espace personnel en ligne ou à l'application MGEN/Ameli : création, connexion, identifiants, mot de passe, compte bloqué, dysfonctionnement du site ou de l'appli. »

**Exemples niveau 1 (15)** :
- accès à mon espace personnel
- accès à mon compte MGEN
- accès espace perso
- accès à mon compte en ligne
- MGEN connexion au compte Ameli
- accès à mon application MGEN
- accès compte personnel sur mon site MGEN
- accès à mon espace adhérent
- accès à l'espace personnel internet de ma fille
- accès en ligne
- accès site mutuelle
- accès à mon espace client
- accès au compte Ameli point FR
- accès à mon espace internet
- accéder au compte internet

**Sous-motifs** (libellé, définition courte, 5 exemples chacun) :

| Sous-motif | Définition | Exemples (dataset) |
|---|---|---|
| `mot_de_passe_oublie` | Mot de passe perdu, oublié ou à renouveler | mot de passe perdu · mot de passe oublié compte client · récupération de mon mot de passe · renouveler mon mot de passe · je souhaite récupérer mon mot de passe pour accéder à mon compte Ameli |
| `identifiants_perdus` | Identifiant/login de connexion perdu ou inconnu | identifiant de connexion oublié · je veux mes identifiants Ameli · problème d'identifiant · recevoir mes codes identifiant · je voudrais un code d'accès au compte Ameli |
| `compte_bloque` | Compte ou espace personnel bloqué/verrouillé | compte bloqué · compte MGEN bloqué · débloquer mon compte personnel · espace adhérent bloqué · connexion espace personnel bloqué |
| `premiere_connexion` | Création ou activation initiale du compte | activer mon compte MGEN · création d'un compte en ligne · comment créer un compte Ameli · activation de mon espace client · activation compte mutuelle |
| `probleme_technique` | Dysfonctionnement du site/appli (erreur, page qui ne s'affiche pas) | connexion impossible sur le site · erreur de connexion · espace personnel qui ne fonctionne pas · dysfonctionnement de mon espace personnel en ligne · impossible d'accéder à mon compte Ameli |

### 2.2 `justificatif_droits`

**Définition** : « L'adhérent demande un document attestant de ses droits ou de sa couverture : attestation de droits, attestation d'affiliation à la sécurité sociale, attestation d'assuré social, carte de tiers payant, attestation pour un ayant droit. »

**Exemples (16)** : attestation de droits · attestation MGEN · attestation d'affiliation à la sécurité sociale · attestation CPAM · attestation d'assuré social · attestation de carte vitale · attestation d'ayant droit · attestation de droits de la sécurité sociale · attestation d'ouverture de droits à la sécurité sociale · attestation d'assurance maladie · aide pour la carte tiers payant · attestation MGEN pour ma fille · attestation de droits en urgence · attestation de couverture sociale · attestation de droits perdue · attestation avec la date d'effet

### 2.3 `arret_travail`

**Définition** : « L'adhérent a une demande liée à un arrêt de travail, un congé maladie ou l'invalidité : déclaration de l'arrêt, indemnités et allocations journalières, complément/maintien de salaire, attestation de salaire ou de paiement des indemnités. »

**Exemples (16)** : arrêt de travail · arrêt de maladie · comment déclarer un arrêt de travail · allocation journalière · indemnités journalières [attesté : allocations journalières] · allocation journalière pour arrêt de travail prolongé · complément de salaire en arrêt maladie · comment activer le maintien de salaire · arrêt maladie passage à demi-traitement · allocation longue maladie · attestation de salaire à remplir · attestation indemnité journalière · attestation à remplir pour le versement de l'ijss · allocation d'invalidité · compensation perte salaire · autorisation de sortie pendant un congé maladie

### 2.4 `cotisations`

**Définition** : « L'adhérent a une question sur ses cotisations mutuelle/prévoyance : montant, calcul, augmentation, échéancier, paiement, prélèvement de la cotisation, contestation. »

**Exemples (16)** : connaître le montant de ma cotisation · calcul de mes cotisations · augmentation des cotisations · comprendre mes cotisations · appel de cotisation mutuelle · comment effectuer le paiement de mes cotisations · comprendre mon échéancier · cotisation mutuelle au prélèvement automatique · comprendre le prélèvement sur mon salaire · contestation cotisation · changement du montant de ma cotisation · calcul montant de la cotisation conjoint · attestation de paiement des cotisations · concernant le prélèvement de la mutuelle · comprendre le mode de calcul des cotisations · connaître le coût de la mutuelle

### 2.5 `changement_coordonnees`

**Définition** : « L'adhérent veut modifier ses coordonnées personnelles dans son dossier : adresse postale, adresse email, numéro de téléphone, RIB/coordonnées bancaires pour les remboursements. »

**Exemples (16)** : changement d'adresse après déménagement · actualiser mon adresse postale · changement d'adresse de domicile · besoin de changer mon RIB · changement de RIB pour les remboursements · ajouter un RIB · changement d'adresse et de RIB · changement RIB assurance maladie · changement de IBAN · actualiser mon adresse email · besoin de changer d'adresse courriel · changement d'adresse courriel · adresse postale erronée · changement coordonnées bancaires familiale · changement d'adresse dans mon dossier · changement de coordonnées personnelles

### 2.6 `teletransmission_noemie`

**Définition** : « L'adhérent a une demande sur la télétransmission Noémie entre la sécurité sociale et la mutuelle : mise en place, activation, annulation/déconnexion, fonctionnement, lien informatique CPAM-mutuelle. »

**Exemples (15)** : comment mettre en place la télétransmission Noemie · activer le lien Noemie · bénéficier de la télétransmission · annuler la télétransmission · arrêter la télétransmission · déconnexion du service Noemie · connexion Noemie · explications fonctionnement Noemie · comment se fait la télétransmission entre le mutuelle et la sécu · est-ce que le lien Noemie est créé avec ma nouvelle mutuelle · codes de télétransmission · déconnecter la mutuelle MGEN de ma sécurité sociale · au sujet des télétransmissions · comment faire une télétrans · contrat Noemie

### 2.7 `resiliation`

**Définition** : « L'adhérent veut résilier son contrat mutuelle ou prévoyance, connaître la procédure ou les délais de résiliation, annuler une résiliation, ou obtenir une attestation/un justificatif de résiliation. »

**Exemples (15)** : comment résilier la MGEN · demande de résiliation de contrat mutuelle · procédure de résiliation · délai de résiliation · conditions de résiliation mutuelle · courrier résiliation mutuelle · attestation de résiliation · annuler ma résiliation · où en est la résiliation de mon contrat · demande résiliation prévoyance · information sur la résiliation d'un bénéficiaire · pouvoir résilier ma mutuelle · changement de mutuelle · justificatif résiliation mutuelle obligatoire · effectuer une résiliation

### 2.8 `hors_périmètre` (intention système obligatoire)

Construite avec des verbatims réels des intentions **non retenues** — c'est la classe de rejet qui empêche SetFit de sur-classifier (spec §4.1). 16 exemples couvrant des univers variés :

- adresse pour envoyer un devis dentaire *(dentaire)*
- remboursement pour une prothèse dentaire [attesté : aide pour le remboursement pour une prothèse dentaire] *(dentaire)*
- achat de lentilles de contact *(optique)*
- changer les verres *(optique)*
- comment déclarer un décès *(deces)*
- bénéficiaire capital décès *(deces)*
- agrément pour une cure thermale *(cure_thermale)*
- déclaration accident de travail *(accident)*
- déclarer un accident corporel *(accident)*
- activer un contrat logement *(habitat)*
- accord préalable pour une prescription médicale de transport *(transport)*
- accusé réception de ma déclaration de grossesse *(maternite)*
- achat de fauteuil roulant remboursement *(pec_soins_courants)*
- adhérer à une complémentaire santé *(adhesion_affiliation)*
- adresse postale de la MGEN *(contact)*
- prise en charge hospitalisation *(hospitalisation, formulation générique)*

### 2.9 `demande_conseiller` (intention système pré-entraînée)

Rien à saisir (modèle embarqué, spec dev §7). Le dataset fournit en revanche un **jeu de validation en or** : les 126 verbatims `parler_conseiller` (« Je ne veux pas parler à un robot », « Je veux avoir un interlocuteur », « J'ai besoin de parler à un être humain »…). Objectif : ≥ 90 % détectés comme sortie transverse.

---

## 3. Base de connaissances et tagging

1. **Source 1 — connecteur FAQ web** : crawl de `mgen.fr/aide-et-contact` (sitemap + profondeur 3, rendu JS, suivi d'iframes). Attendu : un document par article, `source_url` en métadonnée.
2. **Tagging** : chaque article FAQ est taggé vers une des 7 intentions (édition en masse). Les articles « mot de passe », « créer mon compte »… sont taggés au sous-motif précis de `services_en_ligne`.
3. **Cas de couverture volontairement dégradé** : ne tagger que **2 documents** sur `resiliation` → l'indicateur de couverture doit lever l'alerte (« l'intention 'resiliation' n'a que 2 documents associés »), reproduisant l'exemple de la spec §5.3.
4. **Filtre de confidentialité** : ajouter 1 document interne marqué « confidentiel » taggé `cotisations` → il ne doit **jamais** sortir dans le bot public.

---

## 4. Jeu de test held-out (jamais utilisé à l'entraînement)

| ID | Verbatim (réel, dataset) | Attendu |
|---|---|---|
| T01 | « je souhaiterais débloquer mon compte Ameli » | `services_en_ligne` / `compte_bloque`, sans clarification |
| T02 | « modification mot de passe » | `services_en_ligne` / `mot_de_passe_oublie`, sans clarification |
| T03 | « accès à mon compte mutuelle MGEN » | `services_en_ligne`, sous-motif incertain → **clarification intra** (5 boutons + « Autre ») |
| T04 | « RIB coordonnées bancaires » | Ambigu `changement_coordonnees` / `cotisations` → **clarification inter** attendue (ou routage direct assumé, à tracer) |
| T05 | « changement de banque pour les prélèvements de cotisations » | Zone grise assumée : observer le score, la clarification inter est la bonne réponse produit |
| T06 | « attestation de paiement » | Ambigu `arret_travail` / `cotisations` / `justificatif_droits` → clarification inter entre les 2 meilleures |
| T07 | « attestation de droits MGEN » | `justificatif_droits` direct |
| T08 | « complément de salaire arrêt longue maladie » | `arret_travail` direct |
| T09 | « est-ce qu'il y a une télétransmission entre vous et la mutuelle » | `teletransmission_noemie` direct (contrôle positif) |
| T10 | « comment résilier mon ancienne mutuelle » | `resiliation` direct |
| T11 | « Je préfère parler à un humain » | Sortie transverse → **ESCALADE** motif `demande_explicite` |
| T12 | « déclarer un accident de ski » | `hors_périmètre` → template hors périmètre, 1 reformulation |
| T13 | « bilan bucco-dentaire détartrage » | `hors_périmètre` ; si l'utilisateur reformule encore hors scope → ESCALADE motif `hors_perimetre` |
| T14 | « Noemie » (verbatim d'un seul mot) | `teletransmission_noemie` — robustesse aux entrées ultra-courtes |
| T15 | « la référence iban et le numéro de carte vitale ne sont pas reconnus » | Cas piège (IBAN + carte vitale, vrai label `services_en_ligne`) : observer, calibrer |

---

## 5. Protocole de test complet (phases P0 → P9)

### P0 — Installation & création du bot (wizard étape 1)
Créer le bot « Assistant MGEN » (canal `both`, langue `fr`, ton `neutre`). **Critère** : config persistée dans `~/.loko/bots/{id}/config.json`, statut `draft`, le produit RAG desktop existant reste intact.

### P1 — Intentions, entraînement, matrice de confusion (étape 2)
1. Saisir les 7 intentions + `hors_périmètre` du §2. Vérifier la **validation bloquante min 8 exemples** (tenter de sauver `resiliation` avec 5 exemples → refus).
2. Lancer l'entraînement. **Critères** : job < 2 min CPU, progression affichée, matrice de confusion rendue.
3. **Attendus sur la matrice** : confusion visible entre `cotisations` et `changement_coordonnees` (vocabulaire RIB/prélèvement partagé) avec conseil actionnable « ajoutez des exemples discriminants » ; `teletransmission_noemie` quasi parfaite.
4. Appliquer le conseil (ajouter 3 exemples discriminants de chaque côté, ex. « contestation de prélèvement » côté cotisations, « changement d'agence bancaire » côté coordonnées), ré-entraîner, vérifier l'amélioration.
5. Entraîner le niveau 2 de `services_en_ligne` ; vérifier que la discrimination n'est évaluée qu'entre ses 5 sous-motifs.
6. Latence d'inférence mesurée : **20–50 ms CPU** par appel, tracée.

### P2 — Base de connaissances (étape 3)
1. Lancer le crawl FAQ (aperçu des pages découvertes avant ingestion). **Critères** : contenus d'iframes rattachés à l'article parent, accordéons JS extraits, un document par article, `source_url` présent.
2. Tagging en masse ; vérifier l'**alerte de couverture** sur `resiliation` (2 docs).
3. Vérifier que le document « confidentiel » est indexé mais exclu du périmètre bot.
4. Re-synchronisation : modifier une fixture locale → seul l'article modifié est ré-ingéré (diff par hash).

### P3 — Parcours conversationnel (playground, étape 6)
Dérouler les 15 cas du §4 dans le playground, trace ouverte. Pour chaque tour, vérifier dans la trace : état FSM, scores par classe, chunks + scores, latence par étape.

Scénarios de parcours complets à scripter en plus :
- **S1 nominal** : T02 → réponse générée avec **citation du lien FAQ** → enquête « Oui » → « Avez-vous une autre demande ? » → « Non » → template fin → FIN.
- **S2 clarification intra puis texte libre** : T03 → boutons → répondre en texte libre « c'est pour le mot de passe » → re-classification sur `requête initiale + réponse` → routage `mot_de_passe_oublie`.
- **S3 clarification « Autre »** : T03 → clic « Autre » → retrieval sur toute l'intention ; puis variante avec corpus vidé → ESCALADE `retrieval_insuffisant`.
- **S4 règle d'or** : provoquer une clarification inter (T06) puis tenter de déclencher une intra dans la même demande → le moteur doit l'**interdire** (max 1 clarification/demande).
- **S5 insatisfaction** : S1 mais répondre « Non » à l'enquête → template mise en relation avec `{temps_attente}` du mock → ESCALADE `insatisfaction` → FIN, **sans boucle de ré-essai**.
- **S6 multi-demandes** : enchaîner 6 demandes satisfaites → à la 6ᵉ, `max_demandes` (5) déclenche la FIN.
- **S7 retrieval dégradé** : question `resiliation` que les 2 documents ne couvrent pas → fallback intention → escalade si toujours < 2 chunks au-dessus de 0.35.
- **S8 timeout** : session inactive > 300 s → clôture timeout.
- **S9 confidentialité** : question `cotisations` dont seule la réponse est dans le doc confidentiel → le chunk confidentiel n'apparaît jamais dans la trace ni la réponse.

### P4 — Escalade (contrat mock)
Provoquer les 4 motifs (`insatisfaction`, `demande_explicite`, `hors_perimetre`, `retrieval_insuffisant`) et valider pour chacun : payload conforme au contrat JSON (transcript, intention, sous-motif, motif, horodatage), retour `temps_attente_estime_min` injecté dans le template.

### P5 — Déterminisme (exigence n°1)
Rejouer S1 à S9 deux fois à config et index identiques : **séquences d'états et messages système strictement identiques** (seul le texte généré par le LLM peut varier marginalement — temp 0 le limite). Test automatisé de rejeu exigé en CI.

### P6 — Latence
Sur 50 tours de playground : classification L1/L2 ≤ 50 ms, templates ~0 ms, retrieval < 200 ms, premier token < 2 s, réponse complète < 8 s. SLO décomposé visible dans le dashboard.

### P7 — Publication, runtime & widget
1. `POST /publish` : vérifier les validations bloquantes (min 8 exemples, `hors_périmètre` renseignée, avertissement de couverture sur `resiliation`).
2. Générer clé API + snippet ; intégrer le widget sur une page hôte factice.
3. Tests runtime : création session (message d'accueil **annonçant le périmètre** des 7 intentions), message texte en SSE (événements `state`/`template`/`buttons`/`generation_delta`/`sources`/`end_of_turn`), clic bouton de clarification, feedback 👎, reprise de session après rechargement.
4. Sécurité : clé scopée bot + origine (requête depuis une origine non déclarée → refus), aucune clé LLM exposée côté client, bundle < 50 ko gzippé.
5. Charge : 50 sessions simultanées, latences hors LLM stables.

### P8 — Boucle d'amélioration continue
1. Dans le dashboard, retrouver le cas T04 (« RIB coordonnées bancaires ») mal classé ou clarifié → 1 clic → l'ajouter comme exemple à `changement_coordonnees` (flag `from_production`) → ré-entraîner → rejouer T04 : classification directe.
2. Injecter une série de 👎 sur `arret_travail` → vérifier la **suggestion de scission** en sous-motifs dans le dashboard.

### P9 — Métriques & recette finale
Après ~30 conversations de test, vérifier le dashboard : taux de selfcarisation par intention, taux d'escalade par motif (les 4 motifs présents), taux de clarification, latences P50/P95, replay des conversations avec trace.

---

## 6. Critères de succès globaux (Go/No-Go)

| # | Critère | Seuil |
|---|---|---|
| 1 | Précision classification L1 sur le held-out (T01–T15 + 100 verbatims tirés du dataset hors entraînement) | ≥ 85 % de routages corrects ou clarifications pertinentes |
| 2 | Détection `demande_conseiller` sur les 126 verbatims `parler_conseiller` | ≥ 90 % |
| 3 | Rejet `hors_périmètre` sur 100 verbatims des intentions non retenues | ≥ 80 % rejetés ou escaladés (0 réponse générée à côté) |
| 4 | Déterminisme (P5) | 100 % — aucune divergence d'état/message système |
| 5 | Règle d'or max 1 clarification | 100 % — incontournable |
| 6 | Fuite de document confidentiel | 0 occurrence |
| 7 | Budget latence hors LLM (P6) | 100 % des tours dans le budget |
| 8 | Citation du lien source FAQ quand disponible | ≥ 95 % des réponses générées |

Les critères 4, 5, 6 sont **éliminatoires** : ce sont les promesses de construction du produit face à Odigo, pas des métriques de qualité ajustables.
