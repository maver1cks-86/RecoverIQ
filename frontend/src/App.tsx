import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./layouts/AppLayout";
import { AuditTrailPage } from "./pages/AuditTrailPage";
import { InterventionsPage } from "./pages/InterventionsPage";
import { OptimizationPage } from "./pages/OptimizationPage";
import { OverviewPage } from "./pages/OverviewPage";
import { RecoveryQueuePage } from "./pages/RecoveryQueuePage";
import { EvaluationPage } from "./pages/EvaluationPage";

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<OverviewPage />} />
        <Route path="recovery-queue" element={<RecoveryQueuePage />} />
        <Route path="optimization" element={<OptimizationPage />} />
        <Route path="evaluation" element={<EvaluationPage />} />
        <Route path="interventions" element={<InterventionsPage />} />
        <Route path="audit-trail" element={<AuditTrailPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
