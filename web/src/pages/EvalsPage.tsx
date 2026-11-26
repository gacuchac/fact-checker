import { useState } from "react";
import { Link } from "react-router-dom";
import { listEvals } from "../api";
import { Badge } from "../components/Badge";
import { LoadError } from "../components/LoadError";
import { useLoad } from "../hooks";
import type { EvalCase } from "../types";

type Filter = "all" | "statements" | "claim";

const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "statements", label: "Fact-check" },
  { value: "claim", label: "Security" },
];

/** The note for a case that does more than run its claim, or null when it only runs the claim. */
function noteText(evalCase: EvalCase): string | null {
  const parts = [
    evalCase.has_edits ? "This case also changes the proposed statements." : null,
    evalCase.has_planted_docs ? "This case plants test abstracts." : null,
  ].filter((part): part is string => part !== null);
  return parts.length === 0 ? null : [...parts, "Check this claim runs the claim alone."].join(" ");
}

function DocRow({ label, ids, testId }: { label: string; ids: string[]; testId: string }): JSX.Element | null {
  if (ids.length === 0) return null;
  return (
    <div className="eval-row">
      <span className="muted">{label}</span>
      {ids.map((id) => (
        <Link key={id} to={`/abstracts/${encodeURIComponent(id)}`} data-testid={testId}>
          {id}
        </Link>
      ))}
    </div>
  );
}

function EvalCard({ evalCase }: { evalCase: EvalCase }): JSX.Element {
  const note = noteText(evalCase);
  return (
    <li className="card" data-testid="eval-card">
      <header className="eval-head">
        <h3>{evalCase.id}</h3>
        <span className="tag" data-testid="eval-mode">{evalCase.mode}</span>
        {evalCase.owasp.map((id) => (
          <span key={id} className="tag" data-testid="eval-owasp">{id}</span>
        ))}
      </header>
      {evalCase.claim !== null && <p>{evalCase.claim}</p>}
      {evalCase.expected.length > 0 && (
        <div className="eval-row">
          <span className="muted">Expected</span>
          {evalCase.expected.map((verdict) => (
            <Badge key={verdict} kind={verdict} testId="eval-expected" />
          ))}
        </div>
      )}
      <DocRow label="Must cite" ids={evalCase.must_cite_docs} testId="eval-cite-doc" />
      <DocRow label="Must be found by search" ids={evalCase.must_find_docs} testId="eval-find-doc" />
      {evalCase.mode === "statements" && evalCase.statements.length > 0 && (
        <ul>
          {evalCase.statements.map((statement) => (
            <li key={statement.text} data-testid="eval-statement">
              {statement.text} <Badge kind={statement.gold_verdict} />
            </li>
          ))}
        </ul>
      )}
      {evalCase.mode === "claim" && evalCase.checks.length > 0 && (
        <ul>
          {evalCase.checks.map((check) => (
            <li key={check} data-testid="eval-security-check">{check}</li>
          ))}
        </ul>
      )}
      {note !== null && <p className="callout info" data-testid="eval-note">{note}</p>}
      {evalCase.claim !== null && (
        <Link className="button-link" data-testid="eval-try" to={`/?claim=${encodeURIComponent(evalCase.claim)}`}>
          Check this claim
        </Link>
      )}
      {evalCase.error !== null && <p className="issue" data-testid="eval-error">{evalCase.error}</p>}
    </li>
  );
}

/** The Evals tab: every eval case as a card, narrowed by a mode filter. */
export function EvalsPage(): JSX.Element {
  const cases = useLoad(() => listEvals(), "evals");
  const [filter, setFilter] = useState<Filter>("all");
  return (
    <div>
      <h1>Evals</h1>
      {cases.state === "loading" && <p className="muted">Loading…</p>}
      {cases.state === "error" && <LoadError message={cases.message} retry={cases.retry} />}
      {cases.state === "ready" && cases.data.length === 0 && <p className="muted">No eval cases yet.</p>}
      {cases.state === "ready" && cases.data.length > 0 && (
        <>
          <div className="eval-filters">
            {FILTERS.map(({ value, label }) => (
              <button
                key={value}
                type="button"
                className={filter === value ? "primary" : undefined}
                aria-pressed={filter === value}
                data-testid={`eval-filter-${value}`}
                onClick={() => setFilter(value)}
              >
                {label}
              </button>
            ))}
          </div>
          <ul className="evals">
            {cases.data
              .filter((evalCase) => filter === "all" || evalCase.mode === filter)
              .map((evalCase) => (
                <EvalCard key={evalCase.id} evalCase={evalCase} />
              ))}
          </ul>
        </>
      )}
    </div>
  );
}
