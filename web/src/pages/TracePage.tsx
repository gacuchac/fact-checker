import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getTrace } from "../api";
import { Badge } from "../components/Badge";
import { useLoad } from "../hooks";
import { durationMs, formatDuration, formatTokens, llmPrompt } from "../spans";
import type { Span } from "../types";

function Json({ label, value }: { label: string; value: unknown }): JSX.Element {
  return (
    <section>
      <h4>{label}</h4>
      <pre className="json">{JSON.stringify(value, null, 2) ?? "null"}</pre>
    </section>
  );
}

function SpanDetail({ span }: { span: Span }): JSX.Element {
  const prompt = span.kind === "llm" ? llmPrompt(span.input) : null;
  return (
    <div className="span-detail">
      {prompt !== null && (
        <>
          <section>
            <h4>System prompt</h4>
            <pre className="text">{prompt.system}</pre>
          </section>
          <section>
            <h4>User message</h4>
            <pre className="text">{prompt.user}</pre>
          </section>
        </>
      )}
      <Json label="Input" value={span.input} />
      <Json label="Output" value={span.output} />
      {span.error !== null && <p className="issue">{span.error}</p>}
    </div>
  );
}

function SpanRow({ span }: { span: Span }): JSX.Element {
  const [open, setOpen] = useState(false);
  const tokens = formatTokens(span.usage);
  return (
    <li className="span-row" data-testid="span-row">
      <div className="span-head">
        <span className="seq">{span.seq}</span>
        <Badge kind={span.kind} />
        <strong>{span.name}</strong>
        {span.model !== null && <span className="muted">{span.model}</span>}
        <span className="muted">{formatDuration(durationMs(span))}</span>
        {tokens !== "" && <span className="muted">{tokens}</span>}
        {span.status !== "ok" && <span className="tag">{span.status}</span>}
        <button type="button" data-testid="span-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? "Collapse" : "Expand"}
        </button>
      </div>
      {open && <SpanDetail span={span} />}
    </li>
  );
}

export function TracePage(): JSX.Element {
  const { runId = "" } = useParams();
  const trace = useLoad(() => getTrace(runId), runId);
  return (
    <div>
      <p><Link to="/traces">← All runs</Link></p>
      <h1>Trace {runId}</h1>
      {trace.state === "loading" && <p className="muted">Loading…</p>}
      {trace.state === "error" && <p className="issue">{trace.message}</p>}
      {trace.state === "ready" && (
        <ol className="timeline">
          {trace.data.spans.map((span) => (
            <SpanRow key={span.id} span={span} />
          ))}
        </ol>
      )}
    </div>
  );
}
