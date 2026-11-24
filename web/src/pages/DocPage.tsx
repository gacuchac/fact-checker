import { Link, useParams } from "react-router-dom";
import { getDoc } from "../api";
import { LoadError } from "../components/LoadError";
import { useLoad } from "../hooks";

export function DocPage(): JSX.Element {
  const { docId = "" } = useParams();
  const doc = useLoad(() => getDoc(docId), docId);
  return (
    <div>
      <p><Link to="/abstracts">← Search</Link></p>
      {doc.state === "loading" && <p className="muted">Loading…</p>}
      {doc.state === "error" && <LoadError message={doc.message} retry={doc.retry} />}
      {doc.state === "ready" && (
        <article>
          <h1>{doc.data.title}</h1>
          <p className="muted">
            {doc.data.authors.join(", ")} · {doc.data.published} ·{" "}
            <a href={`https://arxiv.org/abs/${doc.data.doc_id}`} target="_blank" rel="noreferrer">
              arXiv:{doc.data.doc_id}
            </a>
          </p>
          <p data-testid="doc-abstract" className="abstract">
            {doc.data.abstract}
          </p>
        </article>
      )}
    </div>
  );
}
