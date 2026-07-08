# 🗺️ LOKO — Feuille de route complète vers le produit final (post-campagne v0.3.7)

> **Version** : 1.0 — 7 juillet 2026
> **Entrées** : `RAPPORT_CAMPAGNE_V0_3_7.md` + `CAMPAGNE_STATUS.md` (campagne v0.3.7, commit `9f2cd15`), spec de cadrage v1.0 (`specs-loko-bot-service-client.md` / synthèse 1), `SPECS_DEV_LOKO_BOT.md`, protocole de recette produit v2.0 (synthèse 3), `PROTOCOLE_VALIDATION_R0_R1_LOKO_V2.md`, `FEUILLE_DE_ROUTE_VALIDATION_FINALE_R0_R1_LOKO.md` (W1–W5).
> **Objet** : document unique couvrant (1) l'état réel du produit vis-à-vis de la spec initiale, (2) la correction des anomalies de la campagne v0.3.7, (3) toutes les étapes restantes jusqu'au produit final déployé, chacune fermée par une **gate** : tests end-to-end + rapport + critères d'acceptance + décision GO/NO-GO explicite pour l'étape suivante.
> **Règle de lecture** : aucune étape ne s'ouvre sans le rapport GO de la précédente. Les travaux de *développement* peuvent anticiper (règle des travaux parallèles), jamais les *recettes*.

---

# PARTIE I — ÉTAT RÉEL VIS-À-VIS DE LA SPEC INITIALE

## I.1 Lecture critique de la campagne v0.3.7 : non opposable

Avant l'état produit, un constat de gouvernance qui conditionne tout le reste. La campagne v0.3.7 s'auto-déclare « R0 VALIDÉ, R1 PARTIEL ». **Cette conclusion n'est pas recevable**, pour quatre violations des règles opposables (annexe B du protocole, en vigueur depuis v0.2.0) :

1. **V1 « présumé PASS » sans exécution** : V1-1→V1-5 « différés », validés par lecture du code (`check_published_bots()` « vérifié au niveau code »). C'est l'interdit n°4 mot pour mot (« valider un critère structurellement sans exécution »). Le mode confirmation du protocole v2.x allège l'exploration, **pas l'exécution**. G-1 est donc NON MESURÉ — et R0 ne peut pas être déclaré validé par cette campagne.
2. **V2-3, V2-4, V2-5 « SKIPPED »** : interdit n°3 (« une ligne non exécutée = FAIL, pas absente »). « Test complexe, faible priorité » n'est pas un verdict.
3. **Requalifications unilatérales en cours de campagne** : V2-6 FAIL (P95 73 ms) requalifié « hardware-dependent, non bloquant » ; V2-2 FAIL requalifié « attendu, non bloquant ». C'est la règle 6 du protocole v2.x, ajoutée précisément contre cette dérive : une anomalie de protocole se **consigne**, elle ne se tranche pas pendant la campagne.
4. **Recommandation dangereuse** : le « Choix A » proposé (renommer `parler_conseiller` → `demande_conseiller` dans `heldout_conseiller.csv`) toucherait un dataset figé par hash — interdit n°5, le plus grave de tous. **À proscrire explicitement.**

## I.2 Le vice caché : le bot de campagne était mal configuré

Le rapport contient la preuve que les chiffres V3-0 de v0.3.7 sont mesurés sur un **bot non conforme au postulat** :

- **« 8 intents, 125 exemples »** — le postulat exige **9 intentions** (7 métier + `hors_perimetre` + `demande_conseiller` transverse pré-entraînée). L'intention manquante est très probablement `demande_conseiller` : c'est exactement ce qui produit **GNG-2 = 0 %** (le bot ne peut structurellement pas émettre `transverse:demande_conseiller` s'il ne connaît pas cette intention).
- **« Pas de L2 services_en_ligne (exemples insuffisants) »** — le niveau 2 avec ses 5 sous-motifs existait et passait V2-2 dans les campagnes v0.3.4, v0.3.5 et v0.3.6 **avec les mêmes datasets figés** (hashes CE-4 identiques). Les exemples n'ont pas disparu : c'est le chargement du postulat qui ne les a pas pris.
- Le diagnostic « incohérence dataset/protocole » est donc **erroné** : GNG-2 se mesurait à 84,8 %, 85,6 % puis 82,4 % sur trois campagnes avec ce même dataset hashé. Ce qui a changé en v0.3.7, c'est la configuration du bot (et/ou le mapping de labels dans le nouveau code de sweep W3.1) — pas le dataset.

**Conséquence** : GNG-1 = 69 %, GNG-2 = 0 %, pièges 8/15 de cette campagne sont **nuls et non avenus**. L'état de référence de la qualité métier reste le plateau des campagnes précédentes : **~74 % / ~86 % / ~83 %, pièges 8/15** — jamais contre-éprouvé proprement (le W2 de la feuille de route précédente n'a pas été exécuté non plus).

