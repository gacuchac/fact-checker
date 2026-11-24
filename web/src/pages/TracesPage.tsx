import { Link } from "react-router-dom";
import { listRuns } from "../api";
import { LoadError } from "../components/LoadError";
import { useLoad } from "../hooks";

export function TracesPage(): JSX.Element {
  const runs = useLoad(() => listRuns(), "runs");
  return (
    <div>
      <h1>Traces</h1>
      {runs.state === "loading" && <p className="muted">Loading…</p>}
      {runs.state === "error" && <LoadError message={runs.message} retry={runs.retry} />}
      {runs.state === "ready" && runs.data.length === 0 && <p className="muted">No runs yet.</p>}
      {runs.state === "ready" && runs.data.length > 0 && (
        <table className="list">
          <thead>
            <tr><th>Claim</th><th>Status</th><th>Created</th></tr>
          </thead>
          <tbody>
            {runs.data.map((run) => (
              <tr key={run.id} data-testid="run-row">
                <td><Link to={`/traces/${run.id}`}>{run.claim}</Link></td>
                <td>{run.status}</td>
                <td>{run.created_at}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
