import { vi } from "vitest";
import type { CheckResult, FinalAnswer, FinalStatement, JudgeScores, Statement } from "../src/types";

export type Handler = (url: string, init: RequestInit) => { status?: number; body: unknown } | undefined;

export interface FetchCall {
  url: string;
  method: string;
  headers: Headers;
  body: unknown;
}

/** Replace global fetch with a mock that answers through handler and records every call. */
export function mockFetch(handler: Handler): FetchCall[] {
  const calls: FetchCall[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const raw = typeof init.body === "string" ? (JSON.parse(init.body) as unknown) : undefined;
      calls.push({ url, method: init.method ?? "GET", headers: new Headers(init.headers), body: raw });
      const answer = handler(url, init) ?? { status: 404, body: { detail: "not found" } };
      const status = answer.status ?? 200;
      return new Response(JSON.stringify(answer.body), { status });
    }),
  );
  return calls;
}

export function statement(id: number, text: string, overrides: Partial<Statement> = {}): Statement {
  return {
    id,
    text,
    load_bearing: true,
    implied_by: text.slice(0, 10),
    query: "q",
    kind: "explicit",
    mark: "confirmed",
    ...overrides,
  };
}

export function scores(overrides: Partial<JudgeScores> = {}): JudgeScores {
  const dim = { score: 4, evidence: "looks fine" };
  return {
    schema_version: 1,
    model: "sol",
    seconds: 2.5,
    dimensions: {
      evidence_relevance: dim,
      statement_verdicts: dim,
      overreach: dim,
      conflict_handling: dim,
      aggregation: dim,
      unknown_calibration: dim,
    },
    flagged: [],
    needs_attention: false,
    ...overrides,
  };
}

export function finalStatement(id: number, overrides: Partial<FinalStatement> = {}): FinalStatement {
  return {
    id,
    text: `Statement ${id}`,
    load_bearing: true,
    mark: "confirmed",
    model_verdict: "supported",
    verdict: "supported",
    downgrade_reason: null,
    evidence: [
      {
        doc_id: "2307.03172v3",
        title: "Lost in the Middle",
        authors: ["Nelson Liu", "Kevin Lin"],
        published: "2023-07-06",
        quote: "models struggle to use long contexts well",
        stance: "supports",
      },
    ],
    dropped_quotes: [{ passage_id: "p9", quote: "a quote that failed verification here", stance: "supports" }],
    ...overrides,
  };
}

export function answer(verdict: "supported" | "contradicted" | "unknown" = "supported"): FinalAnswer {
  return {
    schema_version: 1,
    claim: "claim",
    overall: { verdict, rule: 2 },
    statements: [finalStatement(1)],
    counts: { confirmed: 1, user_edited: 0, user_added: 0, dropped: 0 },
  };
}

export function checkResult(overrides: Partial<CheckResult> = {}): CheckResult {
  return {
    verdicts: {},
    final: answer(),
    scores: scores(),
    review_error: null,
    events: [],
    first_final: answer(),
    first_scores: null,
    revised: false,
    final_message: "FINAL MESSAGE TEXT",
    ...overrides,
  };
}
