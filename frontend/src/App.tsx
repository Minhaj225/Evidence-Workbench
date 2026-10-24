import { Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell";
import DocumentsPage from "./pages/DocumentsPage";
import AskPage from "./pages/AskPage";
import EvaluationPage from "./pages/EvaluationPage";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Navigate to="/documents" replace />} />
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/ask" element={<AskPage />} />
        <Route path="/evaluation" element={<EvaluationPage />} />
        <Route
          path="*"
          element={
            <p>
              Page not found. Use the navigation to return to your documents.
            </p>
          }
        />
      </Routes>
    </AppShell>
  );
}
