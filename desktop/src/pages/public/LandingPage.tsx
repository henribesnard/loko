import { useEffect } from "react";
import { Link } from "react-router-dom";
import { LokoLockup } from "@/components/ui/LokoLockup";

// ---------------------------------------------------------------------------
// F5: Demo widget — loads the real widget when a demo bot is configured.
// Set VITE_DEMO_BOT_ID (and optionally VITE_DEMO_API_KEY) to enable.
// ---------------------------------------------------------------------------

const DEMO_BOT_ID = (
  typeof import.meta !== "undefined" && import.meta.env?.VITE_DEMO_BOT_ID
) as string | undefined;
const DEMO_API_KEY = (
  typeof import.meta !== "undefined" && import.meta.env?.VITE_DEMO_API_KEY
) as string | undefined;

function DemoWidget() {
  useEffect(() => {
    if (!DEMO_BOT_ID) return;

    const script = document.createElement("script");
    script.src = "/widget/loko-widget.js";
    script.setAttribute("data-bot-id", DEMO_BOT_ID);
    script.setAttribute("data-api-url", window.location.origin);
    if (DEMO_API_KEY) script.setAttribute("data-api-key", DEMO_API_KEY);
    document.body.appendChild(script);

    return () => {
      script.remove();
      document.querySelectorAll("loko-widget").forEach((el) => el.remove());
    };
  }, []);

  if (DEMO_BOT_ID) {
    return (
      <div style={{ maxWidth: 400, margin: "0 auto", textAlign: "center", padding: "40px 20px" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-tertiary)", marginBottom: 12 }}>
          Le widget LOKO apparait en bas a droite de cette page.
        </div>
        <div style={{ fontSize: "14px", color: "var(--text-secondary)" }}>
          Cliquez dessus pour discuter avec le bot de demonstration en conditions reelles.
        </div>
      </div>
    );
  }

  // Fallback: static demo when no demo bot is configured
  return (
    <div style={{ maxWidth: 400, margin: "0 auto", border: "2px solid var(--brand-primary-border)", borderRadius: "var(--radius-xl)", padding: 6, position: "relative" }}>
      <div style={{ position: "absolute", top: -11, left: "50%", transform: "translateX(-50%)", background: "var(--brand-primary)", color: "var(--text-on-brand)", fontFamily: "var(--font-mono)", fontSize: "10px", fontWeight: 600, padding: "3px 10px", borderRadius: 999 }}>DEMO</div>
      <div style={{ background: "var(--surface-page)", borderRadius: "var(--radius-lg)", overflow: "hidden", display: "flex", flexDirection: "column", height: 400 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 9, padding: "13px 14px", borderBottom: "1px solid var(--border-subtle)", background: "var(--surface-card)" }}>
          <svg width="24" height="24" viewBox="0 0 64 64"><rect x="1" y="1" width="62" height="62" rx="14" fill="var(--brand-primary)" /><circle cx="32" cy="25" r="10" fill="none" stroke="#fff" strokeWidth="4" /><path d="M32 33 L32 44" stroke="#fff" strokeWidth="4" strokeLinecap="round" /></svg>
          <div style={{ fontSize: "13px", fontWeight: 600 }}>Assistant demo</div>
        </div>
        <div style={{ flex: 1, padding: 14, display: "flex", flexDirection: "column", gap: 12, background: "var(--surface-sunken)", justifyContent: "center", alignItems: "center" }}>
          <div style={{ fontSize: "13px", color: "var(--text-tertiary)", textAlign: "center", maxWidth: 280 }}>
            Le widget de demonstration sera disponible une fois le bot demo configure.
          </div>
          <Link to="/signup" style={{ padding: "8px 16px", borderRadius: "var(--radius-md)", background: "var(--brand-primary)", color: "var(--text-on-brand)", fontSize: "13px", fontWeight: 600, textDecoration: "none" }}>
            Creer un compte pour essayer
          </Link>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step card (6-step grid)
// ---------------------------------------------------------------------------

function StepCard({ num, label, children }: { num: number; label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ height: 74, borderRadius: "var(--radius-md)", background: "var(--surface-sunken)", border: "1px solid var(--border-subtle)", display: "flex", alignItems: "center", justifyContent: "center", padding: 8 }}>
        {children}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
        <div style={{ width: 18, height: 18, borderRadius: "50%", background: "var(--brand-primary-tint)", color: "var(--green-700)", fontFamily: "var(--font-mono)", fontSize: "9.5px", fontWeight: 600, display: "flex", alignItems: "center", justifyContent: "center", flex: "none" }}>{num}</div>
        <div style={{ fontSize: "12.5px", fontWeight: 600 }}>{label}</div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Trust card
// ---------------------------------------------------------------------------

function TrustCard({ title, text, icon }: { title: string; text: string; icon?: React.ReactNode }) {
  return (
    <div style={{ background: "var(--surface-card)", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-lg)", padding: 26 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        {icon}
        <div style={{ fontSize: 16, fontWeight: 600 }}>{title}</div>
      </div>
      <div style={{ fontSize: "13.5px", color: "var(--text-secondary)", lineHeight: "var(--leading-relaxed)" }}>{text}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main landing page
// ---------------------------------------------------------------------------

export function LandingPage() {
  return (
    <div style={{ fontFamily: "var(--font-sans)", background: "var(--surface-page)", color: "var(--text-primary)", minHeight: "100vh" }}>
      {/* Nav */}
      <div style={{ position: "sticky", top: 0, zIndex: 10, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 40px", background: "var(--surface-page)", borderBottom: "1px solid var(--border-subtle)" }}>
        <LokoLockup height={20} />
        <div style={{ display: "flex", alignItems: "center", gap: 32 }}>
          <div style={{ display: "flex", gap: 28, fontSize: "13.5px", color: "var(--text-secondary)" }}>
            <a href="#preuve" style={{ color: "inherit", textDecoration: "none" }}>Le produit</a>
            <a href="#parcours" style={{ color: "inherit", textDecoration: "none" }}>Comment ça marche</a>
            <a href="#tarifs" style={{ color: "inherit", textDecoration: "none" }}>Tarifs</a>
          </div>
          <div style={{ display: "flex", gap: 10 }}>
            <Link to="/login" style={{ padding: "8px 16px", borderRadius: "var(--radius-md)", border: "1px solid var(--border-default)", background: "transparent", color: "var(--text-primary)", fontSize: "13px", fontWeight: 500, textDecoration: "none", display: "inline-flex", alignItems: "center" }}>Connexion</Link>
            <Link to="/signup" style={{ padding: "8px 16px", borderRadius: "var(--radius-md)", border: "none", background: "var(--brand-primary)", color: "var(--text-on-brand)", fontSize: "13px", fontWeight: 600, textDecoration: "none", display: "inline-flex", alignItems: "center" }}>Créer un compte</Link>
          </div>
        </div>
      </div>

      {/* Hero */}
      <div style={{ padding: "88px 40px 64px", maxWidth: 1180, margin: "0 auto", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 56, alignItems: "center" }}>
        <div>
          <div style={{ display: "inline-flex", alignItems: "center", gap: 6, fontFamily: "var(--font-mono)", fontSize: "11.5px", fontWeight: 600, color: "var(--green-700)", background: "var(--brand-primary-tint)", border: "1px solid var(--brand-primary-border)", borderRadius: 5, padding: "4px 9px", marginBottom: 20 }}>Plateforme self-serve — Europe</div>
          <div style={{ fontSize: 44, fontWeight: 600, lineHeight: "var(--leading-tight)", letterSpacing: "var(--tracking-tight)", marginBottom: 20 }}>Le chatbot de service client qui ne répond jamais à côté — et qui vous montre pourquoi.</div>
          <div style={{ fontSize: 17, color: "var(--text-secondary)", lineHeight: "var(--leading-relaxed)", marginBottom: 32, maxWidth: 480 }}>Configuré par vos équipes, sans compétence technique, en une demi-journée.</div>
          <div style={{ display: "flex", gap: 12 }}>
            <Link to="/signup" style={{ padding: "13px 24px", borderRadius: "var(--radius-md)", border: "none", background: "var(--brand-primary)", color: "var(--text-on-brand)", fontSize: "14.5px", fontWeight: 600, textDecoration: "none", display: "inline-flex", alignItems: "center" }}>Créer un compte</Link>
            <a href="#demo" style={{ padding: "13px 24px", borderRadius: "var(--radius-md)", border: "1px solid var(--border-default)", background: "transparent", color: "var(--text-primary)", fontSize: "14.5px", fontWeight: 500, textDecoration: "none", display: "inline-flex", alignItems: "center" }}>Voir la démo</a>
          </div>
        </div>

        {/* Stylized playground capture */}
        <div style={{ background: "var(--surface-card)", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-xl)", boxShadow: "var(--shadow-lg)", overflow: "hidden" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "10px 14px", borderBottom: "1px solid var(--border-subtle)", background: "var(--surface-sunken)" }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--border-strong)" }} />
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--border-strong)" }} />
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--border-strong)" }} />
            <div style={{ flex: 1, textAlign: "center", fontFamily: "var(--font-mono)", fontSize: "10.5px", color: "var(--text-tertiary)" }}>Playground — Mutuelle Verdier</div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1.1fr 1fr", gap: 0 }}>
            <div style={{ background: "var(--gray-900)", padding: 16, display: "flex", flexDirection: "column", gap: 10, minHeight: 280 }}>
              <div style={{ alignSelf: "flex-end", maxWidth: "80%", background: "var(--brand-primary)", color: "#fff", borderRadius: "14px 4px 14px 14px", padding: "9px 13px", fontSize: "12.5px" }}>Je veux résilier mon contrat</div>
              <div style={{ alignSelf: "flex-start", maxWidth: "80%", background: "#232B28", color: "#F2F5F3", borderRadius: "4px 14px 14px 14px", padding: "9px 13px", fontSize: "12.5px" }}>Votre résiliation est enregistrée. Confirmation par e-mail sous 24h.</div>
            </div>
            <div style={{ padding: 14, display: "flex", flexDirection: "column", gap: 10, background: "var(--surface-page)" }}>
              <div style={{ fontSize: "10.5px", fontWeight: 600, color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: "0.03em" }}>Trace</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {[
                  { label: "Classification", detail: "score 0.93 · seuil 0.75" },
                  { label: "Retrieval", detail: "cgv-2026.pdf · 90%" },
                  { label: "Génération", detail: 'template « fin » · 40ms' },
                ].map((step) => (
                  <div key={step.label} style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                    <div style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--green-500)", marginTop: 3, flex: "none" }} />
                    <div>
                      <div style={{ fontSize: "11.5px", fontWeight: 600 }}>{step.label}</div>
                      <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-tertiary)" }}>{step.detail}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Preuve par la trace */}
      <div id="preuve" style={{ padding: "80px 40px", background: "var(--surface-card)", borderTop: "1px solid var(--border-subtle)", borderBottom: "1px solid var(--border-subtle)" }}>
        <div style={{ maxWidth: 1180, margin: "0 auto", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 56, alignItems: "center" }}>
          <div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "11.5px", fontWeight: 600, color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 14 }}>L'anti-boîte-noire</div>
            <div style={{ fontSize: 30, fontWeight: 600, letterSpacing: "var(--tracking-tight)", lineHeight: "var(--leading-tight)", marginBottom: 18 }}>Chaque réponse est traçable.</div>
            <div style={{ fontSize: 15, color: "var(--text-secondary)", lineHeight: "var(--leading-relaxed)", marginBottom: 20, maxWidth: 460 }}>Intention détectée, score de confiance, documents utilisés, latence par étape — rien n'est caché. Quand le bot répond, vous savez pourquoi. Quand il se trompe, vous voyez où.</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {[
                "Scores réels, seuils affichés, jamais de jauge décorative",
                "Sources citées pour toute réponse documentée",
                "Distinction visible entre message écrit par vous et génération",
              ].map((text) => (
                <div key={text} style={{ display: "flex", gap: 8, alignItems: "baseline", fontSize: "13.5px", color: "var(--text-primary)" }}>
                  <span style={{ color: "var(--brand-primary)", fontWeight: 600 }}>—</span> {text}
                </div>
              ))}
            </div>
          </div>
          {/* Trace timeline illustration */}
          <div style={{ background: "var(--surface-page)", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-lg)", padding: 24 }}>
            <div style={{ fontSize: "10.5px", fontWeight: 600, color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: "0.03em", marginBottom: 16 }}>Decision Trace</div>
            {[
              { label: "Classification L1", score: "0.93", threshold: "0.75", color: "var(--green-500)" },
              { label: "Clarification", score: "—", threshold: "", color: "var(--text-tertiary)" },
              { label: "Retrieval L2", score: "0.88", threshold: "0.70", color: "var(--green-500)" },
              { label: "Génération", score: "template", threshold: "40ms", color: "var(--green-500)" },
            ].map((step, i, arr) => (
              <div key={step.label} style={{ display: "flex", gap: 12, paddingBottom: i < arr.length - 1 ? 16 : 0, marginBottom: i < arr.length - 1 ? 16 : 0, borderLeft: i < arr.length - 1 ? "1px solid var(--border-subtle)" : "none", marginLeft: 5, paddingLeft: 16 }}>
                <div style={{ width: 10, height: 10, borderRadius: "50%", background: step.color, marginLeft: -22, marginTop: 2, flex: "none" }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: "12.5px", fontWeight: 600, marginBottom: 2 }}>{step.label}</div>
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-tertiary)" }}>
                    {step.score !== "—" ? `score ${step.score}` : "skipped"}{step.threshold ? ` · ${step.threshold}` : ""}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Parcours 6 étapes */}
      <div id="parcours" style={{ padding: "80px 40px", maxWidth: 1180, margin: "0 auto" }}>
        <div style={{ textAlign: "center", marginBottom: 44 }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "11.5px", fontWeight: 600, color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 12 }}>Comment ça marche</div>
          <div style={{ fontSize: 28, fontWeight: 600, letterSpacing: "var(--tracking-tight)" }}>Six étapes, une demi-journée</div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 14 }}>
          <StepCard num={1} label="Projet">
            <svg width="90" height="52" viewBox="0 0 90 52"><rect x="6" y="8" width="78" height="8" rx="2" fill="var(--border-default)" /><rect x="6" y="22" width="50" height="8" rx="2" fill="var(--border-default)" /><rect x="6" y="36" width="34" height="10" rx="5" fill="var(--brand-primary)" /></svg>
          </StepCard>
          <StepCard num={2} label="Intentions">
            <svg width="90" height="52" viewBox="0 0 90 52"><rect x="4" y="6" width="26" height="40" rx="4" fill="var(--surface-page)" stroke="var(--border-default)" /><rect x="34" y="6" width="52" height="40" rx="4" fill="var(--surface-page)" stroke="var(--border-default)" /><rect x="8" y="12" width="18" height="6" rx="2" fill="var(--brand-primary)" /><rect x="8" y="22" width="18" height="6" rx="2" fill="var(--border-default)" /><rect x="40" y="14" width="16" height="16" rx="3" fill="var(--success-bg)" stroke="var(--success-border)" /><rect x="58" y="14" width="16" height="16" rx="3" fill="var(--error-bg)" stroke="var(--error-border)" /></svg>
          </StepCard>
          <StepCard num={3} label="Connaissances">
            <svg width="90" height="52" viewBox="0 0 90 52"><rect x="8" y="8" width="16" height="20" rx="2" fill="var(--surface-page)" stroke="var(--border-default)" /><rect x="28" y="8" width="16" height="20" rx="2" fill="var(--surface-page)" stroke="var(--border-default)" /><rect x="48" y="8" width="16" height="20" rx="2" fill="var(--surface-page)" stroke="var(--border-default)" /><rect x="8" y="34" width="56" height="6" rx="3" fill="var(--warning-500)" opacity="0.6" /></svg>
          </StepCard>
          <StepCard num={4} label="Parcours">
            <svg width="90" height="52" viewBox="0 0 90 52"><rect x="4" y="22" width="26" height="10" rx="5" fill="var(--success-bg)" /><rect x="34" y="22" width="26" height="10" rx="5" fill="var(--warning-bg)" /><rect x="64" y="22" width="22" height="10" rx="5" fill="var(--error-bg)" /></svg>
          </StepCard>
          <StepCard num={5} label="Messages">
            <svg width="90" height="52" viewBox="0 0 90 52"><rect x="6" y="8" width="48" height="16" rx="8" fill="var(--surface-sunken)" stroke="var(--border-default)" /><rect x="30" y="28" width="48" height="16" rx="8" fill="var(--brand-primary)" /></svg>
          </StepCard>
          <StepCard num={6} label="Publication">
            <svg width="90" height="52" viewBox="0 0 90 52"><rect x="6" y="6" width="78" height="40" rx="4" fill="var(--surface-page)" stroke="var(--border-default)" /><path d="M20 26 L34 36 L64 14" stroke="var(--brand-primary)" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </StepCard>
        </div>
      </div>

      {/* Démo widget */}
      <div id="demo" style={{ padding: "80px 40px", background: "var(--surface-card)", borderTop: "1px solid var(--border-subtle)", borderBottom: "1px solid var(--border-subtle)" }}>
        <div style={{ maxWidth: 640, margin: "0 auto", textAlign: "center", marginBottom: 36 }}>
          <div style={{ fontSize: 28, fontWeight: 600, letterSpacing: "var(--tracking-tight)", marginBottom: 12 }}>Essayez-le</div>
          <div style={{ fontSize: "14.5px", color: "var(--text-secondary)" }}>Ceci est le produit, pas une vidéo — un vrai bot de démonstration.</div>
        </div>
        <DemoWidget />
      </div>

      {/* Confiance */}
      <div style={{ padding: "80px 40px", maxWidth: 1180, margin: "0 auto" }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 20 }}>
          <TrustCard
            title="Déterminisme"
            text="Vos messages, jamais improvisés. Chaque réponse provient d'un template que vous avez écrit — le parcours est une machine à états auditable, pas une conversation libre avec un modèle."
          />
          <TrustCard
            title="Confidentialité"
            text="Vos documents restent cloisonnés par intention et par niveau de confidentialité. Rien n'est mélangé, rien ne fuite entre projets."
            icon={<svg width="16" height="16" viewBox="0 0 64 64"><circle cx="32" cy="25" r="10" fill="none" stroke="var(--brand-primary)" strokeWidth="4" /><path d="M32 33 L32 44" stroke="var(--brand-primary)" strokeWidth="4" strokeLinecap="round" /></svg>}
          />
          <TrustCard
            title="Souveraineté"
            text="Vos données, hébergées en Europe, purgeables sur demande dans le respect du RGPD. Vous restez propriétaire de tout ce que le bot apprend."
          />
        </div>
      </div>

      {/* Pricing */}
      <div id="tarifs" style={{ padding: "80px 40px", background: "var(--surface-card)", borderTop: "1px solid var(--border-subtle)", borderBottom: "1px solid var(--border-subtle)" }}>
        <div style={{ maxWidth: 460, margin: "0 auto", textAlign: "center" }}>
          <div style={{ fontSize: 28, fontWeight: 600, letterSpacing: "var(--tracking-tight)", marginBottom: 10 }}>Plan pilote</div>
          <div style={{ fontSize: 14, color: "var(--text-secondary)", marginBottom: 32 }}>Pour tester LOKO en conditions réelles sur un premier périmètre.</div>
          <div style={{ background: "var(--surface-page)", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-lg)", padding: 32, textAlign: "left" }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginBottom: 20 }}>
              <div style={{ fontSize: 34, fontWeight: 600, fontFamily: "var(--font-mono)" }}>0 €</div>
              <div style={{ fontSize: 13, color: "var(--text-tertiary)" }}>pendant 90 jours</div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 11, marginBottom: 26 }}>
              {[
                { label: "Bots", value: "1" },
                { label: "Sessions / mois", value: "1 000" },
                { label: "Entraînements / mois", value: "50" },
                { label: "Documents source", value: "100" },
              ].map((row) => (
                <div key={row.label} style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                  <span style={{ color: "var(--text-secondary)" }}>{row.label}</span>
                  <span style={{ fontFamily: "var(--font-mono)", fontWeight: 600 }}>{row.value}</span>
                </div>
              ))}
            </div>
            <Link to="/signup" style={{ display: "block", width: "100%", boxSizing: "border-box", padding: 12, borderRadius: "var(--radius-md)", border: "none", background: "var(--brand-primary)", color: "var(--text-on-brand)", fontSize: 14, fontWeight: 600, textAlign: "center", textDecoration: "none" }}>Démarrer le pilote</Link>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div style={{ padding: "32px 40px", maxWidth: 1180, margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>© 2026 LOKO. Tous droits réservés.</div>
        <div style={{ display: "flex", gap: 22, fontSize: 12, color: "var(--text-tertiary)" }}>
          <Link to="/cgu" style={{ color: "inherit", textDecoration: "none" }}>CGU</Link>
          <Link to="/confidentialite" style={{ color: "inherit", textDecoration: "none" }}>Confidentialite</Link>
          <Link to="/mentions" style={{ color: "inherit", textDecoration: "none" }}>Mentions legales</Link>
          <Link to="/contact" style={{ color: "inherit", textDecoration: "none" }}>Contact</Link>
        </div>
      </div>
    </div>
  );
}
