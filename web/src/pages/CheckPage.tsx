import { useEffect, useState } from "react";
import { confirmClaim, confirmIssues, createClaim, getClaim, verifyClaim } from "../api";
import { ResultView } from "../components/ResultView";
import { StatementsTable } from "../components/StatementsTable";
import { type AddedRow, buildEdits, type Row, rowsFrom } from "../edits";
import type { CheckResult, ConfirmIssue } from "../types";

type Phase =
  | { name: "entry" }
  | { name: "review"; runId: string }
  | { name: "working"; runId: string; status: string }
  | { name: "done"; runId: string; result: CheckResult }
  | { name: "failed"; runId: string; error: string };

interface Props {
  pollMs?: number;
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function Progress({ status }: { status: string }): JSX.Element {
  const label = status === "reviewing" ? "Reviewing…" : "Verifying…";
  return (
    <p className="progress" data-testid="progress" role="status">
      <span className="spinner" /> {label}
    </p>
  );
}

export function CheckPage({ pollMs = 2000 }: Props): JSX.Element {
  const [claim, setClaim] = useState("");
  const [phase, setPhase] = useState<Phase>({ name: "entry" });
  const [rows, setRows] = useState<Row[]>([]);
  const [added, setAdded] = useState<AddedRow[]>([]);
  const [issues, setIssues] = useState<ConfirmIssue[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const polling = phase.name === "working" ? phase.runId : null;
  useEffect(() => {
    if (polling === null) return;
    let live = true;
    const timer = setInterval(() => {
      getClaim(polling).then(
        (run) => {
          if (!live) return;
          if (run.status === "done" && run.result !== null) setPhase({ name: "done", runId: polling, result: run.result });
          else if (run.status === "failed") setPhase({ name: "failed", runId: polling, error: run.error ?? "The check failed." });
          else setPhase({ name: "working", runId: polling, status: run.status });
        },
        (e: unknown) => live && setPhase({ name: "failed", runId: polling, error: messageOf(e) }),
      );
    }, pollMs);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [polling, pollMs]);

  async function breakDown(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      const proposed = await createClaim(claim.trim());
      setRows(rowsFrom(proposed.proposed));
      setAdded([]);
      setIssues([]);
      setPhase({ name: "review", runId: proposed.run_id });
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(false);
    }
  }

  async function approve(runId: string): Promise<void> {
    setBusy(true);
    setError(null);
    setIssues([]);
    try {
      await confirmClaim(runId, buildEdits(rows, added));
      await verifyClaim(runId);
      setPhase({ name: "working", runId, status: "verifying" });
    } catch (e) {
      const found = confirmIssues(e);
      if (found === null) setError(messageOf(e));
      else setIssues(found);
    } finally {
      setBusy(false);
    }
  }

  function reset(): void {
    setPhase({ name: "entry" });
    setClaim("");
    setError(null);
  }

  return (
    <div className="check">
      <h1>Check a claim</h1>
      <textarea
        data-testid="claim-input"
        value={claim}
        maxLength={500}
        rows={3}
        disabled={phase.name !== "entry"}
        placeholder="Type a claim to fact-check"
        onChange={(e) => setClaim(e.target.value)}
      />
      {phase.name === "entry" && (
        <button type="button" data-testid="decompose-button" disabled={busy || claim.trim() === ""} onClick={() => void breakDown()}>
          Break down
        </button>
      )}
      {error !== null && <p className="issue">{error}</p>}
      {phase.name === "review" && (
        <>
          <h2>Statements</h2>
          <StatementsTable rows={rows} added={added} issues={issues} onRows={setRows} onAdded={setAdded} />
          <button type="button" data-testid="approve-button" disabled={busy} onClick={() => void approve(phase.runId)}>
            Approve &amp; verify
          </button>
        </>
      )}
      {phase.name === "working" && <Progress status={phase.status} />}
      {phase.name === "failed" && <p className="issue">The check failed: {phase.error}</p>}
      {phase.name === "done" && <ResultView runId={phase.runId} result={phase.result} />}
      {(phase.name === "done" || phase.name === "failed") && (
        <button type="button" onClick={reset}>
          New claim
        </button>
      )}
    </div>
  );
}
