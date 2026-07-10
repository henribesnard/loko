import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Sidebar } from "@/components/layout/Sidebar";
import { BotList } from "@/pages/bot/BotList";
import { BotWizard } from "@/pages/bot/BotWizard";
import { BotPlayground } from "@/pages/bot/BotPlayground";
import { BotDashboard } from "@/pages/bot/BotDashboard";
import { LoginPage } from "@/pages/LoginPage";
import { SignupPage } from "@/pages/auth/SignupPage";
import { ResetPasswordPage } from "@/pages/auth/ResetPasswordPage";
import { LandingPage } from "@/pages/public/LandingPage";
import { LegalPage } from "@/pages/public/LegalPage";
import { useAuth } from "@/hooks/useAuth";

/** F3: redirect to /login?next={current_path} for protected routes. */
function RequireAuth() {
  const location = useLocation();
  const path = location.pathname;
  // Public paths don't need redirect — just go to landing
  if (path === "/" || path === "/login" || path === "/signup" || path === "/reset"
      || path === "/cgu" || path === "/confidentialite" || path === "/mentions" || path === "/contact") {
    return <Navigate to="/" replace />;
  }
  return <Navigate to={`/login?next=${encodeURIComponent(path)}`} replace />;
}

export default function App() {
  const { authenticated, loading, login, logout } = useAuth();

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-surface-page">
        <p className="text-sm text-loko-tertiary">Chargement…</p>
      </div>
    );
  }

  // Public routes (accessible without auth)
  if (!authenticated) {
    return (
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage onLogin={login} />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route path="/reset" element={<ResetPasswordPage />} />
        <Route path="/cgu" element={<LegalPage page="cgu" />} />
        <Route path="/confidentialite" element={<LegalPage page="confidentialite" />} />
        <Route path="/mentions" element={<LegalPage page="mentions" />} />
        <Route path="/contact" element={<LegalPage page="contact" />} />
        <Route path="*" element={<RequireAuth />} />
      </Routes>
    );
  }

  // Authenticated routes
  return (
    <div className="flex h-screen bg-surface-page text-loko-primary">
      <Sidebar onLogout={logout} />
      <main className="flex-1 overflow-hidden">
        <Routes>
          <Route path="/bot" element={<BotList />} />
          <Route path="/bot/:id/wizard" element={<BotWizard />} />
          <Route path="/bot/:id/wizard/:step" element={<BotWizard />} />
          <Route path="/bot/:id/playground" element={<BotPlayground />} />
          <Route path="/bot/:id/dashboard" element={<BotDashboard />} />
          <Route path="*" element={<Navigate to="/bot" replace />} />
        </Routes>
      </main>
    </div>
  );
}
