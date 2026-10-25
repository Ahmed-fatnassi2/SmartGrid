import { Compass } from "lucide-react";
import { lazy } from "react";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import { Layout } from "./components/layout/Layout";
import { EmptyState } from "./components/ui/States";
import { BackendProvider } from "./context/BackendContext";
import { ToastProvider } from "./context/ToastContext";

// Each page is its own chunk (React Flow and Recharts load only where used).
const BuildingsPage = lazy(() => import("./pages/BuildingsPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const EnergySourcesPage = lazy(() => import("./pages/EnergySourcesPage"));
const GridExplorerPage = lazy(() => import("./pages/GridExplorerPage"));
const NlpAssistantPage = lazy(() => import("./pages/NlpAssistantPage"));
const OntologyExplorerPage = lazy(() => import("./pages/OntologyExplorerPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const SparqlConsolePage = lazy(() => import("./pages/SparqlConsolePage"));
const StoragePage = lazy(() => import("./pages/StoragePage"));
const TransmissionLinesPage = lazy(() => import("./pages/TransmissionLinesPage"));

function NotFound() {
  return (
    <div className="page">
      <EmptyState
        icon={<Compass size={22} />}
        title="Page introuvable"
        message="Cette adresse ne correspond à aucune page."
        action={
          <Link className="btn btn-primary btn-md" to="/">
            Retour au tableau de bord
          </Link>
        }
      />
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <BackendProvider>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<DashboardPage />} />
              <Route path="sources" element={<EnergySourcesPage />} />
              <Route path="storage" element={<StoragePage />} />
              <Route path="buildings" element={<BuildingsPage />} />
              <Route path="lines" element={<TransmissionLinesPage />} />
              <Route path="grid" element={<GridExplorerPage />} />
              <Route path="ontology" element={<OntologyExplorerPage />} />
              <Route path="sparql" element={<SparqlConsolePage />} />
              <Route path="assistant" element={<NlpAssistantPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="*" element={<NotFound />} />
            </Route>
          </Routes>
        </BackendProvider>
      </ToastProvider>
    </BrowserRouter>
  );
}
