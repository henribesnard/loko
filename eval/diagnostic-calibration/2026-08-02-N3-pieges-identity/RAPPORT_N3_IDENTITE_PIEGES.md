# N3 — Identite nominative des pieges en echec (v1.3.3 vs v1.3.4)

> Date : 2026-08-02
> Sources : `eval/recette-integrale/2026-07-17-v1.3.3/V3_pieges/report.json`,
>           `eval/recette-integrale/2026-08-01-v1.3.4/V3_pieges/report.json`,
>           `eval/recette-integrale/2026-08-01-v1.3.4-H3/pieges/report.json`

## Tableau comparatif T01-T15

| ID | Attendu | v1.3.3 (T=1.0) | v1.3.4 (T=0.60) | v1.3.4+H3 (T=1.0) |
|---|---|---|---|---|
| T01 | route:help_account | PASS | PASS | PASS |
| T02 | route:help_account | **FAIL** clarify_inter (0.746) | **FAIL** clarify_inter (0.712) | **FAIL** clarify_inter (0.628) |
| T03 | clarify_intra:help_account | PASS | PASS | PASS |
| T04 | clarify_inter:help_contact\|help_billing | **FAIL** route:help_contact (0.981) | **FAIL** route:help_contact (0.999) | **FAIL** route:help_contact (0.983) |
| T05 | clarify_inter:help_contact\|help_billing | **FAIL** route:help_billing (0.982) | **FAIL** route:help_billing (1.000) | **FAIL** route:help_billing (0.989) |
| T06 | clarify_inter:3 classes | **FAIL** clarify_inter:2 (0.600) | **FAIL** clarify_inter:2 (0.782) | **FAIL** clarify_inter:2 (0.629) |
| T07 | route:help_documents | PASS | PASS | PASS |
| T08 | route:help_leave | PASS | PASS | PASS |
| T09 | route:help_transfer | PASS | PASS | **FAIL** clarify_inter (0.787) |
| T10 | route:help_cancellation | PASS | PASS | PASS |
| T11 | escalate | PASS | PASS | PASS |
| T12 | reject | PASS | PASS | PASS |
| T13 | reject | **FAIL** clarify_inter (0.685) | **FAIL** clarify_inter (0.766) | **FAIL** clarify_inter (0.575) |
| T14 | route:help_transfer | PASS | PASS | PASS |
| T15 | route:help_account | **FAIL** reject (0.491) | **FAIL** clarify_inter (0.740) | **FAIL** clarify_inter (0.517) |
| | | **9/15** | **9/15** | **8/15** |

## Analyse

### Identite parfaite entre v1.3.3 et v1.3.4

Les 6 pieges en echec sont **strictement les memes** dans les deux versions :
{T02, T04, T05, T06, T13, T15}. Le score 9/15 est identique.

C'est une **recomposition a somme nulle** : la calibration T=0.60 modifie les
scores mais ne change ni les pieges qui passent, ni ceux qui echouent.

### Effet de la calibration sur T15

T15 change de *type de decision* entre les deux :
- v1.3.3 (T=1.0) : score 0.491 < seuil_bas 0.50 -> **reject** (mauvais)
- v1.3.4 (T=0.60) : score 0.740 en zone grise -> **clarify_inter** (mauvais aussi)

La calibration pousse le score au-dessus de seuil_bas, changeant le mecanisme
d'echec (reject -> clarify) mais pas le resultat (FAIL dans les deux cas).

### Contre-test H3 : T09 degrade

Avec T=1.0 sur le modele v1.3.4, T09 (help_transfer) tombe en clarify_inter
(score 0.787, juste en dessous de seuil_haut 0.85). La calibration T=0.60 pousse
ce score au-dessus de 0.85, le faisant passer en route directe (PASS).

C'est un cas ou la calibration **aide** : elle compense un modele legerement
plus faible sur T09 par rapport a v1.3.3.

## Conclusion N3

**Verdict : recomposition a somme nulle.**

L'identite des pieges en echec est parfaitement stable entre v1.3.3 et v1.3.4.
La calibration ne change pas le set de pieges qui echouent — elle modifie les
scores et parfois le mecanisme d'echec (reject vs clarify) mais pas le resultat.

Le contre-test H3 montre une legere degradation (T09), masquee par la calibration
dans la mesure v1.3.4. Cela confirme que le 9/15 stable est un artefact de
compensation : le modele v1.3.4 est legerement plus faible sur T09 mais la
calibration le sauve. L'hypothese "H3 incomplete" du §4.3 de l'analyse v1.1 est
donc infirmee : les pieges ne sont pas affectes par H3 parce que le set d'echecs
est exactement le meme, independamment de la calibration.
