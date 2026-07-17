# P1 — Note d'enquête : disparition de eval/datasets/ et make_datasets.py

**Date** : 2026-07-17 · **Exécutant** : agent (Cowork) · **Mission** : préparation de campagne (aucune campagne en cours)

## Cause racine

Les datasets figés et l'outillage ont été **supprimés volontairement** le 10 juillet 2026, dans le cadre du nettoyage des références client (MGEN) du dépôt. Ce ne sont ni un `.gitignore` trop large (seuls `dataset.csv` / `*.dataset.csv` sont ignorés, lignes 58–60), ni des fichiers jamais versionnés.

Chaîne des commits (preuve : `02_disparition_datasets.txt`) :

| Commit | Date | Objet | Contenu supprimé |
|---|---|---|---|
| `ef55439` | 2026-07-10 07:24 | feat: remediation post-evaluation — lots V, R, F | 20 CSV d'enrichissement (`enrichment_w4*.csv`, `train_enriched_v03*.csv`) |
| `2c8f58d` | 2026-07-10 15:48 | **chore: remove MGEN frozen datasets** | `HASHES.sha256`, `train.csv`, `heldout_metier.csv` (100), `heldout_conseiller.csv` (125), `heldout_horsscope.csv` (100), `pieges.csv` (15) |
| `c95035d` | 2026-07-10 15:49 | **chore: remove MGEN evaluation tools** | `tools/make_datasets.py` (540 lignes) |

Le commit HEAD `0c00423` (« scrub client-specific references ») confirme l'intention : purge des références MGEN.

## Récupérabilité

**Oui, intégralement récupérable depuis git** :

- `git show 2c8f58d~1:eval/datasets/HASHES.sha256` → 5 entrées (sortie ci-dessous).
- Les 5 CSV sont extraits du même commit parent (`dcd3a5d`, 2026-07-05, « correction plan C1-C10 »).
- `tools/make_datasets.py` : `git show c95035d~1:tools/make_datasets.py` (540 lignes).

```
c219dbe139e543dfb7a58e21c65a24dce4f56ab42fe0903377b83afa451c742a  heldout_conseiller.csv
9f76b391d5fd7cdaad8e4158ff94eedc4ddd39dc3941e8a253f34c0c6394edcc  heldout_horsscope.csv
b6a143d079512387b0b981d3dafcc2bd5f03f475d604da364836ebd207857c42  heldout_metier.csv
eea9ed37b36e4e4685bdf314c983ab05c430d4caf6c6752c5f02dcefe97a1d26  pieges.csv
19f272946b6e5380cf9ad91faae1f147937f0b1ddb9d5e2ef7d95172d77fce67  train.csv
```

## Vérification d'intégrité (nuance fins de ligne)

`sha256sum -c` sur les blobs git bruts (LF) **échoue 5/5**. Cause identifiée et prouvée : les hash de `HASHES.sha256` ont été calculés sur les fichiers du checkout **Windows (CRLF)** ; git stocke les blobs normalisés LF. Après conversion LF→CRLF, la vérification passe **5/5** au commit `dcd3a5d` (« MATCH INTEGRAL (CRLF) »).

Conséquence opérationnelle : la vérification CE-3 en conteneur (Linux) doit se faire soit sur des fichiers restaurés en CRLF, soit après re-calcul du `HASHES.sha256` sur la forme canonique restaurée — à trancher en P2, en le traçant.

Note historique : les held-out ont évolué entre `2297fa5` (04-07) et `dcd3a5d` (05-07) avec mise à jour cohérente de `HASHES.sha256` (corrections M4, plan C1-C10) — re-figeage inter-campagnes tracé, conforme.

## Point de décision pour P2 (à trancher par l'humain)

Les datasets sont techniquement récupérables (CAS A), **mais** leur suppression était une décision délibérée de purge des données client MGEN. Restaurer ces fichiers dans le dépôt réintroduit du contenu client. Options soumises : restaurer tel quel (CAS A), restaurer hors-git (non versionné — en tension avec « les datasets et le hash sont COMMITTÉS »), ou re-figeage avec des jeux dé-clientélisés (CAS B assumé, perte de comparabilité E1).
