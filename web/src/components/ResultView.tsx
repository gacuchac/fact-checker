import { useState } from "react";
import { Link } from "react-router-dom";
import type { CheckResult, FinalAnswer, FinalEvidence, FinalStatement, JudgeScores } from "../types";
import { Badge } from "./Badge";

function EvidenceQuote({ item }: { item: FinalEvidence }): JSX.Element {
  return (
    <blockquote className={`quote quote-${item.stance}`} data-testid="evidence-quote">
      <p>“{item.quote}”</p>
      <footer>
        <span className="stance">{item.stance}</span> · <strong>{item.title}</strong> ·{" "}
        <a href={`https://arxiv.org/abs/${item.doc_id}`} target="_blank" rel="noreferrer">
          arXiv:{item.doc_id}
        </a>{" "}
        · {item.authors.join(", ")} · {item.published}
      </footer>
    </blockquote>
  );
}

function StatementResult({ statement }: { statement: FinalStatement }): JSX.Element {
  return (
    <section className="card statement-result">
      <header>
        <Badge kind={statement.verdict} testId="statement-verdict" />
        <span className="statement-text">{statement.text}</span>
        {statement.load_bearing && <span className="tag">load-bearing</span>}
      </header>
      {statement.downgrade_reason !== null && (
        <p className="muted">
          Model said {statement.model_verdict}; downgraded ({statement.downgrade_reason}).
        </p>
      )}
      {statement.evidence.map((item, i) => (
        <EvidenceQuote key={i} item={item} />
      ))}
      {statement.dropped_quotes.length > 0 && (
        <details>
          <summary>{statement.dropped_quotes.length} dropped quote(s)</summary>
          {statement.dropped_quotes.map((quote, i) => (
            <blockquote key={i} className="quote dropped-quote">
              <p>{quote.quote}</p>
              <footer>
                {quote.stance} · {quote.passage_id}
              </footer>
            </blockquote>
          ))}
        </details>
      )}
    </section>
  );
}

function ReviewPanel({ scores }: { scores: JudgeScores }): JSX.Element {
  return (
    <section className="card" data-testid="review-panel">
      <h3>Review</h3>
      {scores.needs_attention && (
        <div className="callout" data-testid="needs-attention">
          Needs attention: the reviewer flagged problems with this answer.
        </div>
      )}
      <table className="scores">
        <tbody>
          {Object.entries(scores.dimensions).map(([name, dim]) => (
            <tr key={name}>
              <th>{name.replaceAll("_", " ")}</th>
              <td className="score">{dim.score}/5</td>
              <td>{dim.evidence}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {scores.flagged.length > 0 && (
        <ul>
          {scores.flagged.map((flag, i) => (
            <li key={i}>
              Statement {flag.statement_id} · {flag.dimension.replaceAll("_", " ")}: {flag.reason}
            </li>
          ))}
        </ul>
      )}
      <p className="muted">
        {scores.model} · {scores.seconds.toFixed(1)}s
      </p>
    </section>
  );
}

function Answer({ answer, scores }: { answer: FinalAnswer; scores: JudgeScores | null }): JSX.Element {
  return (
    <>
      <p>
        <Badge kind={answer.overall.verdict} testId="result-overall" /> <span className="muted">rule {answer.overall.rule}</span>
      </p>
      {answer.statements.map((statement) => (
        <StatementResult key={statement.id} statement={statement} />
      ))}
      {scores !== null && <ReviewPanel scores={scores} />}
    </>
  );
}

interface Props {
  runId: string;
  result: CheckResult;
}

export function ResultView({ runId, result }: Props): JSX.Element {
  const [showFirst, setShowFirst] = useState(false);
  return (
    <div className="result">
      <h2>Result</h2>
      {result.revised && (
        <div className="callout info" data-testid="revised-banner">
          Revised after review.{" "}
          <button type="button" className="link" data-testid="first-answer-toggle" onClick={() => setShowFirst(!showFirst)}>
            {showFirst ? "Hide first answer" : "Show first answer"}
          </button>
        </div>
      )}
      {result.revised && showFirst && (
        <div className="first-answer" data-testid="first-answer">
          <h3>First answer</h3>
          <Answer answer={result.first_final} scores={result.first_scores} />
        </div>
      )}
      <Answer answer={result.final} scores={result.scores} />
      {result.review_error !== null && <p className="issue">Review failed: {result.review_error}</p>}
      <h3>Final message</h3>
      <pre data-testid="final-message" className="final-message">
        {result.final_message}
      </pre>
      <Link to={`/traces/${runId}`} data-testid="view-trace">
        View trace
      </Link>
    </div>
  );
}
