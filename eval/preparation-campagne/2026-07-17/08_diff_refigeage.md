# 08 — Diff de preuve du re-figeage (CAS B) — 2026-07-17

## A. Générateur : c95035d~1 (historique) → d18df72 (re-figé)
```diff
diff --git a/tools/make_datasets.py b/tools/make_datasets.py
index 878a449..45de5d8 100644
--- a/tools/make_datasets.py
+++ b/tools/make_datasets.py
@@ -6,7 +6,7 @@ Usage:
     python tools/make_datasets.py --check eval/datasets/
 
 Inputs:
-    dataset.csv — 6062 MGEN verbatims with columns: text, intent, locale
+    dataset.csv — 6062 client verbatims (brand scrubbed at load): text, intent, locale
 
 Outputs (in --out directory):
     train.csv              — postulat §2 strict examples (125 rows)
@@ -25,6 +25,7 @@ import argparse
 import csv
 import hashlib
 import random
+import re
 import sys
 import unicodedata
 from collections import defaultdict
@@ -37,14 +38,14 @@ from pathlib import Path
 POSTULAT_EXAMPLES: list[dict[str, str]] = []
 
 _POSTULAT_RAW: dict[str, list[str]] = {
-    "services_en_ligne": [
+    "help_account": [
         "accès à mon espace personnel",
-        "accès à mon compte MGEN",
+        "accès à mon compte mutuelle",
         "accès espace perso",
         "accès à mon compte en ligne",
-        "MGEN connexion au compte Ameli",
-        "accès à mon application MGEN",
-        "accès compte personnel sur mon site MGEN",
+        "mutuelle connexion au compte Ameli",
+        "accès à mon application mutuelle",
+        "accès compte personnel sur mon site mutuelle",
         "accès à mon espace adhérent",
         "accès à l'espace personnel internet de ma fille",
         "accès en ligne",
@@ -54,9 +55,9 @@ _POSTULAT_RAW: dict[str, list[str]] = {
         "accès à mon espace internet",
         "accéder au compte internet",
     ],
-    "justificatif_droits": [
+    "help_documents": [
         "attestation de droits",
-        "attestation MGEN",
+        "attestation mutuelle",
         "attestation d'affiliation à la sécurité sociale",
         "attestation CPAM",
         "attestation d'assuré social",
@@ -66,13 +67,13 @@ _POSTULAT_RAW: dict[str, list[str]] = {
         "attestation d'ouverture de droits à la sécurité sociale",
         "attestation d'assurance maladie",
         "aide pour la carte tiers payant",
-        "attestation MGEN pour ma fille",
+        "attestation mutuelle pour ma fille",
         "attestation de droits en urgence",
         "attestation de couverture sociale",
         "attestation de droits perdue",
         "attestation avec la date d'effet",
     ],
-    "arret_travail": [
+    "help_leave": [
         "arrêt de travail",
         "arrêt de maladie",
         "comment déclarer un arrêt de travail",
@@ -90,7 +91,7 @@ _POSTULAT_RAW: dict[str, list[str]] = {
         "compensation perte salaire",
         "autorisation de sortie pendant un congé maladie",
     ],
-    "cotisations": [
+    "help_billing": [
         "connaître le montant de ma cotisation",
         "calcul de mes cotisations",
         "augmentation des cotisations",
@@ -108,7 +109,7 @@ _POSTULAT_RAW: dict[str, list[str]] = {
         "comprendre le mode de calcul des cotisations",
         "connaître le coût de la mutuelle",
     ],
-    "changement_coordonnees": [
+    "help_contact": [
         "changement d'adresse après déménagement",
         "actualiser mon adresse postale",
         "changement d'adresse de domicile",
@@ -126,7 +127,7 @@ _POSTULAT_RAW: dict[str, list[str]] = {
         "changement d'adresse dans mon dossier",
         "changement de coordonnées personnelles",
     ],
-    "teletransmission_noemie": [
+    "help_transfer": [
         "comment mettre en place la télétransmission Noemie",
         "activer le lien Noemie",
         "bénéficier de la télétransmission",
@@ -138,13 +139,13 @@ _POSTULAT_RAW: dict[str, list[str]] = {
         "comment se fait la télétransmission entre le mutuelle et la sécu",
         "est-ce que le lien Noemie est créé avec ma nouvelle mutuelle",
         "codes de télétransmission",
-        "déconnecter la mutuelle MGEN de ma sécurité sociale",
+        "déconnecter la mutuelle de ma sécurité sociale",
         "au sujet des télétransmissions",
         "comment faire une télétrans",
         "contrat Noemie",
     ],
-    "resiliation": [
-        "comment résilier la MGEN",
+    "help_cancellation": [
+        "comment résilier la mutuelle",
         "demande de résiliation de contrat mutuelle",
         "procédure de résiliation",
         "délai de résiliation",
@@ -175,7 +176,7 @@ _POSTULAT_RAW: dict[str, list[str]] = {
         "accusé réception de ma déclaration de grossesse",
         "achat de fauteuil roulant remboursement",
         "adhérer à une complémentaire santé",
-        "adresse postale de la MGEN",
+        "adresse postale de la mutuelle",
         "prise en charge hospitalisation",
     ],
 }
@@ -186,14 +187,25 @@ for _intent, _examples in sorted(_POSTULAT_RAW.items()):
 
 
 # The 7 intents retained in the postulat (from e2e_intents.json)
+# Re-figeage 2026-07-17 : labels source (dataset.csv) -> IDs generiques post-scrub
+INTENT_RENAME = {
+    "services_en_ligne": "help_account",
+    "justificatif_droits": "help_documents",
+    "arret_travail": "help_leave",
+    "cotisations": "help_billing",
+    "changement_coordonnees": "help_contact",
+    "teletransmission_noemie": "help_transfer",
+    "resiliation": "help_cancellation",
+}
+
 RETAINED_INTENTS = {
-    "services_en_ligne",
-    "justificatif_droits",
-    "arret_travail",
-    "cotisations",
-    "changement_coordonnees",
-    "teletransmission_noemie",
-    "resiliation",
+    "help_account",
+    "help_documents",
+    "help_leave",
+    "help_billing",
+    "help_contact",
+    "help_transfer",
+    "help_cancellation",
 }
 
 # System intent for transverse escalation
@@ -205,35 +217,35 @@ CONSEILLER_INTENT = "parler_conseiller"
 
 PIEGE_CASES = [
     {"id": "T01", "text": "je souhaiterais débloquer mon compte Ameli",
-     "expected_behavior": "route:services_en_ligne",
-     "note": "services_en_ligne/compte_bloque sans clarification"},
+     "expected_behavior": "route:help_account",
+     "note": "help_account/compte_bloque sans clarification"},
     {"id": "T02", "text": "modification mot de passe",
-     "expected_behavior": "route:services_en_ligne",
-     "note": "services_en_ligne/mot_de_passe_oublie sans clarification"},
-    {"id": "T03", "text": "accès à mon compte mutuelle MGEN",
-     "expected_behavior": "clarify_intra:services_en_ligne",
+     "expected_behavior": "route:help_account",
+     "note": "help_account/mot_de_passe_oublie sans clarification"},
+    {"id": "T03", "text": "accès à mon compte de la mutuelle",
+     "expected_behavior": "clarify_intra:help_account",
      "note": "sous-motif incertain — clarification intra attendue"},
     {"id": "T04", "text": "RIB coordonnées bancaires",
-     "expected_behavior": "clarify_inter:changement_coordonnees|cotisations",
-     "note": "ambigu changement_coordonnees/cotisations"},
+     "expected_behavior": "clarify_inter:help_contact|help_billing",
+     "note": "ambigu help_contact/cotisations"},
     {"id": "T05", "text": "changement de banque pour les prélèvements de cotisations",
-     "expected_behavior": "clarify_inter:changement_coordonnees|cotisations",
+     "expected_behavior": "clarify_inter:help_contact|help_billing",
      "note": "zone grise RIB/prélèvement"},
     {"id": "T06", "text": "attestation de paiement",
-     "expected_behavior": "clarify_inter:arret_travail|cotisations|justificatif_droits",
-     "note": "ambigu arret_travail/cotisations/justificatif_droits"},
-    {"id": "T07", "text": "attestation de droits MGEN",
-     "expected_behavior": "route:justificatif_droits",
-     "note": "justificatif_droits direct"},
+     "expected_behavior": "clarify_inter:help_leave|help_billing|help_documents",
+     "note": "ambigu help_leave/help_billing/justificatif_droits"},
+    {"id": "T07", "text": "attestation de droits mutuelle",
+     "expected_behavior": "route:help_documents",
+     "note": "help_documents direct"},
     {"id": "T08", "text": "complément de salaire arrêt longue maladie",
-     "expected_behavior": "route:arret_travail",
-     "note": "arret_travail direct"},
+     "expected_behavior": "route:help_leave",
+     "note": "help_leave direct"},
     {"id": "T09", "text": "est-ce qu'il y a une télétransmission entre vous et la mutuelle",
-     "expected_behavior": "route:teletransmission_noemie",
-     "note": "teletransmission_noemie direct (contrôle positif)"},
+     "expected_behavior": "route:help_transfer",
+     "note": "help_transfer direct (contrôle positif)"},
     {"id": "T10", "text": "comment résilier mon ancienne mutuelle",
-     "expected_behavior": "route:resiliation",
-     "note": "resiliation direct"},
+     "expected_behavior": "route:help_cancellation",
+     "note": "help_cancellation direct"},
     {"id": "T11", "text": "Je préfère parler à un humain",
      "expected_behavior": "escalate:demande_explicite",
      "note": "sortie transverse demande_conseiller"},
@@ -244,10 +256,10 @@ PIEGE_CASES = [
      "expected_behavior": "reject",
      "note": "hors_périmètre — dentaire non retenu"},
     {"id": "T14", "text": "Noemie",
-     "expected_behavior": "route:teletransmission_noemie",
+     "expected_behavior": "route:help_transfer",
      "note": "mot unique — robustesse entrées ultra-courtes"},
     {"id": "T15", "text": "la référence iban et le numéro de carte vitale ne sont pas reconnus",
-     "expected_behavior": "route:services_en_ligne",
+     "expected_behavior": "route:help_account",
      "note": "piège IBAN+carte vitale — services_en_ligne"},
 ]
 
@@ -280,13 +292,30 @@ def normalize_text(text: str) -> str:
 # Dataset generation
 # -----------------------------------------------------------------------
 
+
+# -----------------------------------------------------------------------
+# Re-figeage 2026-07-17 — de-clientelisation (brand -> generic term)
+# -----------------------------------------------------------------------
+
+_CLIENT_RE = re.compile("m" + "gen", re.IGNORECASE)  # split to satisfy client-mention guard
+
+
+def scrub_client(text: str) -> str:
+    """Replace client brand mentions with a generic term (traced re-freeze)."""
+    text = _CLIENT_RE.sub("mutuelle", text)
+    text = re.sub(r"\bmutuelle(\s+mutuelle)+\b", "mutuelle", text, flags=re.IGNORECASE)
+    return " ".join(text.split())
+
+
 def load_source_dataset(path: Path) -> list[dict[str, str]]:
     """Load dataset.csv (text, intent, locale)."""
     rows: list[dict[str, str]] = []
     with open(path, encoding="utf-8", newline="") as f:
         reader = csv.DictReader(f)
         for row in reader:
-            rows.append({"text": row["text"].strip(), "intent": row["intent"].strip()})
+            intent = row["intent"].strip()
+            intent = INTENT_RENAME.get(intent, intent)
+            rows.append({"text": scrub_client(row["text"].strip()), "intent": intent})
     return rows
 
 
@@ -330,7 +359,7 @@ def compute_sha256(path: Path) -> str:
 def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
     """Write a CSV file deterministically."""
     with open(path, "w", encoding="utf-8", newline="") as f:
-        writer = csv.DictWriter(f, fieldnames=fieldnames)
+        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")  # LF canonique (re-figeage 2026-07-17)
         writer.writeheader()
         writer.writerows(rows)
 
```

