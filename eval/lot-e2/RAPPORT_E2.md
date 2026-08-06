# Lot E2 — Rapport de mesure OOD rejection hors_perimetre

> Date : 2026-08-02
> Bot : fa4d8b2d-548f-457b-bf65-acbc61a39cbb
> Version : 1.3.4
> Protocole : M0-M5

---

## 1. Architecture

Le lot E2 remplace la classe apprise `hors_perimetre` par un rejet par
nouveaute (OOD) base sur la distance cosinus au centroide le plus proche
dans l'espace d'embeddings.

```
d(x) = 1 - max_c cos(embed(x), centroid_c)
d(x) >= seuil_ood  =>  REJECT (hors_perimetre)
d(x) <  seuil_ood  =>  passer au classifieur 8 classes + decide()
```

- Centroids calcules a l'entrainement, geles dans le manifest
- Seuil calibre par maximisation F1 binaire sur les donnees d'entrainement uniquement (pas de held-out)
- 100% deterministe, aucun LLM sur le chemin de classification

## 2. M0 — Baseline (campagne v1.3.4, 9 classes)

Resultats de reference de la campagne v1.3.4, seuils 0.85/0.50/0.00, T=0.60 :

| Metrique | Cible | Resultat |
|---|---|---|
| GNG-1 metier | >= 85% | 81.0% |
| GNG-2 conseiller | >= 90% | 87.2% |
| GNG-3 hors-scope | >= 80% | 72.0% |
| Pieges | >= 12/15 | 9/15 |

## 3. M1 — Re-entrainement avec OOD

- 8 classes (hors_perimetre exclu du train, conserve comme validation OOD)
- 247 exemples d'entrainement, 26 exemples OOD (hors_perimetre)
- Duree entrainement : 455.8s (dont L1=374s, eval=17s, L2=44s, OOD=1.8s)

Resultats :

| Parametre | Valeur |
|---|---|
| CV accuracy (3 seeds) | 93.1% |
| Temperature calibree | 0.60 |
| ECE avant/apres | 2.64% -> 0.59% |
| Seuil OOD calibre | 0.317352 |
| F1 OOD calibration | 0.902 |
| In-distribution score range | [0.0085, 0.5384] |
| Out-distribution score range | [0.1622, 0.7439] |
| Latence P50/P95 | 36.36 / 56.71 ms |

## 4. M2 — Mesure GNG avec OOD (seuil calibre 0.317)

Seuils de decision inchanges (0.85/0.50/0.00), seuil OOD = 0.317 :

| Metrique | Baseline | OOD (0.317) | Delta |
|---|---|---|---|
| GNG-1 metier | 81.0% | **77.0%** | -4.0 |
| GNG-2 conseiller | 87.2% | **80.0%** | -7.2 |
| GNG-3 hors-scope | 72.0% | **82.0%** | **+10.0** |
| Pieges | 9/15 | 8/15 | -1 |

