import { Link } from "react-router-dom";
import { LokoLockup } from "@/components/ui/LokoLockup";

const PAGES: Record<string, { title: string; content: string }> = {
  cgu: {
    title: "Conditions Generales d'Utilisation",
    content: `Derniere mise a jour : juillet 2026

1. OBJET
Les presentes Conditions Generales d'Utilisation (CGU) regissent l'acces et l'utilisation de la plateforme LOKO.

2. ACCEPTATION
L'utilisation de la plateforme implique l'acceptation pleine et entiere des presentes CGU.

3. DESCRIPTION DU SERVICE
LOKO est une plateforme de creation et de gestion de chatbots deterministes pour le service client. Le service comprend la configuration de bots, l'entrainement de modeles de classification, et la mise en production de widgets conversationnels.

4. INSCRIPTION
L'acces aux fonctionnalites de la plateforme necessite la creation d'un compte. L'utilisateur s'engage a fournir des informations exactes et a maintenir la confidentialite de ses identifiants.

5. RESPONSABILITES
L'utilisateur est seul responsable du contenu configure dans ses bots, des reponses templates et des documents sources importes.

6. PROPRIETE INTELLECTUELLE
Les contenus, templates et configurations crees par l'utilisateur lui appartiennent. La plateforme LOKO et son code source restent la propriete de LOKO SAS.

7. RESILIATION
L'utilisateur peut supprimer son compte a tout moment. LOKO se reserve le droit de suspendre un compte en cas de non-respect des presentes CGU.

8. DROIT APPLICABLE
Les presentes CGU sont soumises au droit francais. Tout litige sera soumis aux tribunaux competents de Paris.`,
  },
  confidentialite: {
    title: "Politique de Confidentialite",
    content: `Derniere mise a jour : juillet 2026

1. RESPONSABLE DU TRAITEMENT
LOKO SAS est responsable du traitement des donnees personnelles collectees via la plateforme.

2. DONNEES COLLECTEES
- Donnees d'inscription : email, nom de l'organisation
- Donnees d'utilisation : logs de sessions, metriques de performance des bots
- Documents sources : fichiers importes pour l'entrainement des bots

3. FINALITES
Les donnees sont traitees pour :
- La fourniture du service de chatbot
- L'amelioration de la plateforme
- La communication avec les utilisateurs

4. BASE LEGALE
Le traitement est fonde sur l'execution du contrat (CGU) et le consentement de l'utilisateur.

5. DUREE DE CONSERVATION
Les donnees sont conservees pendant la duree du compte. Les sessions de chat sont purgees apres 7 jours (24 heures pour les bots de demonstration).

6. HEBERGEMENT
Les donnees sont hebergees en Europe (France).

7. DROITS DES UTILISATEURS
Conformement au RGPD, vous disposez des droits d'acces, de rectification, de suppression, de portabilite et d'opposition. Contact : privacy@loko.ai

8. COOKIES
La plateforme utilise un cookie de session (authentification) et un cookie CSRF (securite). Aucun cookie de tracking n'est utilise.`,
  },
  mentions: {
    title: "Mentions Legales",
    content: `Editeur
LOKO SAS
Siege social : Paris, France
Email : contact@loko.ai

Hebergement
Les services sont heberges en France.

Directeur de la publication
Henri -- Fondateur

Propriete intellectuelle
L'ensemble du contenu de la plateforme LOKO (textes, graphismes, logiciels, etc.) est protege par le droit de la propriete intellectuelle.

Credits
Plateforme developpee par LOKO SAS.
Typographie : Geist (Vercel).`,
  },
  contact: {
    title: "Contact",
    content: `Pour toute question relative a la plateforme LOKO :

Email general : contact@loko.ai
Support technique : support@loko.ai
Protection des donnees : privacy@loko.ai

Adresse
LOKO SAS
Paris, France

Nous nous efforcons de repondre a toute demande sous 48 heures ouvrees.`,
  },
};

interface LegalPageProps {
  page: string;
}

export function LegalPage({ page }: LegalPageProps) {
  const data = PAGES[page];

  if (!data) {
    return (
      <div style={{ padding: 40, textAlign: "center", fontFamily: "var(--font-sans)", background: "var(--surface-page)", color: "var(--text-primary)", minHeight: "100vh" }}>
        <p>Page introuvable.</p>
        <Link to="/" style={{ color: "var(--text-link)" }}>Retour</Link>
      </div>
    );
  }

  return (
    <div style={{ fontFamily: "var(--font-sans)", background: "var(--surface-page)", color: "var(--text-primary)", minHeight: "100vh" }}>
      {/* Header */}
      <div style={{ padding: "16px 40px", borderBottom: "1px solid var(--border-subtle)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <Link to="/" style={{ textDecoration: "none" }}>
          <LokoLockup height={20} />
        </Link>
        <Link
          to="/"
          style={{ fontSize: 13, color: "var(--text-link)", textDecoration: "none" }}
        >
          Retour
        </Link>
      </div>

      {/* Content */}
      <div style={{ maxWidth: 680, margin: "0 auto", padding: "48px 40px" }}>
        <h1 style={{ fontSize: 28, fontWeight: 600, marginBottom: 32, letterSpacing: "var(--tracking-tight)" }}>
          {data.title}
        </h1>
        <div style={{ fontSize: 14, lineHeight: "var(--leading-relaxed)", color: "var(--text-secondary)", whiteSpace: "pre-line" }}>
          {data.content}
        </div>
      </div>
    </div>
  );
}