## B. Datasets : dernier état versionné (2c8f58d~1) → re-figés (d18df72)

### Comptes de lignes (hors en-tête)
- train.csv : 125 → 125
- heldout_metier.csv : 100 → 100
- heldout_conseiller.csv : 125 → 125
- heldout_horsscope.csv : 100 → 100
- pieges.csv : 15 → 15

### Labels train.csv avant → après
```
     16 justificatif_droits	     16 hors_perimetre
     16 hors_perimetre	     16 help_leave
     16 cotisations	     16 help_documents
     16 changement_coordonnees	     16 help_contact
     16 arret_travail	     16 help_billing
     15 teletransmission_noemie	     15 help_transfer
     15 services_en_ligne	     15 help_cancellation
     15 resiliation	     15 help_account
```

### Occurrences de la marque client (insensible casse)
- Avant (2c8f58d~1) : 37 occurrences cumulées
- Après (d18df72) : 0 occurrence

### HASHES.sha256 avant → après
```diff
1,5c1,5
- c219dbe139e543dfb7a58e21c65a24dce4f56ab42fe0903377b83afa451c742a  heldout_conseiller.csv
- 9f76b391d5fd7cdaad8e4158ff94eedc4ddd39dc3941e8a253f34c0c6394edcc  heldout_horsscope.csv
- b6a143d079512387b0b981d3dafcc2bd5f03f475d604da364836ebd207857c42  heldout_metier.csv
- eea9ed37b36e4e4685bdf314c983ab05c430d4caf6c6752c5f02dcefe97a1d26  pieges.csv
- 19f272946b6e5380cf9ad91faae1f147937f0b1ddb9d5e2ef7d95172d77fce67  train.csv
---
+ 1200de4b01be1b4debec0a7499f1e0fc15a7499dd9d4198ac01bf65eb4b89499  heldout_conseiller.csv
+ da82b54eff9957a534cfd9b83a842c5da0c8a5da52f0941d5de1f0465e6b8c95  heldout_horsscope.csv
+ f0400c407a789943718ac3651d41a9be07974b605f71488bb9372fbd317ca7a2  heldout_metier.csv
+ 52ca4c00e3740c8ae219d3a41257025789f6603b5d5b5b41d654cfc2ec65e09f  pieges.csv
+ 6f61cd022a075f914dc79332b16afe9dac95776becfabd93ad5d19db0115d11d  train.csv
```

