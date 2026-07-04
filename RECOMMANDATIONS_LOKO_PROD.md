# 🛠️ LOKO — Recommandations pour la mise en production

> **Version** : 1.0 — 3 juillet 2026
> **Entrées** : `RAPPORT_TEST_E2E_LOKO.md` (campagne du 3 juillet), `POSTULAT_TEST_E2E_LOKO.md` v1.0, specs de cadrage et de dev
> **Verdict de lecture** : la coquille est prête, le cœur n'a pas encore été mis sous tension.

---

## 1. Lecture du rapport : ce qui est réellement validé

Le rapport est bon signe sur un point structurel : **les décisions d'architecture tiennent**. Le moteur pur (`engine.step` sans I/O) a permis de valider la FSM, la règle d'or (max 1 clarification), le décompte des reformulations et la persistance SQLite WAL sans dépendre du ML — c'était exactement l'objectif de cette conception. Le dashboard, la boucle d'amélioration, le streaming SSE et les validations bloquantes de publication fonctionnent.

Mais il faut être lucide sur ce que le mock classifier a masqué : **la totalité de la proposition de valeur de LOKO face à Odigo n'a pas été testée**. Classification L1/L2, clarifications inter et intra, retrieval filtré par tags, génération avec citations, déclenchement réel des 4 motifs d'escalade, enquête de satisfaction — aucun scénario S1–S9 n'a dépassé l'état `CLASSIFICATION_L1`. Les critères Go/No-Go 1, 2, 3, 6 et 8 sont non testables, dont le **n°6 (fuite confidentielle), pourtant éliminatoire**. Les PASS de P5 (déterminisme) et P6 (latence) sont explicitement triviaux dans le rapport lui-même.

Conclusion : LOKO n'est pas « presque prêt » ; il est **prêt à moitié, la bonne moitié étant celle qui se répare le moins souvent**. Les recommandations ci-dessous sont organisées en 5 chantiers, du plus bloquant au plus cosmétique, avec un plan séquencé en §7.

---

## 2. Chantier A — Remettre le ML sous tension (débloque P1, puis tout le reste)

### A1. Stratégie Docker pour les dépendances ML — décision d'architecture à acter

Le rapport propose `pip install -e ".[server,ml]"` en signalant +2–3 Go. Trois options, avec une recommandation claire :

| Option | Description | Verdict |
|---|---|---|
| **A1a — Image unique `[server,ml]` avec torch CPU-only** | Multi-stage + `pip install torch --index-url https://download.pytorch.org/whl/cpu` avant setfit. L'image passe de ~3 Go à **~1,2–1,5 Go** (pas de wheels CUDA). | ✅ **Recommandée pour la v1** |
| A1b — Service ML séparé (sidecar) | Un conteneur `loko-ml` exposant train/infer en gRPC/HTTP interne. | Sur-ingénierie pour un produit mono-nœud CPU (spec §perf : ≥ 50 sessions sur un nœud). À garder pour une v2 multi-bots. |
| A1c — Deux tags d'image (`loko:slim`, `loko:full`) | Slim = runtime sans entraînement, full = admin+train. | Séduisant mais casse la promesse « le bot vit et s'améliore en production » : la boucle P8 (retrain 1-clic) exige le ML dans l'image de prod. |

Décisions associées à A1a :
- **Pré-embarquer le modèle de base** (`paraphrase-multilingual-MiniLM-L12-v2`, ~470 Mo) dans l'image via `HF_HOME` fixé, ou à défaut téléchargement au premier entraînement avec barre de progression réutilisant le pattern d'ingestion. Un conteneur de prod **ne doit pas dépendre d'un accès Hugging Face à chaud** (environnements clients sans egress).
- Variable d'env documentée `LOKO_ML=on|off` pour permettre un mode dégradé explicite (runtime seul, entraînement désactivé avec message clair) plutôt que l'échec silencieux actuel (`No module named 'setfit'` découvert *après* le lancement du job).
- **Fail-fast au démarrage** : si le bot est publié et son modèle absent/corrompu, refuser de démarrer le runtime plutôt que retomber sur `_MockClassifier`. Le mock ne doit être injectable **qu'en environnement de test** (garde-fou : lever une exception si `_MockClassifier` est instancié hors `RAGKIT_ENV=test`). C'est le risque le plus sournois révélé par cette campagne : un mock qui répond `hors_perimetre` à 0.5 ressemble à un bot vivant.

### A2. Rejouer P1 en entier dès A1 livré

Entraînement des 8 intentions + niveau 2 `services_en_ligne`, matrice de confusion (confusion attendue `cotisations`↔`changement_coordonnees`), conseils actionnables, cycle correction→ré-entraînement, latence d'inférence mesurée dans le budget 20–50 ms **dans le conteneur** (pas depuis l'hôte). Les 3 tests `@pytest.mark.slow` skippés doivent tourner dans la CI au moins en job nightly.

