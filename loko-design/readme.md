# LOKO — Design System

LOKO est une plateforme self-serve B2B (Europe) qui permet à une entreprise de configurer, tester et déployer un chatbot de service client fiable, à partir de ses propres documents (RAG). Différenciateur : le **déterminisme** — le parcours conversationnel est une machine à états auditable, le bot clarifie avant de répondre, chaque réponse est traçable. Positionnement fort sur la souveraineté / confidentialité des données (traitement local, filtres de confidentialité).

Source : brief de marque fourni directement dans la conversation (aucun repo/Figma attaché). Ce projet **est** le design system — il n'y avait pas de système existant à explorer ; tout ce qui suit a été conçu à partir du brief.

## Personnalité de marque (par priorité)
1. Fiable / maîtrisé — rien d'aléatoire.
2. Clair / précis — qualifie avant de répondre.
3. Sobre et professionnel, mais accessible (self-serve, non-techniciens).
4. Souverain / de confiance — les données restent chez le client.

À éviter : clichés IA (cerveaux, circuits, dégradés violet/bleu néon, étincelles, robots), esthétique gadget, surcharge visuelle.

## Logo — 3 directions explorées, 1 retenue (v2 : direction C)
Voir `guidelines/brand/logo-directions.html` (Design System tab, groupe **Brand**) pour le comparatif avec rationale complet.