## I.3 État consolidé par domaine de la spec initiale

| Domaine de la spec v1.0 | Implémenté | Validé en recette | État réel |
|---|---:|---:|---|
| **Déterminisme structurel** (FSM Python pure, templates fixes, SetFit, temp 0) | ✅ | Partiel (v0.1/v0.2 « machine ») | Architecture en place et testée unitairement (393 tests) ; recette produit du parcours complet (R4) non faite. |
| **Classification 2 niveaux** (L1 9 classes, L2 sous-motifs, matrice, advice) | ✅ | ⚠️ | Train 219 s, CV 3-seeds, advice fonctionnel (3 paires détectées). Mais **G-3 jamais atteint** : plateau ~74/86/83 vs cibles 85/90/80, pièges 8/15 vs 12/15. **C'est LE verrou.** |
| **Intégrité anti-mock / fail-fast** (R0) | ✅ | ⚠️ quasi | Démontré intégralement en v0.3.5 ; V1-4 complet (log CRITICAL) codé en v0.3.7 (W1.2) mais **jamais exécuté en E2E**. Une exécution propre suffit. |
| **Calibration & évaluation outillée** (`loko-eval`, sweep Pareto) | ✅ | ⚠️ | Sweep 3 axes + sélection Pareto opérationnels (80 faisables/240, 15 Pareto). Suspicion de régression de mapping de labels à lever (GNG-2=0 %). |
| **Knowledge & retrieval filtré** (ingestion, tagging, filtrage dur, couverture, citations) | ✅ (lot B) | ❌ | Développé (backend hybride BM25+vectoriel, pré-filtrage dur) ; recette R2 (0 fuite/50 requêtes, citations `source_url`) jamais exécutée. |
| **Génération LLM réelle** (streaming, temp 0, provider API) | ✅ | ❌ | Provider `openai_compat` opérationnel (ping OK toutes campagnes) ; recette R3 (qualité/latence de génération sur parcours réels) non faite. |
| **Connecteur FAQ web** (crawler JS/iframes, resync) | ✅ (item R6 plan v2) | ❌ | Développé ; recette sur miroir figé mgen.fr non faite. |
| **Widget embarquable** (streaming, boutons, feedback, reprise) | ✅ | ❌ | Développé ; E2E Playwright sur page hôte (R5/spec §12.8) non exécuté. |
| **Sécurité runtime** (P0-1→P0-5 : clés scopées, admin token fail-closed, CORS/headers, path traversal, rate limiting) | ✅ | Partiel | Corrigés et vérifiés au plan v2 ; recette sécurité dédiée (R7) + `npm audit` OK. Pentest de confirmation non fait. |
| **Observabilité & dashboard** (traces, selfcare par intention, boucle 1-clic) | ✅ (lot D) | ❌ | Développé (bug pollution dataset corrigé + garde-fou) ; recette non faite. |
| **Charge & concurrence** (50 sessions simultanées) | ✅ script | ❌ | Non exécuté en recette. |
| **Docker/mode serveur** | ✅ | ✅ | Image 1 009 Mo conforme, offline OK, atomicité OK — le socle infra a convergé. |
| **Déploiement production** (VPS, domaine, TLS, RGPD purge) | ❌ | ❌ | Non commencé (prépa Cloudflare/loko.wezon.fr discutée, rien d'exécuté). |

**Synthèse en une phrase** : le produit est **développé à ~90 %** et son infrastructure de validation a convergé, mais il n'est **recetté qu'à ~25 %** — un seul verrou de fond (la qualité de classification G-3, jamais attaquée par l'enrichissement W4), plus une dérive de discipline de campagne qui, elle, est le risque n°1 du projet à ce stade : **des rapports non opposables valent zéro, quel que soit le code.**

---

# PARTIE II — LA FEUILLE DE ROUTE : 8 ÉTAPES, 8 GATES

Chaque étape suit le même contrat : **Objectif → Prérequis → Travaux → Protocole de test E2E → Critères d'acceptance → Rapport & décision de gate.** Le rapport de gate suit le gabarit commun (annexe A) ; un critère non mesuré = FAIL du critère ; une gate FAIL = l'étape suivante reste fermée.

```
E0 Gouvernance ──► E1 Diagnostic & config ──► E2 Validation R0+R1 (G-3) ──► E3 Knowledge/RAG (R2)
                                                        │ (échec → E2b postulat)
E3 ──► E4 Parcours complet + génération (R3+R4) ──► E5 Widget & connecteur (R5+R6)
E5 ──► E6 Sécurité, charge, observabilité (R7+R8) ──► E7 Recette humaine & GO produit (R9)
E7 ──► E8 Déploiement pilote production
```

---

## E0 — Rétablir l'opposabilité des campagnes (gouvernance + outillage)

**Objectif** : rendre matériellement impossible la dérive constatée en v0.3.7 (tests sautés, PASS présumés, requalifications en cours de route). Sans E0, toutes les gates suivantes sont du théâtre.

**Prérequis** : aucun.

**Travaux** :
1. **Runner de campagne** (`tools/run_campaign.py`) : exécute séquentiellement toutes les lignes du protocole actif, génère le squelette de rapport avec **toutes** les lignes pré-remplies `NON EXÉCUTÉ = FAIL`, remplace chaque ligne uniquement par un verdict adossé à un artefact existant (chemin vérifié). Un test ne peut être marqué SKIP que si le protocole prévoit explicitement ce statut pour lui. Le verdict des gates est **calculé** par le runner, pas rédigé.
2. **Verrou de requalification** : les champs verdict du rapport sont générés ; les commentaires libres vont dans une section « anomalies de protocole suspectées » qui n'altère jamais le verdict.
3. **Amendement protocole v2.2** : (a) le mode confirmation V1 = exécution complète V1-1→V1-5 avec exploration allégée, jamais une lecture de code ; (b) V2-6 : la mesure de latence de gate se fait sur une machine de référence déclarée en CE (l'écart matériel constaté — 28 ms en v0.3.6, 73 ms en v0.3.7 — devient une donnée de CE, pas une excuse a posteriori) ; (c) interdit n°9 : auto-déclarer un gate PASS sans exécution de toutes ses lignes.
4. **Rappel formalisé** au(x) exécutant(s) (humain ou agent) : les interdits n°1–9 en tête de chaque prompt de campagne.

**Protocole de test E2E** : campagne à blanc (dry-run) sur l'image v0.3.7 existante — le runner doit produire un rapport où V2-3/V2-4/V2-5 apparaissent FAIL (et non absents), où G-1 est FAIL faute d'exécution V1, et refuser de calculer « R0 VALIDÉ ».

**Critères d'acceptance** :
| # | Critère | Mesure |
|---|---|---|
| E0-1 | Le runner produit un rapport exhaustif (toutes lignes V0-1→V3-7 présentes) | Diff structurel rapport/protocole vide |
| E0-2 | Une ligne sans artefact = FAIL automatique | Test du runner (artefact supprimé → FAIL) |
| E0-3 | Verdicts de gates calculés, non éditables | Revue code + test |
| E0-4 | Dry-run sur v0.3.7 → « NON VALIDÉS », G-1 FAIL | Rapport dry-run archivé |

**Gate G-E0** : rapport `RAPPORT_E0_GOUVERNANCE.md` + dry-run joint → GO ouvre E1. **Effort : 1 jour.**

---

## E1 — Diagnostic v0.3.7, conformité du bot de campagne, contre-épreuve du plateau

**Objectif** : corriger la cause racine des chiffres invalides de v0.3.7 (bot mal configuré), lever la suspicion sur le code de sweep, et mesurer enfin le vrai plateau (le W2 jamais exécuté). C'est l'étape qui rend E2 pilotable.

**Prérequis** : G-E0 PASS.

**Travaux** :
1. **Diagnostic de la config** : instrumenter `tools/load_postulat.py` — pourquoi le bot v0.3.7 a 8 intentions au lieu de 9 et pas de L2 ? Corriger (chargement de `demande_conseiller` transverse + sous-motifs `services_en_ligne`).
2. **Nouvelle condition d'entrée CE-9 (bloquante, protocole v2.2)** : conformité du bot au postulat vérifiée **avant** V2 — 9 intentions dont `hors_perimetre` et `demande_conseiller`, ≥ 8 exemples/intention, `level2_services_en_ligne` déclaré avec ses 5 labels. Sortie machine (JSON) archivée.
3. **Audit du mapping de labels** dans le code de sweep W3.1 : vérifier que `parler_conseiller`/`demande_conseiller` et le mode conseiller (`decision == escalate` + intent transverse) sont évalués comme dans les campagnes v0.3.4–v0.3.6 (qui mesuraient GNG-2 à 82–86 %). Test de non-régression : rejouer le sweep sur les décisions archivées de v0.3.6 → retrouver les chiffres de v0.3.6. **Interdiction rappelée : aucun renommage dans les CSV held-out.**
4. **Contre-épreuve du plateau (ex-W2)** : bot conforme (9 intentions + L2), train complet, V3-1→V3-4 aux seuils v0.3.5 **et** au point Pareto recalculé. Établir la référence chiffrée officielle.

**Protocole de test E2E** : exécution par le runner E0 d'une mini-campagne « diagnostic » : CE-1→CE-9, V2-1, V2-2, puis V3-0 (sweep) et V3-1→V3-4, artefacts complets.

**Critères d'acceptance** :
| # | Critère | Mesure |
|---|---|---|
| E1-1 | CE-9 OK : bot 9 intentions + L2 5 labels | JSON de conformité |
| E1-2 | V2-2 OK (retour au niveau v0.3.4–v0.3.6) | Manifeste |
| E1-3 | GNG-2 redevient mesurable et ≥ 80 % au point Pareto | `report.json` conseiller |
| E1-4 | Non-régression sweep : chiffres v0.3.6 retrouvés sur décisions archivées | Diff |
| E1-5 | Plateau de référence consigné (GNG-1/2/3, routes directes, pièges, aux deux jeux de seuils) | Note de contre-épreuve |

**Gate G-E1** : rapport `RAPPORT_E1_DIAGNOSTIC.md` → GO ouvre E2 avec un plateau de départ fiable et le gap exact à combler. **Effort : 1–2 jours.**

---

## E2 — Validation R0+R1 complète (campagne v0.3.8) — le verrou G-3

**Objectif** : la campagne qui valide enfin R0+R1, en jouant la **seule cartouche jamais tirée en sept campagnes** : l'enrichissement du train (W4). Ouvre R2–R9.

**Prérequis** : G-E1 PASS ; protocole v2.2 publié (amendements E0 + CE-9) ; **exemples W4 produits et revus par le métier avant le tag**.

**Travaux (pré-campagne)** :
1. **W4.1 — synthèse des patterns d'erreurs** depuis la référence E1 (les 4 patterns identifiés : frontière `services_en_ligne`↔`changement_coordonnees` ; `demande_conseiller` indirect ; bandes de clarification T04–T06 ; faux rejets sur verbatims réels).
2. **W4.2 — production des exemples** : passer de ~14 à 25–30 exemples/classe (train ~125 → ~230–270), verbatims **réalistes** (tournures orales, fautes, contexte parasite), rédigés avec le métier, chaque exemple tagué par pattern ciblé. **Jamais tirés des held-out.** Budget train à surveiller (≤ 300 s ; marge : 219 s à 125 ex).
3. **W1 soldé en exécution** : V1-1→V1-5 complets (dont log CRITICAL au boot, codé mais jamais exécuté).
4. Préparer le **dossier W5** (branche d'échec) en parallèle : hypothèses de fusion d'intentions, critère de déclenchement (> 3 pts manquants sur un GNG ou > 2 pièges après 2 itérations), coût du re-figeage des datasets.

**Protocole de test E2E** : campagne complète protocole v2.2 par le runner : CE-1→CE-9 → V0 → V1 (exécution intégrale) → V2 (V2-4/V2-5 sur bot jetable) → V3-0 sweep Pareto → V3-1→V3-4, V3-6 → itérations V3-7 (max 2) avec re-sweep à chaque itération.

**Critères d'acceptance** (= gates du protocole, inchangés) :
| # | Critère | Seuil |
|---|---|---|
| E2-1 | G-0 : V0-1→V0-5 | PASS (image par inspect ≤ 1,6 Go) |
| E2-2 | G-1 éliminatoire : V1-1→V1-4 **exécutés** | PASS sans réserve |
| E2-3 | G-1b : V1-5 offline | PASS |
| E2-4 | G-2 : V2-1 ≤ 300 s ; V2-2 L2 conforme ; V2-3 atomicité ; V2-4/V2-5 cycle sur paire détectée ; V2-6 P95 ≤ 50 ms sur machine de référence | PASS |
| E2-5 | G-3 : GNG-1 ≥ 85 % ; GNG-2 ≥ 90 % ; GNG-3 ≥ 80 % avec ≤ 5 routes directes ; pièges ≥ 12/15 commentés ; V3-6 diff vide — aux seuils figés V3-0 | PASS |
| E2-6 | Modèle + seuils + manifeste **gelés** et consignés | Manifeste archivé |

**Gate G-E2** : `RAPPORT_VALIDATION_R0_R1_v038.md` (gabarit protocole) →
- **GO** : R0+R1 VALIDÉS, ouverture des recettes E3+.
- **NO-GO net après 2 itérations** : bascule **E2b — révision du postulat** (W5) : décision métier sur les frontières d'intentions, re-figeage des datasets, cycle court de re-validation. E2b est une étape à part entière avec son propre rapport ; les développements E3–E6 continuent en parallèle, seules les recettes attendent.

**Effort : 2–4 jours ingénierie + production de données métier ; +2–3 jours si E2b.**

---

## E3 — Recette Knowledge & RAG filtré (phase R2)

**Objectif** : valider la chaîne connaissances en conditions réelles : ingestion de la FAQ cible (miroir figé), tagging intention/sous-motif, retrieval filtré **dur**, couverture, citations. C'est la première brique du « répond juste » après le « route juste » de E2.

**Prérequis** : G-E2 PASS (modèle et seuils gelés). Développements déjà livrés (lot B) ; miroir figé de `mgen.fr/aide-et-contact` constitué et hashé (E4 du protocole recette : FAQ cible ou miroir).

**Travaux** : constitution du miroir figé versionné ; jeu de 50 requêtes de fuite (verbatims visant des documents d'une autre intention ou confidentiels) ; jeu de couverture par intention.

**Protocole de test E2E** (in-container, bot gelé E2) :
1. Ingestion du miroir → tagging par intention/sous-motif via l'API → indicateur de couverture relevé pour les 7 intentions métier.
2. **Test d'étanchéité** : 50 requêtes adverses → analyse des chunks retournés (pré-filtrage dur : aucun chunk d'une intention non ciblée, aucun document non-« publique » côté bot public).
3. **Test de citation** : 20 réponses générées → chaque réponse porte ses `source_url` du miroir.
4. **Fallback** : requêtes à couverture faible → élargissement intention puis escalade, conformes aux paramètres (`retrieval_min_score` 0.35, `retrieval_min_chunks` 2).

**Critères d'acceptance** :
| # | Critère | Seuil |
|---|---|---|
| E3-1 | Ingestion miroir complète (iframes suivies) | 100 % des articles du miroir indexés |
| E3-2 | Étanchéité du filtrage dur | **0 fuite / 50 requêtes** (critère 6 du plan v2) |
| E3-3 | Citations | 20/20 réponses avec `source_url` valide (critère 8) |
| E3-4 | Couverture visible par intention | Indicateur exact vs comptage manuel |
| E3-5 | Fallback → escalade sous les seuils | Transcripts conformes FSM |

**Gate G-E3** : `RAPPORT_RECETTE_R2_KNOWLEDGE.md` → GO ouvre E4. **Effort : 2–3 jours.**

---## E4 — Recette du parcours complet : génération LLM réelle + FSM (phases R3+R4)

**Objectif** : valider le parcours de bout en bout tel que la spec le définit (§A.3) : accueil → classification → clarifications (max 1) → retrieval filtré → **génération streaming temp 0 par provider réel** → enquête → fin/escalade, avec trace complète.

**Prérequis** : G-E3 PASS. Provider LLM réel (contrat E3 du protocole recette : temp 0).

**Protocole de test E2E** :
1. **Matrice de parcours** : un scénario par chemin de la FSM (route directe, clarification inter, clarification intra par bouton, clarification intra texte libre, « Autre », hors-périmètre + reformulation, escalade transverse, timeout, enquête satisfait/insatisfait, max_demandes) — exécutés par l'API runtime, transcripts complets archivés.
2. **Déterminisme structurel** : rejeu de 10 parcours → états, décisions et templates strictement identiques ; seul le texte généré par le LLM peut varier (et à temp 0, doit être quasi stable — diff consigné).
3. **Templates** : vérification qu'aucun message système ne provient du LLM (trace par étape).
4. **Latence de bout en bout** : budget par étape mesuré (classification ~50 ms locale ; TTFB génération streamée < 2 s ; enquête instantanée).
5. **Escalade mock** : contrat d'interface figé respecté (payload complet : session, intention, transcript, temps d'attente).

**Critères d'acceptance** :
| # | Critère | Seuil |
|---|---|---|
| E4-1 | Tous les chemins FSM couverts | 100 % de la matrice, transcripts archivés |
| E4-2 | Max 1 clarification par demande, tous scénarios | 0 violation |
| E4-3 | Messages système = templates | 0 message système généré par LLM |
| E4-4 | Rejeu déterministe (hors texte LLM) | Diff structurel vide sur 10 parcours |
| E4-5 | TTFB génération < 2 s, classification P95 ≤ 50 ms | Mesures in-container |
| E4-6 | Contrat d'escalade conforme | Payloads validés par schéma |

**Gate G-E4** : `RAPPORT_RECETTE_R3_R4_PARCOURS.md` → GO ouvre E5. **Effort : 2–3 jours.**

---

## E5 — Recette Widget & Connecteur FAQ (phases R5+R6)

**Objectif** : valider les deux surfaces d'exposition : le widget embarquable (l'interface adhérent) et le connecteur de crawl (l'alimentation continue des connaissances).

**Prérequis** : G-E4 PASS.

**Protocole de test E2E** :
1. **Widget (Playwright, page hôte factice — spec §12.8)** : chargement du snippet, ouverture, streaming visible, boutons de choix fermé (clarifications), feedback 👍/👎, reprise de session après rechargement, échappement HTML (payload XSS dans un verbatim), light/dark, mobile.
2. **Connecteur FAQ (sur miroir figé, item R6)** : crawl initial complet (rendu JS + iframes), resync avec 1 article modifié / 1 supprimé → diff d'index correct ; robustesse (page 404, timeout).
3. **Chaîne complète** : question posée **dans le widget** → réponse citant un article crawlé — le parcours produit intégral, du crawl à la bulle.

**Critères d'acceptance** :
| # | Critère | Seuil |
|---|---|---|
| E5-1 | Suite Playwright widget | 100 % verte, vidéo/screenshots archivés |
| E5-2 | XSS : payload rendu inerte | 0 exécution de script |
| E5-3 | Reprise de session | Historique restauré |
| E5-4 | Crawl initial du miroir | 100 % articles, iframes comprises |
| E5-5 | Resync incrémental | Diff d'index exact (1 modif, 1 suppression) |
| E5-6 | Chaîne widget→crawl bout en bout | Transcript + citation archivés |

**Gate G-E5** : `RAPPORT_RECETTE_R5_R6_SURFACES.md` → GO ouvre E6. **Effort : 2 jours.**

---

## E6 — Recette Sécurité, Charge & Observabilité (phases R7+R8)

**Objectif** : valider que le produit tient l'exposition réelle : sécurité runtime éprouvée offensivement, tenue en charge, observabilité fidèle.

**Prérequis** : G-E5 PASS.

**Protocole de test E2E** :
1. **Sécurité offensive** (checklist P0-1→P0-5 rejouée en attaque) : endpoints bot sans clé → 401/403 uniformes ; admin sans token → routers non montés (fail-closed) ; CORS restreint ; path traversal (`bot_id=../…`) → 422 ; rate limiting → 429 + `Retry-After` ; entrées surdimensionnées (> 2 000 chars) → rejet ; scan headers sécurité ; `npm audit`/`pip-audit` propres ; fuite d'info (aucun chemin disque/stack trace dans les réponses).
2. **Charge** : 50 sessions simultanées, 15 min (spec §12.9) : latences hors LLM stables (P95 classification ≤ 50 ms sous charge), 0 erreur 5xx, 0 mélange de sessions (isolation vérifiée par marquage), mémoire stable.
3. **Observabilité** : les traces des sessions de charge alimentent le dashboard → sessions, taux selfcare, escalades, latence P50, selfcare par intention **exacts vs comptage indépendant** ; boucle 1-clic (mal-classé → exemple d'entraînement) avec le garde-fou anti-pollution (message bot ≠ verbatim) vérifié.
4. **RGPD** : purge des transcripts (rétention configurable) effective ; détection PII sur logs.

**Critères d'acceptance** :
| # | Critère | Seuil |
|---|---|---|
| E6-1 | Checklist offensive | 0 finding P0/P1 ouvert |
| E6-2 | Charge 50 sessions/15 min | 0 5xx, 0 fuite inter-sessions, P95 classif ≤ 50 ms |
| E6-3 | Dashboard exact | Écart 0 vs comptage indépendant |
| E6-4 | Boucle 1-clic sans pollution | Garde-fou vérifié par test adverse |
| E6-5 | Purge RGPD | Transcripts absents après purge, prouvé |

**Gate G-E6** : `RAPPORT_RECETTE_R7_R8_SECU_CHARGE.md` → GO ouvre E7. **Effort : 2–3 jours.**

---

## E7 — Recette humaine & GO produit (phase R9)

**Objectif** : la validation finale de la spec : des humains (métier MGEN ou panel équivalent) utilisent le bot en conditions réelles, et les engagements produit sont tenus. C'est ici que se décide le **GO produit** du protocole de recette v2.

**Prérequis** : G-E6 PASS. Modèle/seuils/manifeste inchangés depuis E2 (sinon rejouer V3 — règle de gel).

**Protocole de test E2E** :
1. **Panel** : ≥ 5 testeurs métier, ≥ 100 sollicitations réelles cumulées (verbatims libres, pas de script), sur le widget.
2. **Mesures** : taux de selfcarisation global et par intention, taux d'escalade et motifs, taux de clarification, satisfaction (enquête intégrée), verbatims des échecs analysés un par un.
3. **Critère GO du protocole recette rappelé** : GNG-3 en conditions réelles vise **0 réponse à côté** (le ≤ 5 de E2 était la borne intermédiaire).
4. **Revue de sortie** : toutes les gates G-E2→G-E6 revérifiées inchangées (version figée), dossier de GO assemblé.

**Critères d'acceptance** :
| # | Critère | Seuil |
|---|---|---|
| E7-1 | Volume panel | ≥ 100 sollicitations réelles, ≥ 5 testeurs |
| E7-2 | Réponses « à côté » constatées | 0 (toute occurrence analysée et corrigée avant GO) |
| E7-3 | Taux de selfcarisation | ≥ objectif fixé avec le métier avant le panel (à contractualiser, référence callbot Odigo) |
| E7-4 | Satisfaction panel | ≥ 4/5 médian |
| E7-5 | Échecs analysés | 100 % commentés, plan d'action consigné |

**Gate G-E7** : `RAPPORT_GO_PRODUIT.md` → **GO PRODUIT** ouvre E8. Un NO-GO renvoie vers l'étape responsable identifiée (classification → boucle V3-7 dérogatoire ; knowledge → E3 ; etc.) avec re-passage des gates aval impactées. **Effort : 3–5 jours (dont disponibilité panel).**

---

## E8 — Déploiement pilote production

**Objectif** : mettre le produit validé en service réel sur `loko.wezon.fr`, avec l'exploitation minimale viable (sauvegardes, supervision, runbook).

**Prérequis** : **G-E7 PASS — l'exposition publique avant le GO produit reste limitée à la démo** (réserve déjà actée : token admin fort + Cloudflare Access sur `/api/admin/*`).

**Travaux** : VPS durci (ufw restreint aux plages IP Cloudflare, fail2ban, mises à jour auto) ; DNS A proxied `loko.wezon.fr`, SSL Full (strict), certificat Origin sur reverse proxy (Caddy/Nginx) → `127.0.0.1:8000` ; `docker-compose` production (restart policy, volume `/data`, healthcheck) ; sauvegarde quotidienne chiffrée de `/data` testée en restauration ; supervision (uptime + alerte santé + espace disque) ; runbook (démarrage, restauration, rotation des clés, incident modèle → fail-fast attendu) ; page de statut ou message de repli widget.

**Protocole de test E2E** :
1. **Smoke test production** : parcours complet depuis le widget sur le domaine public (HTTPS, streaming, session, escalade).
2. **Test de restauration** : restauration de la sauvegarde de la veille sur environnement vierge → bot identique (hash manifeste).
3. **Test d'incident** : suppression volontaire du modèle sur un bot de test → 503 fail-fast + alerte supervision reçue.
4. **Re-scan sécurité externe** : depuis Internet, seuls 443 (Cloudflare) et SSH (IP restreinte) répondent ; headers et rate limiting actifs sur le domaine public.

**Critères d'acceptance** :
| # | Critère | Seuil |
|---|---|---|
| E8-1 | Smoke test public | Parcours complet OK en HTTPS |
| E8-2 | Restauration prouvée | Manifeste identique post-restore |
| E8-3 | Incident → alerte | Alerte reçue < 5 min, fail-fast conforme |
| E8-4 | Surface d'exposition | Scan externe : 443/SSH uniquement, origin non joignable en direct |
| E8-5 | Runbook | Exécuté une fois de bout en bout par une personne qui ne l'a pas écrit |

**Gate G-E8** : `RAPPORT_MISE_EN_SERVICE.md` → **produit final en service pilote.** **Effort : 2 jours.**

---

# PARTIE III — PILOTAGE

## III.1 Chemin critique et parallélisation

- **Chemin critique** : E0 → E1 → E2 (→ E2b éventuel) → E3 → E4 → E7. Les recettes E5 et E6 peuvent s'exécuter en parallèle de E4/entre elles une fois E3 passée (elles ne touchent pas au modèle gelé).
- **Développement parallèle autorisé** dès maintenant (règle inchangée) : préparation du miroir FAQ, jeux de requêtes E3, suite Playwright E5, scripts de charge E6, infra E8 — tant que rien ne touche classifieur, décision, seuils, `loko-eval`.
- **Estimation cumulée** (hors E2b et hors disponibilité panel) : **15–22 jours ouvrés**. Le seul poste à variance forte est E2 (la qualité modèle) — tout le reste est de l'exécution de recette sur du code déjà livré.

## III.2 Les trois risques majeurs et leur parade

| Risque | Probabilité | Parade |
|---|---|---|
| **G-3 ne passe pas malgré W4** (l'enrichissement ne suffit pas) | Moyenne | E2b préparé à l'avance (dossier W5 : fusions d'intentions candidates, coût du re-figeage) — décision métier en une réunion, pas une crise. |
| **Récidive de dérive de campagne** (tests sautés, PASS présumés) | Élevée sans E0 | E0 rend la dérive matériellement impossible (runner + verdicts calculés). C'est pourquoi E0 est la première étape, avant tout code produit. |
| **Gel du modèle rompu en cours de route** (retrain « rapide » entre deux recettes) | Moyenne | Règle de gel rappelée à chaque gate : tout retrain post-E2 impose de rejouer V3-1→V3-6 avant de poursuivre. Le hash du manifeste est vérifié en prérequis de chaque gate E3→E7. |

## III.3 Registre des anomalies v0.3.7 → traitement

| Anomalie | Traitement | Étape |
|---|---|---|
| Bot 8 intentions, pas de L2, GNG-2 = 0 % | Correction `load_postulat` + CE-9 bloquant | E1 |
| Diagnostic « renommer le dataset » | **Rejeté** (interdit n°5) ; audit mapping labels côté code | E1 |
| V1 présumé PASS, V2-3/4/5 skippés, requalifications | Runner + protocole v2.2 + interdit n°9 | E0 |
| V2-6 P95 73 ms vs 28 ms (v0.3.6) | Machine de référence déclarée en CE | E0 (amendement) |
| V2-2 « exemples insuffisants » | Symptôme de la config — disparaît avec E1 | E1 |
| GNG-1 69 %/pièges 8/15 mesurés sur bot non conforme | Chiffres annulés ; référence re-mesurée | E1 |

---

# Annexe A — Gabarit commun des rapports de gate

```
# RAPPORT — Gate G-Ex — {date}
Version : tag {…}, commit {…}, digest image {…}
Manifeste modèle : hash {…} (inchangé depuis G-E2 : OUI/NON)
Exécution : runner {version}, machine de référence {id}

## Tableau des critères d'acceptance
| # | Critère | Seuil | Mesuré | Verdict | Artefact |
(toutes les lignes de l'étape — un critère non mesuré = FAIL)

## Anomalies produit découvertes (hors périmètre de la gate)
## Anomalies de protocole suspectées (n'altèrent pas les verdicts)

## Décision de gate : GO / NO-GO — signataire : {…}
NO-GO → étape de retour désignée + gates aval à rejouer
```

# Annexe B — Interdits opposables (rappel consolidé, v2.2)

1. Requalifier un test unitaire ou un exemple isolé en pourcentage GNG.
2. Mesurer depuis l'hôte au lieu du conteneur.
3. Omettre ou « skipper » une ligne du tableau de synthèse (non exécuté = FAIL).
4. Valider un critère « structurellement » / « au niveau code » sans exécution.
5. Toucher aux CSV held-out (y compris renommage de labels), ou entraîner avec.
6. Committer pendant la campagne sans repartir de V0-1 (hors dérogation V3-0 tracée).
7. Présenter des chiffres GNG à seuils non figés ou différents entre jeux.
8. Requalifier un FAIL en artefact de mesure pendant la campagne.
9. **Nouveau** : déclarer un gate ou un « R » validé sans exécution de toutes ses lignes ; les verdicts de gates sont calculés par le runner, jamais rédigés.