---

## 3. Chantier B — La base de connaissances n'existe pas encore côté API (débloque P2, critères 6 et 8)

Le rapport révèle un trou plus large qu'un oubli de dépendance : **aucun endpoint d'ingestion/tagging, retriever `InMemorySearchBackend` vide, connecteur crawl non exposé**. Or la spec dev avait acté la réutilisation de l'existant RAGKIT (`ragkit/desktop/api/ingestion.py`, pipeline de métadonnées, retrieval hybride BM25+vectoriel). La recommandation n'est donc pas de développer un module knowledge, mais de **brancher celui qui existe** :

1. **B1 — Monter le pipeline d'ingestion RAGKIT dans le scope bot.** Réutiliser les routes d'ingestion existantes en les rattachant à `config.knowledge_collection` (aujourd'hui un string vide sans effet). Ajouter les endpoints manquants prévus par la spec :
   - `PATCH /api/bot/{id}/documents/tags` (tagging en masse intention/sous-motif, métadonnées de premier ordre) ;
   - `GET /api/bot/{id}/knowledge/coverage` (nombre de documents par intention) pour alimenter l'**alerte de couverture** de l'étape 3 et de la publication — c'est l'exemple `resiliation` du protocole.
2. **B2 — Remplacer `InMemorySearchBackend` par le backend persistant existant** (hybride BM25+vectoriel de RAGKIT), avec deux exigences non négociables :
   - le **filtrage par tag intention/sous-motif et le filtre de confidentialité s'appliquent dans la requête** (pré-filtrage dur), jamais en post-filtrage des résultats — c'est la seule façon de rendre le critère éliminatoire n°6 démontrable par construction ;
   - le fallback « sous-motif → intention entière » de la spec §retrieval reste déterministe et tracé.
3. **B3 — Exposer le connecteur `faq_web_crawler`** (le code existe) : formulaire étape 3 (URL racine, profondeur, planification, aperçu avant ingestion) + endpoint de déclenchement + resync diff par hash. Point d'attention Docker : Playwright + Chromium ajoutent ~400 Mo et des dépendances système. Deux voies acceptables : les inclure dans l'image unique (simplicité), ou décider que **le crawl est une opération d'administration** exécutable aussi depuis le poste (desktop Tauri) avec push vers le serveur — à trancher, mais ne pas laisser le connecteur orphelin.
4. **B4 — Tests associés à écrire immédiatement** : test automatisé « document confidentiel taggé `cotisations` → 0 apparition dans chunks/trace/réponse sur 50 requêtes » (critère 6), et test de citation `source_url` (critère 8).

---

## 4. Chantier C — Sécurité runtime : le trou le plus grave du rapport (P7)

Le constat est sec : **`api_keys.py` implémente tout (generate, validate, revoke, check_origin) mais aucune route ne le monte, et les endpoints `/api/v1/bot/*` sont ouverts sans clé ni vérification d'origine**. En l'état, n'importe qui peut créer des sessions et consommer le LLM du client. C'est un no-go absolu de mise en production, indépendamment du ML.

1. **C1 — Monter les routes de gestion des clés** (`POST/GET/DELETE /api/bot/{id}/api-keys`) dans l'admin, avec le scoping bot+origine prévu par la spec (claims ou table de mapping). La génération du snippet widget à l'étape 6 doit consommer ces routes.
2. **C2 — Middleware d'authentification sur tout `/api/v1/bot/*`** : `Depends(verify_api_key)` validant clé + correspondance `Origin`/`Referer` avec les origines déclarées, CORS restreint en cohérence. Réutiliser l'`ApiKeyMiddleware` existant du mode serveur RAGKIT plutôt que d'en réécrire un.
3. **C3 — Garde-fous de consommation** : rate limiting par clé et par session (même simple : token bucket en mémoire par bot), plafond de messages par session déjà couvert par `max_demandes`, mais rien ne limite la création de sessions. Sans cela, la facture LLM du client est une surface d'attaque.
4. **C4 — Fallback SPA** : remplacer `StaticFiles(html=True)` seul par un catch-all (`@app.get("/{path:path}")` renvoyant `index.html` pour toute route non-API/non-static/non-widget). Trivial, mais bloquant pour l'usage réel de l'admin (deep-links, refresh navigateur, liens partagés vers un replay).

---

## 5. Chantier D — Intégrité des données d'observabilité et de la boucle d'amélioration

Deux anomalies du rapport paraissent mineures et ne le sont pas :

1. **D1 — Traces non persistées** (`GET /traces` vide, `store.add_trace()` jamais appelé dans le flux message). Conséquence : le replay du dashboard — argument produit central face à Odigo (« chaque décision est traçable ») — ne montre pas les scores ni les latences des conversations passées. Persister chaque trace au fil du tour (même transaction que le transcript), avec une politique de rétention configurable.
2. **D2 — Bug `get_misclassified_turns` : `user_message` contient le message du bot.** C'est plus qu'un bug d'affichage : la boucle P8 « 1 clic → ajouter comme exemple » consommerait ce champ et **injecterait des phrases du bot dans le dataset d'entraînement**, polluant silencieusement le classifieur à chaque itération d'amélioration. Corriger la requête SQL **et** ajouter un garde-fou côté `add-example` : refuser tout exemple identique à un template connu du bot.
3. **D3 — Template de présentation** : confirmer que l'accueil consomme la variable `{intentions_gerees}` (le rapport a un doute). Test simple : ajouter une 9ᵉ intention, republier, vérifier l'accueil sans toucher au template.
4. **D4 — Nettoyage CI** : enregistrer `pytest.mark.slow` dans `pyproject.toml`, migrer les deprecation warnings (httpx, React Router v7). Faible coût, à glisser dans le premier sprint pour que la CI reste un signal propre.

---

## 6. Chantier E — Campagne de revalidation (le protocole n'est pas terminé, il est suspendu)

Une fois A+B+C livrés, la campagne du 3 juillet doit être **rejouée, pas complétée** : les PASS de P3, P5 et P6 sont conditionnés au mock et n'ont pas valeur de recette.

| Reprise | Contenu | Critère de sortie |
|---|---|---|
| P1 complet | Entraînement réel, matrice, cycle correction, latence in-container | Matrice cohérente, inférence 20–50 ms |
| P2 complet | Crawl FAQ MGEN, tagging, alerte `resiliation` à 2 docs, doc confidentiel | Alerte levée, critère 6 = 0 fuite |
| P3 : T01–T15 + S1–S9 | Held-out du postulat, y compris les pièges (« RIB coordonnées bancaires », « attestation de paiement », « Noemie ») | Go/No-Go 1 : ≥ 85 % |
| P4 réel | Les 4 motifs déclenchés en conditions réelles, payload + `temps_attente_estime_min` | 4/4 conformes |
| P5 non trivial | **Rejeu automatisé S1–S9 en CI** avec classifieur entraîné et index figé : séquences d'états/messages système identiques sur 2 exécutions | 100 %, éliminatoire |
| P6 réel | Budget par étape mesuré in-container (la baseline réseau Docker→hôte de ~200 ms observée doit être isolée de la mesure) | Budgets spec tenus |
| Éval statistique | Script d'évaluation batch (à livrer) : 100 verbatims held-out du dataset, 126 `parler_conseiller`, 100 hors-scope | Go/No-Go 1–3 |
| P7 sécurité | Requête sans clé → 401, origine non déclarée → refus, rate limit → 429 | 100 % |

Livrable outillé recommandé : un **script `loko-eval`** (CLI) qui prend un CSV `text,intent` et produit précision/rappel par classe + les cas frontière, exécutable en CI. Il servira aussi aux clients pour recetter leurs propres bots — c'est un actif produit, pas seulement un outil de test.

---

## 7. Plan séquencé et critères de « prêt »

| Sprint | Contenu | Débloque |
|---|---|---|
| **S1 (bloquants, ~1 sem.)** | A1 (image ML CPU-only + modèle embarqué + fail-fast mock), C1+C2 (clés API + middleware), C4 (SPA), D1+D2 (traces + bug misclassified) | P1, P7, intégrité P8 |
| **S2 (knowledge, ~1–2 sem.)** | B1–B4 (ingestion branchée, backend persistant, filtrage dur, crawler exposé, tests confidentialité/citation) | P2, critères 6 et 8 |
| **S3 (recette, ~1 sem.)** | Chantier E complet + `loko-eval` + C3 (rate limiting) + D3/D4 | Go/No-Go 1–8 |

**Définition de « LOKO prêt »** — reprendre les critères du postulat, désormais tous mesurables, avec deux ajouts issus de cette campagne :

1. Les 8 critères Go/No-Go du protocole passent, les n° 4, 5, 6 restant éliminatoires.
2. **Nouveau critère éliminatoire n°9 — sécurité runtime** : aucun endpoint `/api/v1/bot/*` accessible sans clé valide et origine déclarée.
3. **Nouveau critère éliminatoire n°10 — pas de mode dégradé silencieux** : aucun composant mock (classifieur, retriever, LLM, escalade) instanciable hors environnement de test ; un bot publié dont un composant réel est indisponible refuse de servir avec une erreur explicite.

Le point encourageant mérite d'être dit en conclusion : rien dans ce rapport ne remet en cause l'architecture. Les échecs sont des **absences de branchement** (deps, routes, backend) et non des défauts de conception — le moteur pur, la persistance et le contrat SSE ont précisément joué leur rôle de fondation testable. Les trois sprints ci-dessus sont du câblage et de la recette, pas de la re-conception.
