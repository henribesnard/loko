import { Navigate, Route, Routes } from "react-router-dom";
import { Sidebar } from "@/components/layout/Sidebar";
import { BotList } from "@/pages/bot/BotList";
import { BotWizard } from "@/pages/bot/BotWizard";
import { BotPlayground } from "@/pages/bot/BotPlayground";
import { BotDashboard } from "@/pages/bot/BotDashboard";
import { LoginPage } from "@/pages/LoginPage";
import { SignupPage } from "@/pages/auth/SignupPage";
import { ResetPasswordPage } from "@/pages/auth/ResetPasswordPage";
import { LandingPage } from "@/pages/public/LandingPage";
import { useAuth } from "@/hooks/useAuth";

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
        <Route path="*" element={<Navigate to="/" replace />} />
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
