# W4.1 — Analyse des patterns d'erreur V3-1

**Source** : V3-1_errors_classified.csv
**Total erreurs** : 28

## Distribution par catégorie

- **seuil** : 24 erreurs
- **verbatim_ambigu** : 3 erreurs
- **manque_exemples** : 1 erreurs

## Intentions affectées

### services_en_ligne (7 erreurs)

**Mots-clés fréquents** :
- `espace` (2×)
- `compte` (2×)
- `ameli` (2×)
- `internet` (2×)
- `associée` (1×)

**Abréviations détectées** :
- `MGEN` (1×)

**Exemples d'erreurs** :
- "associée mon espace client" → prédit `hors_perimetre` (cat: seuil)
- "créer un compte pour une personne" → prédit `demande_conseiller` (cat: seuil)
- "espace Ameli" → prédit `hors_perimetre` (cat: seuil)

**Recommandations** :
- Ajouter 5 exemples discriminants pour renforcer le signal (actuellement 7 faux rejets)

### arret_travail (6 erreurs)

**Mots-clés fréquents** :
- `maladie` (2×)
- `besoin` (1×)
- `imprimé` (1×)
- `trente` (1×)
- `trois` (1×)

**Abréviations détectées** :
- `AJ` (2×)

**Exemples d'erreurs** :
- "besoin d'un imprimé trente-trois seize" → prédit `hors_perimetre` (cat: seuil)
- "document AJ" → prédit `hors_perimetre` (cat: seuil)
- "problème pour arrêt maladie" → prédit `hors_perimetre` (cat: seuil)

**Recommandations** :
- Ajouter 5 exemples discriminants pour renforcer le signal (actuellement 5 faux rejets)
- Clarifier avec métier : 1 verbatims ambigus déclenchent clarify_inter (besoin reformulation ?)

### justificatif_droits (6 erreurs)

**Mots-clés fréquents** :
- `carte` (5×)
- `adhérent` (2×)
- `tiers` (2×)
- `payant` (2×)
- `mutuelle` (1×)

**Exemples d'erreurs** :
- "carte mutuelle" → prédit `hors_perimetre` (cat: seuil)
- "certificat d'affiliation" → prédit `hors_perimetre` (cat: seuil)
- "demande de carte adhérent" → prédit `hors_perimetre` (cat: seuil)

**Recommandations** :
- Ajouter 5 exemples discriminants pour renforcer le signal (actuellement 5 faux rejets)
- Clarifier avec métier : 1 verbatims ambigus déclenchent clarify_inter (besoin reformulation ?)

### changement_coordonnees (5 erreurs)

**Mots-clés fréquents** :
- `adresse` (3×)
- `postale` (3×)
- `confirmer` (1×)
- `information` (1×)
- `concernant` (1×)

**Abréviations détectées** :
- `RIB` (1×)

**Exemples d'erreurs** :
- "confirmer mon adresse postale" → prédit `demande_conseiller` (cat: seuil)
- "information concernant une demande de RIB" → prédit `hors_perimetre` (cat: seuil)
- "problème coordonnées postales" → prédit `hors_perimetre` (cat: seuil)

**Recommandations** :
- Ajouter 5 exemples discriminants pour renforcer le signal (actuellement 5 faux rejets)

### resiliation (2 erreurs)

**Mots-clés fréquents** :
- `résilier` (2×)
- `complémentaire` (1×)
- `santé` (1×)
- `fille` (1×)
- `contrat` (1×)

**Exemples d'erreurs** :
- "résilier la complémentaire santé de ma fille" → prédit `hors_perimetre` (cat: seuil)
- "résilier mon contrat prévoyance actifs" → prédit `hors_perimetre` (cat: seuil)

**Recommandations** :
- Ajouter 2 exemples discriminants pour renforcer le signal (actuellement 2 faux rejets)

### cotisations (1 erreurs)

**Mots-clés fréquents** :
- `cotisation` (1×)
- `retraité` (1×)

**Exemples d'erreurs** :
- "cotisation retraité" → prédit `arret_travail` (cat: manque_exemples)

**Recommandations** :
- Enrichir frontière avec intent confondu : 1 routage(s) incorrect(s) suggèrent manque d'exemples discriminants

### teletransmission_noemie (1 erreurs)

**Mots-clés fréquents** :
- `connaitre` (1×)
- `mutuelle` (1×)
- `associée` (1×)
- `compte` (1×)
- `sécurité` (1×)

**Exemples d'erreurs** :
- "connaitre la mutuelle associée à mon compte sécurité sociale" → prédit `justificatif_droits` (cat: verbatim_ambigu)

**Recommandations** :
- Clarifier avec métier : 1 verbatims ambigus déclenchent clarify_inter (besoin reformulation ?)


## Priorités d'enrichissement

1. **arret_travail** (score 8.0)
   - 6 erreurs totales
   - Objectif : ajouter ~12 exemples ciblés

2. **justificatif_droits** (score 8.0)
   - 6 erreurs totales
   - Objectif : ajouter ~12 exemples ciblés

3. **services_en_ligne** (score 7.0)
   - 7 erreurs totales
   - Objectif : ajouter ~14 exemples ciblés

4. **changement_coordonnees** (score 5.0)
   - 5 erreurs totales
   - Objectif : ajouter ~10 exemples ciblés

5. **cotisations** (score 4.0)
   - 1 erreurs totales
   - Objectif : ajouter ~5 exemples ciblés

6. **teletransmission_noemie** (score 3.0)
   - 1 erreurs totales
   - Objectif : ajouter ~5 exemples ciblés

7. **resiliation** (score 2.0)
   - 2 erreurs totales
   - Objectif : ajouter ~5 exemples ciblés

