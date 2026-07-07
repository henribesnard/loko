# W2 — Guide d'exécution de la contre-épreuve

> **Objectif** : Mesurer le vrai plateau (74/86/83 ou 72/82/72 ?) avant de décider quoi que ce soit pour W4.
> **Durée** : ~1 heure
> **Priorité** : BLOQUANT pour tout le reste

---

## Contexte

La campagne v0.3.6 montre une régression apparente :
- GNG-1 : 74 → 72%
- GNG-2 : 85.6 → 82.4%
- GNG-3 : 83 → 72%
- Pièges : 8 → 6/15

**Deux hypothèses** :
1. **Artefact méthodologique** : coin de sweep + contamination V2-5
2. **Régression réelle** : problème introduit entre v0.3.5 et v0.3.6

W2 tranche entre les deux.

---

## Approche simplifiée (recommandée)

### Option A : Analyse des artefacts existants

**Constat actuel** :
- Nous n'avons PAS d'artefacts de campagne v0.3.5 dans `eval/campagne-R0R1/`
- Seule la campagne v0.3.6 (2026-07-06) est présente
- Le rapport v0.3.6 mentionne les chiffres v0.3.5 comme référence, mais sans artefacts

**Action rapide** (15 min) :
1. Vérifier dans git l'historique des campagnes
2. Chercher si v0.3.5 a été archivée ailleurs
3. Si introuvable → **documenter l'absence et passer directement à W1+W3**

```bash
# Recherche d'artefacts v0.3.5
git log --all --oneline --grep="v0.3.5"
git log --all --oneline --grep="campagne"
git ls-tree -r v0.3.5 --name-only | grep -i "campagne\|rapport\|validation"
```

**Si v0.3.5 introuvable** :
- Acte: « W2 non exécutable (données v0.3.5 manquantes) »
- **Décision pragmatique** : W4 partira de l'hypothèse plateau ~74/86/83 (raisonnable car le sweep de v0.3.6 confirme qu'aucun seuil n'atteint les cibles)
- Si W4 échoue NET, on reviendra au bisect M1/M2/M3

---

### Option B : Recréer une mesure de référence

**Si l'image v0.3.6 est stable et train.csv propre**, on peut mesurer maintenant avec seuils v0.3.5 :

#### Prérequis
- Docker Desktop installé et démarré
- Image `loko-r0r1-codex:v0.3.6` disponible
- Git Bash ou WSL pour exécuter le script

#### Exécution Windows (Git Bash)

```bash
# Depuis Git Bash dans c:/Users/henri/Projets/loko
chmod +x tools/w2_contre_epreuve.sh
./tools/w2_contre_epreuve.sh
```

**Le script va** :
1. Créer un conteneur Docker temporaire
2. Créer un bot avec train.csv (125 exemples, SANS V2-5)
3. Entraîner (V2-1)
4. Configurer seuils v0.3.5 (haut 0.85 / bas 0.30 / écart 0.05)
5. Exécuter V3-1→V3-4
6. Comparer aux chiffres v0.3.5
7. Écrire le verdict dans `eval/w2-contre-epreuve-{date}/W2_contre_epreuve.md`

#### Lecture des résultats

**Si Δ < ±2% sur GNG-1/GNG-2/GNG-3** :
```
LECTURE: Régression v0.3.6 = ARTEFACT
  → Plateau confirmé ~74/86/83
  → W4 vise +11 pts GNG-1, +4 pts GNG-2
  → Continuer avec W1+W3 puis W4
```

**Si Δ ≥ 3% sur un GNG** :
```
LECTURE: Régression v0.3.6 RÉELLE
  → SUSPENDRE W4
  → Bissecter M1/M2/M3 (diff v0.3.5..v0.3.6)
  → Corriger avant de continuer
```

---

## Option C : Skip W2 et acter une hypothèse

**Si contraintes de temps ou environnement** :

### Hypothèse actée (à documenter)

> W2 non exécuté par manque d'artefacts v0.3.5 de référence.
>
> **Hypothèse retenue** : La régression v0.3.6 est un artefact (coin de sweep + contamination V2-5).
>
> **Plateau de départ pour W4** : 74% / 86% / 83% (pièges 8/15).
>
> **Plan B** : Si W4 itération 1 dégrade les chiffres (≠ amélioration), alors bissecter M1/M2/M3 pour identifier une éventuelle régression réelle.

Créer `W2_hypothese_actee.md` :

```markdown
# W2 — Hypothèse actée (contre-épreuve non exécutée)

**Date** : 2026-07-06
**Raison** : Artefacts campagne v0.3.5 introuvables

## Hypothèse retenue

La régression observée en v0.3.6 (GNG 74→72 / 85.6→82.4 / 83→72) est un **artefact méthodologique** :
- Seuils en coin de grille (haut 0.90 / bas 0.30 / écart 0.05)
- Contamination V2-5 (6 exemples `hors_perimetre` avant V3)

## Plateau de référence pour W4

- GNG-1 : **74%** (cible +11 pts → 85%)
- GNG-2 : **86%** (cible +4 pts → 90%)
- GNG-3 : **83%** (déjà > 80%, maintenir)
- Pièges : **8/15** (cible 12/15)

## Plan B

Si W4 itération 1 **dégrade** les métriques (régression observée), alors :
1. Interrompre W4
2. Bissecter diff v0.3.5..v0.3.6 (commits M1/M2/M3)
3. Identifier et corriger la cause
4. Revenir à cette étape

## Implications

- W1+W3 peuvent démarrer immédiatement (non bloqués par W2)
- W4 démarre avec cette hypothèse de plateau
- Surveillance stricte de W4 itération 1 pour détecter toute régression
```

---

## Recommandation

**Compte tenu** :
- Pas d'artefacts v0.3.5 disponibles
- La régression v0.3.6 est cohérente avec les défauts connus (sweep coin + V2-5)
- W1+W3 peuvent avancer en parallèle
- Le temps est compté pour valider R0+R1

**Je recommande Option C** : Acter l'hypothèse, continuer avec W1+W3, surveiller W4.

**Si vous insistez sur W2** : Exécuter Option B (script automatisé, ~1h).

---

## Prochaine action

Souhaitez-vous :
1. **Exécuter le script W2** (`./tools/w2_contre_epreuve.sh` via Git Bash) ?
2. **Acter l'hypothèse** et passer à W1+W3 directement ?
3. **Chercher les artefacts v0.3.5** dans git/archive avant de décider ?

Votre choix ?
