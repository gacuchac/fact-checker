import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { searchDocs } from "../api";
import type { DocSummary } from "../types";

export function AbstractsPage(): JSX.Element {
  const [query, setQuery] = useState("");
  const [docs, setDocs] = useState<DocSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function search(event: FormEvent): Promise<void> {
    event.preventDefault();
    setError(null);
    try {
      setDocs(await searchDocs(query.trim()));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div>
      <h1>Abstracts</h1>
      <form className="search" onSubmit={(e) => void search(e)}>
        <input data-testid="doc-search" type="search" value={query} placeholder="Search papers" onChange={(e) => setQuery(e.target.value)} />
        <button type="submit">Search</button>
      </form>
      {error !== null && <p className="issue">{error}</p>}
      {docs !== null && docs.length === 0 && <p className="muted">No papers found.</p>}
      {docs !== null && docs.length > 0 && (
        <ul className="docs">
          {docs.map((doc) => (
            <li key={doc.doc_id} className="card" data-testid="doc-row">
              <Link to={`/abstracts/${encodeURIComponent(doc.doc_id)}`}>{doc.title}</Link>
              <div className="muted">
                {doc.authors.join(", ")} · {doc.published}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
