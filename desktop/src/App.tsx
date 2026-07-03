import { Navigate, Route, Routes } from "react-router-dom";
import { Sidebar } from "@/components/layout/Sidebar";
import { BotList } from "@/pages/bot/BotList";
import { BotWizard } from "@/pages/bot/BotWizard";
import { BotPlayground } from "@/pages/bot/BotPlayground";
import { BotDashboard } from "@/pages/bot/BotDashboard";

export default function App() {
  return (
    <div className="flex h-screen bg-gray-50 dark:bg-gray-950 text-gray-700 dark:text-gray-200">
      <Sidebar />
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
