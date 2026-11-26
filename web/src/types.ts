export type Verdict = "supported" | "contradicted" | "unknown";
export type Stance = "supports" | "contradicts";
export type StatementKind = "explicit" | "implicit_assumption" | "framing_bias";
export type Mark = "confirmed" | "user_edited" | "user_added";
export type RunStatus = "proposed" | "confirmed" | "verifying" | "done" | "failed";

export interface Statement {
  id: number;
  text: string;
  load_bearing: boolean;
  implied_by: string;
  query: string;
  kind: StatementKind;
  mark: Mark;
}

export type EditOp = "drop" | "edit" | "add" | "flip_load_bearing" | "feedback";

export interface Edit {
  op: EditOp;
  id: number | null;
  value: string | null;
}

export interface ConfirmedStatements {
  schema_version: 1;
  claim: string;
  statements: Statement[];
  proposed: Statement[];
  edits: Edit[];
  rounds: number;
  source: "chat" | "case";
}

export interface Evidence {
  passage_id: string;
  quote: string;
  stance: Stance;
}

export interface FinalEvidence {
  doc_id: string;
  title: string;
  authors: string[];
  published: string;
  quote: string;
  stance: Stance;
}

export interface FinalStatement {
  id: number;
  text: string;
  load_bearing: boolean;
  mark: Mark;
  model_verdict: Verdict;
  verdict: Verdict;
  downgrade_reason: "quote_failed" | "no_hits" | "conflict" | null;
  evidence: FinalEvidence[];
  dropped_quotes: Evidence[];
}

export interface FinalAnswer {
  schema_version: 1;
  claim: string;
  overall: { verdict: Verdict; rule: number };
  statements: FinalStatement[];
  counts: { confirmed: number; user_edited: number; user_added: number; dropped: number };
}

export type Dimension =
  | "evidence_relevance"
  | "statement_verdicts"
  | "overreach"
  | "conflict_handling"
  | "aggregation"
  | "unknown_calibration";

export interface DimensionScore {
  score: number;
  evidence: string;
}

export interface Flag {
  statement_id: number;
  dimension: Dimension;
  reason: string;
}

export interface JudgeScores {
  schema_version: 1;
  model: string;
  seconds: number;
  dimensions: Record<Dimension, DimensionScore>;
  flagged: Flag[];
  needs_attention: boolean;
}

export interface CheckResult {
  verdicts: unknown;
  final: FinalAnswer;
  scores: JudgeScores | null;
  review_error: string | null;
  events: unknown[];
  first_final: FinalAnswer;
  first_scores: JudgeScores | null;
  revised: boolean;
  final_message: string;
  consistency_flags?: Flag[];
}

export interface ProposedClaim {
  run_id: string;
  claim: string;
  proposed: Statement[];
}

export interface ConfirmIssue {
  statement_id: number;
  reason: string;
}

export interface ClaimRun {
  run_id: string;
  claim: string;
  status: RunStatus;
  proposed: Statement[] | null;
  confirmed: ConfirmedStatements | null;
  result: CheckResult | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface RunSummary {
  id: string;
  claim: string;
  status: string;
  created_at: string;
  updated_at: string;
  error: string | null;
}

export type SpanKind = "user" | "llm" | "tool" | "code" | "system";

export interface Span {
  id: string;
  run_id: string;
  parent_id: string | null;
  seq: number;
  kind: SpanKind | string;
  name: string;
  started_at: string;
  ended_at: string;
  status: string;
  model: string | null;
  input: unknown;
  output: unknown;
  usage: unknown;
  error: string | null;
}

export interface Trace {
  run_id: string;
  spans: Span[];
}

export interface DocSummary {
  doc_id: string;
  title: string;
  authors: string[];
  published: string;
}

export interface Doc extends DocSummary {
  base_id: string;
  abstract: string;
}

export interface EvalStatement {
  text: string;
  gold_verdict: string;
  load_bearing: boolean;
}

export interface EvalCase {
  id: string;
  mode: string;
  claim: string | null;
  expected: string[];
  statements: EvalStatement[];
  must_cite_docs: string[];
  must_find_docs: string[];
  expected_docs: string[];
  owasp: string[];
  checks: string[];
  budgets: Record<string, unknown>;
  has_edits: boolean;
  has_planted_docs: boolean;
  error: string | null;
}
