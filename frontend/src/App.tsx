import { Routes, Route } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { DashboardPage } from "./pages/DashboardPage";
import { ProjectPage } from "./pages/ProjectPage";
import { ApprovalsPage } from "./pages/ApprovalsPage";
import { ApprovalDetailPage } from "./pages/ApprovalDetailPage";
import { FindingsPage } from "./pages/FindingsPage";
import { PromotionPage } from "./pages/PromotionPage";
import { SettingsPage } from "./pages/SettingsPage";
import { ReportsPage } from "./pages/ReportsPage";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/projects/:projectId" element={<ProjectPage />} />
        <Route path="/approvals" element={<ApprovalsPage />} />
        <Route path="/approvals/:approvalId" element={<ApprovalDetailPage />} />
        <Route path="/projects/:projectId/findings" element={<FindingsPage />} />
        <Route path="/projects/:projectId/promotions" element={<PromotionPage />} />
        <Route path="/projects/:projectId/reports" element={<ReportsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </AppShell>
  );
}
