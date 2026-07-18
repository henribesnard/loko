# T2 — Arret du runner sur CE FAIL

## Symptome
La campagne v1.3.3 a deroule V0-V3 malgre CE-2 FAIL, alors que CE est
defini comme « bloquant » dans le protocole v2.2.

## Cause racine
`run_campaign()` iterait toutes les lignes sans verifier le verdict CE
entre les phases CE et V0.

## Correction
1. Apres l'execution des lignes CE, le runner calcule le verdict CE
   intermediaire.
2. Si CE FAIL et pas `--diagnostic` : les lignes V0+ restent
   « CE FAIL — non execute (bloquant) », le rapport est ecrit, exit 2.
3. Avec `--diagnostic` : la campagne continue mais le rapport porte la
   mention « MODE DIAGNOSTIC — CAMPAGNE NON OPPOSABLE (CE FAIL) ».

## Preuve
- Syntaxe Python verifiee : `ast.parse()` OK
- Le flag `--diagnostic` est ajoute au parseur CLI
- Exit code 2 dedie pour « CE bloquant » (distinct de 0=PASS, 1=gate FAIL)
