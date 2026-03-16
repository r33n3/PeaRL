import { Routes, Route, Navigate } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { RequireAuth } from "./components/layout/RequireAuth";
import { LoginPage } from "./pages/LoginPage";
import { PipelineDashboardPage } from "./pages/PipelineDashboardPage";
import { ProjectPage } from "./pages/ProjectPage";
import { ApprovalsPage } from "./pages/ApprovalsPage";
import { ApprovalDetailPage } from "./pages/ApprovalDetailPage";
import { FindingsPage } from "./pages/FindingsPage";
import { PromotionPage } from "./pages/PromotionPage";
import { SettingsPage } from "./pages/SettingsPage";
import { ReportsPage } from "./pages/ReportsPage";
import { AdminBusinessUnitsPage } from "./pages/AdminBusinessUnitsPage";
import { AdminProjectsPage } from "./pages/AdminProjectsPage";
import { ExceptionReviewPage } from "./pages/ExceptionReviewPage";
import { PolicyPage } from "./pages/PolicyPage";

export default function App() {
  return (
    <Routes>
      {/* Public */}
      <Route path="/login" element={<LoginPage />} />

      {/* Protected — all other routes require auth */}
      <Route
        path="/*"
        element={
          <RequireAuth>
            <AppShell>
              <Routes>
                <Route path="/" element={<PipelineDashboardPage />} />
                <Route path="/policy" element={<PolicyPage />} />
                <Route path="/projects/:projectId" element={<ProjectPage />} />
                <Route path="/approvals" element={<ApprovalsPage />} />
                <Route path="/approvals/:approvalId" element={<ApprovalDetailPage />} />
                <Route path="/exceptions/:exceptionId" element={<ExceptionReviewPage />} />
                <Route path="/projects/:projectId/findings" element={<FindingsPage />} />
                <Route path="/projects/:projectId/promotions" element={<PromotionPage />} />
                <Route path="/projects/:projectId/reports" element={<ReportsPage />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="/admin/business-units" element={<AdminBusinessUnitsPage />} />
                <Route path="/admin/projects" element={<AdminProjectsPage />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </AppShell>
          </RequireAuth>
        }
      />
    </Routes>
  );
}