- **A — Trou de serrure évoluée** : le glyphe existant, redessiné en géométrie pure (cercle + trapèze). Lisible à 16px, mais retour client : trop littéral, se lit comme une icône générique de "sécurité" plutôt que comme une marque distinctive. Écartée en v2.
- **B — Machine à états** : nœuds + transition, le plus juste conceptuellement mais illisible en petite taille et redondant avec le motif graphique — traité comme motif secondaire plutôt que glyphe (`guidelines/brand/motif.html`).
- **C — Typographique pure (retenue)** : aucun pictogramme séparé. Le dernier "O" du mot LOKO est redessiné en disque plein avec une fente étroite (découpe en négatif, `fill-rule="evenodd"` — fonctionne en un seul trait, sur n'importe quel fond). Cette même forme, isolée, redevient le glyphe seul (app icon/favicon) : une seule source de vérité pour le mot et l'icône.

Système final dans `guidelines/brand/logo-final.html` et `assets/logo/` : glyphe seul (couleur / mono noir / mono blanc), lockup horizontal (LOK + O signature), app icon.

## Index

- `styles.css` — point d'entrée CSS (import unique, jamais de règles inline).
- `tokens/` — `colors.css` (vert de marque, accent bronze, neutres, sémantique, light+dark), `typography.css` (Geist / Geist Mono via Google Fonts), `spacing.css`, `effects.css` (ombres, easing).
- `assets/logo/` — SVG : `glyph-color.svg`, `glyph-mono-black.svg`, `glyph-mono-white.svg`, `glyph-bare-green.svg`, `lockup-horizontal-*.svg`.
- `guidelines/brand/` — directions du logo, système final, motif graphique, iconographie.
- `guidelines/colors/`, `guidelines/type/`, `guidelines/spacing/` — spécimens des fondations.
- `components/chat/` — primitives du widget : `ChatLauncher`, `MessageBubble`, `ChoiceButtons`, `StreamingIndicator`, `StateTraceBadge`.
- `ui_kits/chatbot-widget/` — bulle flottante + fenêtre de conversation sur un site client fictif, bascule light/dark.
- `ui_kits/brand-board/` — planche récapitulative (logo, palette, typo, console admin, widget, carte OG).

## CONTENT FUNDAMENTALS
- Ton : sobre, direct, orienté "preuve" — on montre l'état, la source, le score plutôt que d'affirmer sans justification. Pas d'exclamations, pas d'émoji décoratif (un seul emoji d'accueil 👋 toléré dans le premier message du bot, jamais ailleurs).
- Vouvoiement en français (le produit s'adresse à des décideurs/admin non techniciens) ; copie B2B, jamais familière.
- Toujours nommer la source ou l'état quand le bot répond ("cgv-2026.pdf · state.confirm_return") — la traçabilité est un argument produit, pas un détail technique caché.
- Pas de superlatifs marketing IA ("révolutionnaire", "magique", "intelligent"). Le vocabulaire tourne autour de : fiable, maîtrisé, traçable, auditable, souverain, déterministe.

## VISUAL FOUNDATIONS
- **Couleur** : vert de marque `#0F7D63` conservé (voir rationale ci-dessous), un seul accent bronze `#A8752D` réservé aux mises en avant/focus (jamais aux alertes). Neutres graphite froid pour ne pas concurrencer le vert. Succès réutilise le vert de marque plutôt qu'un second vert — moins de couleurs à mémoriser.
- **Type** : Geist (UI, titres, corps) + Geist Mono exclusivement pour les valeurs techniques (états, scores, timestamps, IDs) — la mono est elle-même un signal de fiabilité/traçabilité.
- **Fond** : pas d'images plein cadre, pas de dégradés décoratifs. Le seul motif graphique est le lattice nœuds/transitions en surimpression très légère (opacité ≤ 0.35) ou le trou de serrure répété en filigrane sur fond vert foncé pour le marketing (`guidelines/brand/motif.html`).
- **Animation** : minimale et calme. L'indicateur de streaming pulse en opacité (jamais de rebond/bounce) — signal de traitement, pas de "magie IA". Transitions standards 120–320ms, easing `cubic-bezier(0.4,0,0.2,1)`.
- **Hover/press** : hover = teinte plus foncée d'un cran sur la même couleur (`--brand-primary-hover`) ; jamais d'ombre colorée ou de halo. Press = teinte encore plus foncée (`--brand-primary-active`), pas de scale.
- **Ombres** : neutres (teinte grise, jamais teintées de vert), très basses — `--shadow-sm/md/lg`, utilisées avec parcimonie (cartes, widget flottant uniquement).
- **Rayons** : sobres, 8–16px pour les surfaces, pill pour les boutons de choix et badges, `22%` pour l'app icon (superellipse douce, pas un cercle parfait).
- **Cartes** : fond `--surface-card`, bordure 1px `--border-subtle`, pas d'ombre en repos sauf éléments flottants (widget, popovers).
- **Transparence/flou** : overlay de modale seulement (`--surface-overlay`), pas de glassmorphism/blur décoratif.
- **Light/dark** : chaque token a son équivalent dans les deux thèmes (`tokens/colors.css`, blocs `:root`/`[data-theme="light"]` et `[data-theme="dark"]`) ; contrastes vérifiés AA sur texte/fond pour les combinaisons principales.

## ICONOGRAPHIE
Aucun set d'icônes n'était fourni. Substitution : **Lucide** (CDN), trait 1.75px, angles arrondis — cohérent avec la géométrie de Geist et le glyphe. Voir `guidelines/brand/iconography.html`. Pas d'emoji en dehors du "👋" d'accueil ; pas de caractères unicode utilisés comme icônes.

## Intentional additions (composants sans source à copier)
Aucune source de composants existante (pas de Figma/codebase attaché) : le set de primitives ci-dessus a été conçu directement pour le besoin exprimé (widget chatbot), pas comme un set générique Button/Input/Card — celles-ci n'ont pas été demandées et n'auraient rien à recréer sans plus de contexte produit.

## Produit — Wizard de configuration (v1 : composant trace + parcours complet)

Périmètre de cette passe (sur 10 écrans demandés au total) : le composant trace réutilisable, et le wizard de configuration du bot (étapes 1 à 6) en prototype cliquable, light/dark. Dashboard et widget adhérent (déjà esquissé dans `ui_kits/chatbot-widget/`) restent à faire dans une prochaine passe.

- **`TraceTimeline.dc.html`** — composant trace signature du produit : timeline verticale classification → clarification → retrieval → génération, score vs seuil en Geist Mono, code couleur de confiance (vert/ambre/rouge), sources citées, distinction visible template verrouillé 🔒 vs génération LLM. Props `variant` (`full`/`mini`) et `steps` pour le réutiliser dans d'autres contextes (dashboard, détail de session) plus tard.
- **`LOKO Wizard.dc.html`** — prototype cliquable des 6 étapes : Projet, Intentions (éditeur + entraînement simulé + matrice de confusion + conseils actionnables), Connaissances (upload, connecteur FAQ, table de tagging, couverture par intention), Parcours (curseurs à 2 seuils avec zones route directe/clarification/rejet + schéma d'états), Messages (templates verrouillés par état + aperçu widget live), Simulation & publication (playground conversation + trace en direct, historique d'essais, checklist de publication, cas bloqué "ré-entraînement requis", succès avec clé API + snippet).
- Toggle clair/sombre dans l'en-tête du wizard, navigation libre entre étapes visitées, avatar de bot dédié (`assets/logo/bot-avatar-*.svg`, distinct du wordmark — anneau + tige, inspiré du trou de serrure sans être littéral).

## Dashboard & Widget adhérent (v1)

- **`LOKO Dashboard.dc.html`** — bandeau KPI (sessions, selfcare, escalades, latence P50, feedback), selfcare par intention, motifs d'escalade, retours négatifs avec boucle 1-clic (Ajouter comme exemple → Ré-entraîner), sessions récentes avec détail (transcript + `TraceTimeline` en variant mini par tour).
- **`LOKO Widget.dc.html`** — widget adhérent mobile-first en cadre téléphone : bulle flottante, fenêtre de conversation, choix fermés, indicateur de streaming, feedback 👍/👎 discret, source citée en pied de réponse documentée, reprise de session, thème auto (`prefers-color-scheme`) + toggle démo. Prop tweakable `accentColor` (4 teintes curatées) pour la personnalisation client sans casser l'identité.

## Caveats
- Les wordmarks SVG utilisent `<text font-family="Geist">` — à vectoriser (outline) avant distribution externe (impression, partenaires) pour un rendu garanti sans dépendance à la police chargée.
- Palette et système entièrement conçus à partir du brief texte ; aucune maquette produit existante n'a été fournie pour l'admin console — la vignette "console admin" du brand board est illustrative, pas une recréation d'écran réel.
