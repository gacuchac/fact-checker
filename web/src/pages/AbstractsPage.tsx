import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { searchDocs } from "../api";
import { LoadError } from "../components/LoadError";
import type { DocSummary } from "../types";

export function AbstractsPage(): JSX.Element {
  const [query, setQuery] = useState("");
  const [docs, setDocs] = useState<DocSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function runSearch(): Promise<void> {
    setError(null);
    try {
      setDocs(await searchDocs(query.trim()));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function search(event: FormEvent): void {
    event.preventDefault();
    void runSearch();
  }

  return (
    <div>
      <h1>Abstracts</h1>
      <form className="search" onSubmit={search}>
        <input data-testid="doc-search" type="search" value={query} placeholder="Search papers" onChange={(e) => setQuery(e.target.value)} />
        <button type="submit">Search</button>
      </form>
      {error !== null && <LoadError message={error} retry={() => void runSearch()} />}
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