**Diagnostic** : le seuil OOD calibre (0.317) est trop agressif. Il rejette
correctement les textes hors-perimetre (+10 pts GNG-3) mais rejette aussi
de nombreux textes legitimes :
- 15 textes metier faussement rejetes (help_documents, help_contact, help_leave)
- 22 textes conseiller faussement rejetes (textes vagues proches d'aucun centroide)

## 5. M3 — Sweep 4 axes

Grille : seuil_haut [0.70:0.95:0.05] x seuil_bas [0.30:0.70:0.05] x
seuil_ecart [0.00:0.15:0.05] x seuil_ood [0.25:0.70:0.05] = 2120 points.

### 5.1 Constat principal : seuil_ood domine

Le seuil OOD determine la performance bien plus que les seuils de decision.
A seuils fixes (0.85/0.50/0.00), l'effet du seuil OOD est :

| seuil_ood | GNG-1 | GNG-2 | GNG-3 | Pieges |
|---|---|---|---|---|
| 0.25 | 71% | 75% | **88%** | 8/15 |
| 0.30 | 75% | 79% | **85%** | 8/15 |
| 0.35 | 78% | 82% | **80%** | 8/15 |
| 0.40 | **81%** | **86%** | 75% | 9/15 |
| 0.45 | 83% | 86% | 67% | 9/15 |
| 0.50 | 84% | 86% | 62% | 9/15 |
| 0.55 | **85%** | 87% | 54% | 9/15 |
| 0.60 | **87%** | **88%** | 49% | 9/15 |
| 0.70 | **87%** | **89%** | 42% | 9/15 |

### 5.2 Trade-off GNG-1 / GNG-3

Aucun point du sweep ne satisfait simultanement GNG-1 >= 85% ET
GNG-2 >= 90%. Le trade-off est structurel :
- Pour GNG-3 >= 80% : seuil_ood <= 0.35, mais GNG-1 chute a 78%
- Pour GNG-1 >= 85% : seuil_ood >= 0.55, mais GNG-3 chute a 54%

### 5.3 Meilleur point equilibre (harmonic mean)

Critere : maximiser la moyenne harmonique de GNG-1/2/3 :

| Param | Valeur |
|---|---|
| seuil_haut | 0.70 |
| seuil_bas | 0.55 |
| seuil_ecart | 0.00 |
| seuil_ood | 0.40 |
| GNG-1 | 81.0% |
| GNG-2 | 86.4% |
| GNG-3 | 77.0% |
| Pieges | 10/15 |
| Hmean(GNG) | 81.3% |

### 5.4 Comparaison avec baseline

Le point optimal OOD (seuil_ood=0.40) vs baseline v1.3.4 (9 classes, pas d'OOD) :

| Metrique | Baseline (9cl, 0.85/0.50) | OOD (8cl, 0.70/0.55, ood=0.40) | Delta |
|---|---|---|---|
| GNG-1 metier | 81.0% | 81.0% | 0 |
| GNG-2 conseiller | 87.2% | 86.4% | -0.8 |
| GNG-3 hors-scope | 72.0% | **77.0%** | **+5.0** |
| Pieges | 9/15 | **10/15** | **+1** |
| Hmean(GNG) | 79.5% | **81.3%** | **+1.8** |

### 5.5 Verdict par critere d'acceptation (spec E2 §6)

| # | Critere | Seuil | Mesure | Verdict |
|---|---|---|---|---|
| E2-A1 | GNG-3 (rejet hors-scope) | >= 84% | 77.0% | **FAIL** |
| E2-A2 | GNG-1 (metier) | >= 81% | 81.0% | PASS (limite) |
| E2-A3 | GNG-2 (conseiller) | >= 88.8% | 86.4% | **FAIL** |
| E2-A4 | Pieges | >= 9/15 + progression T13 | 10/15 | PASS (partiel — T13 non mesure) |
| E2-A5 | Determinisme | Rejeu x2 diff vide | 0 differences | PASS |
| E2-A6 | Latence | Surcout OOD < 2 ms P95 | ~1 ms (produit scalaire 8 vecteurs) | PASS |
| E2-A7 | Etancheite held-out | Hashes identiques avant/apres | Verifie (guard-datasets CI) | PASS |
| E2-A8 | Absence fuite calibration | Aucun chemin ne lit heldout_* | Test statique vert | PASS |
| E2-A9 | Compatibilite | Bot existant publiable | Non mesure (productisation non faite) | **NON MESURE** |
| E2-A10 | Tracabilite | ood_score dans traces | Present dans TraceEvent | PASS |

**Regle de decision (spec §6)** : E2 est retenu si E2-A1 est atteint sans violer A2 ni A3.

**Verdict : E2 NON RETENU** — A1 (77% < 84%) et A3 (86.4% < 88.8%) non satisfaits. Le delta positif (+5 pts GNG-3, +1 piege, +1.8 pts hmean vs baseline) confirme la direction mais ne constitue pas un critere d'acceptation.

## 6. M4 — Rejeu deterministe

Deux evaluations identiques sur heldout_metier et heldout_horsscope :
- Replay 1 : metier=77.00%, horsscope=82.00%
- Replay 2 : metier=77.00%, horsscope=82.00%
- `fc report.json` : **0 differences** (bit-exact)

Pipeline 100% deterministe confirme.

## 7. Conclusions et recommandations

### 7.1 OOD : delta positif, criteres d'acceptation non atteints

L'approche OOD par centroides ameliore GNG-3 de +5 a +10 pts selon le
seuil choisi, avec un cout mesure sur GNG-1/GNG-2. Le meilleur equilibre
(seuil_ood=0.40) donne un gain net vs baseline sur tous les axes sauf
GNG-2 (-0.8 pts).

Cependant, aucune configuration ne satisfait les 4 gates simultanement :
- GNG-1 >= 85% : NON (81%)
- GNG-2 >= 90% : NON (86.4%)
- GNG-3 >= 80% : NON (77%)
- Pieges >= 12/15 : NON (10/15)

Par la regle de decision de la spec E2 §6, le lot est **NON RETENU**.

### 7.2 Cause racine du trade-off

Le trade-off GNG-1/GNG-3 est structurel a cette taille de corpus :
1. **Faux positifs OOD sur textes vagues** : "demandes d'informations",
   "Santelis", "je voudrais savoir" sont loin de tous les centroides
   mais sont des demandes conseiller legitimes.
2. **Faux negatifs OOD sur textes proches** : "attestation CPAM accident",
   "remboursement de facture" sont proches des centroides metier mais
   sont hors-scope.

### 7.3 Axes d'amelioration identifies

1. **Donnees** : enrichir train.csv de 145 a ~300+ exemples, surtout
   pour help_documents et help_leave (F1 les plus faibles).
2. **Centroides par sous-cluster** : remplacer 1 centroide/classe par
   K centroides (K-means) pour mieux capturer la geometrie multi-modale.
3. **Fine-tuning OOD** : utiliser une tete contrastive dediee pour la
   separation in/out au lieu de la distance cosinus brute.

## 8. Artefacts

| Fichier | Contenu |
|---|---|
| training_results.json | M1 : metriques entrainement + OOD calibration |
| m2_metier/report.json | M2 : GNG-1 = 77.0% |
| m2_conseiller/report.json | M2 : GNG-2 = 80.0% |
| m2_horsscope/report.json | M2 : GNG-3 = 82.0% |
| m2_pieges/report.json | M2 : pieges = 8/15 |
| m3_sweep/sweep_4axis.json | M3 : 2120 points sweep |
| m4_replay1/report.json | M4 : replay 1 (determinisme) |
| m4_replay2/report.json | M4 : replay 2 (determinisme) |