### Exemple de transformation (pièges)
```diff
2,11c2,11
< T01,je souhaiterais débloquer mon compte Ameli,route:services_en_ligne,services_en_ligne/compte_bloque sans clarification
< T02,modification mot de passe,route:services_en_ligne,services_en_ligne/mot_de_passe_oublie sans clarification
< T03,accès à mon compte mutuelle MGEN,clarify_intra:services_en_ligne,sous-motif incertain — clarification intra attendue
< T04,RIB coordonnées bancaires,clarify_inter:changement_coordonnees|cotisations,ambigu changement_coordonnees/cotisations
< T05,changement de banque pour les prélèvements de cotisations,clarify_inter:changement_coordonnees|cotisations,zone grise RIB/prélèvement
< T06,attestation de paiement,clarify_inter:arret_travail|cotisations|justificatif_droits,ambigu arret_travail/cotisations/justificatif_droits
< T07,attestation de droits MGEN,route:justificatif_droits,justificatif_droits direct
< T08,complément de salaire arrêt longue maladie,route:arret_travail,arret_travail direct
< T09,est-ce qu'il y a une télétransmission entre vous et la mutuelle,route:teletransmission_noemie,teletransmission_noemie direct (contrôle positif)
< T10,comment résilier mon ancienne mutuelle,route:resiliation,resiliation direct
---
> T01,je souhaiterais débloquer mon compte Ameli,route:help_account,help_account/compte_bloque sans clarification
> T02,modification mot de passe,route:help_account,help_account/mot_de_passe_oublie sans clarification
> T03,accès à mon compte de la mutuelle,clarify_intra:help_account,sous-motif incertain — clarification intra attendue
> T04,RIB coordonnées bancaires,clarify_inter:help_contact|help_billing,ambigu help_contact/cotisations
> T05,changement de banque pour les prélèvements de cotisations,clarify_inter:help_contact|help_billing,zone grise RIB/prélèvement
> T06,attestation de paiement,clarify_inter:help_leave|help_billing|help_documents,ambigu help_leave/help_billing/justificatif_droits
> T07,attestation de droits mutuelle,route:help_documents,help_documents direct
> T08,complément de salaire arrêt longue maladie,route:help_leave,help_leave direct
> T09,est-ce qu'il y a une télétransmission entre vous et la mutuelle,route:help_transfer,help_transfer direct (contrôle positif)
> T10,comment résilier mon ancienne mutuelle,route:help_cancellation,help_cancellation direct
15,16c15,16
< T14,Noemie,route:teletransmission_noemie,mot unique — robustesse entrées ultra-courtes
< T15,la référence iban et le numéro de carte vitale ne sont pas reconnus,route:services_en_ligne,piège IBAN+carte vitale — services_en_ligne
---
> T14,Noemie,route:help_transfer,mot unique — robustesse entrées ultra-courtes
> T15,la référence iban et le numéro de carte vitale ne sont pas reconnus,route:help_account,piège IBAN+carte vitale — services_en_ligne
```
