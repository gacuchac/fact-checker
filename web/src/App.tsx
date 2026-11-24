import { NavLink, Route, Routes } from "react-router-dom";
import { AccessCodeGate } from "./components/AccessCodeGate";
import { AbstractsPage } from "./pages/AbstractsPage";
import { CheckPage } from "./pages/CheckPage";
import { DocPage } from "./pages/DocPage";
import { TracePage } from "./pages/TracePage";
import { TracesPage } from "./pages/TracesPage";

export function App(): JSX.Element {
  return (
    <AccessCodeGate>
      <nav className="nav">
        <NavLink to="/" end>Check</NavLink>
        <NavLink to="/traces">Traces</NavLink>
        <NavLink to="/abstracts">Abstracts</NavLink>
      </nav>
      <main>
        <Routes>
          <Route path="/" element={<CheckPage />} />
          <Route path="/traces" element={<TracesPage />} />
          <Route path="/traces/:runId" element={<TracePage />} />
          <Route path="/abstracts" element={<AbstractsPage />} />
          <Route path="/abstracts/:docId" element={<DocPage />} />
        </Routes>
      </main>
    </AccessCodeGate>
  );
}
