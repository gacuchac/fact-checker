import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ResultView } from "../src/components/ResultView";
import { CheckPage } from "../src/pages/CheckPage";
import { TracePage } from "../src/pages/TracePage";
import { TracesPage } from "../src/pages/TracesPage";
import type { Flag, Span } from "../src/types";
import { answer, checkResult, finalStatement, mockFetch, scores, statement } from "./helpers";

const IMG = '<img src=x onerror="window.__xss=1">';
const SCRIPT = "<script>window.__xss=2</script>";
const PAYLOAD = `${IMG} lost in the middle ${SCRIPT}`;

declare global {
  interface Window {
    __xss?: number;
  }
}

afterEach(() => {
  vi.unstubAllGlobals();
  delete window.__xss;
});

function expectInert(container: HTMLElement): void {
  expect(container.querySelector('img[src="x"]')).toBeNull();
  expect([...container.querySelectorAll("script")].filter((s) => s.textContent?.includes("__xss"))).toHaveLength(0);
  expect(window.__xss).toBeUndefined();
  expect(container.textContent).toContain('onerror="window.__xss=1"');
}

it("S07: the claim and proposed statements render payloads as text", async () => {
  mockFetch((url, init) => {
    if (url === "/api/claims" && init.method === "POST") {
      return { status: 201, body: { run_id: "r1", claim: PAYLOAD, proposed: [statement(1, PAYLOAD)] } };
    }
    return undefined;
  });
  const { container } = render(
    <MemoryRouter>
      <CheckPage pollMs={10} />
    </MemoryRouter>,
  );
  await userEvent.type(screen.getByTestId("claim-input"), "claim");
  await userEvent.click(screen.getByTestId("decompose-button"));
  await screen.findAllByTestId("statement-row");
  expectInert(container);
});

it("S07: reasons, quotes, flags and the final message render payloads as text", () => {
  const flag: Flag = { statement_id: 1, dimension: "overreach", reason: PAYLOAD };
  const final = {
    ...answer("unknown"),
    claim: PAYLOAD,
    statements: [
      finalStatement(1, {
        text: PAYLOAD,
        evidence: [{ ...finalStatement(1).evidence[0]!, quote: PAYLOAD, title: PAYLOAD }],
        dropped_quotes: [{ passage_id: "p1", quote: PAYLOAD, stance: "supports" }],
      }),
    ],
  };
  const result = checkResult({
    final,
    scores: scores({ flagged: [flag], needs_attention: true }),
    consistency_flags: [flag],
    final_message: PAYLOAD,
  });
  const { container } = render(
    <MemoryRouter>
      <ResultView runId="r1" result={result} />
    </MemoryRouter>,
  );
  expectInert(container);
});

function span(seq: number, overrides: Partial<Span>): Span {
  return {
    id: `s${seq}`,
    run_id: "r1",
    parent_id: null,
    seq,
    kind: "llm",
    name: `step-${seq}`,
    started_at: "2026-11-24T10:00:00+00:00",
    ended_at: "2026-11-24T10:00:01+00:00",
    status: "error",
    model: "m",
    input: { system: PAYLOAD, user: PAYLOAD },
    output: { text: PAYLOAD },
    usage: null,
    error: PAYLOAD,
    ...overrides,
  };
}

it("S07: span input, output and error render payloads as text with every span open", async () => {
  mockFetch(() => ({ body: { run_id: "r1", spans: [span(1, {}), span(2, { kind: "user", name: "claim" })] } }));
  const { container } = render(
    <MemoryRouter initialEntries={["/traces/r1"]}>
      <Routes>
        <Route path="/traces/:runId" element={<TracePage />} />
      </Routes>
    </MemoryRouter>,
  );
  const toggles = await screen.findAllByTestId("span-toggle");
  for (const toggle of toggles) await userEvent.click(toggle);
  expectInert(container);
});

it("S07: the runs list renders a payload claim and error as text", async () => {
  mockFetch(() => ({
    body: [{ id: "r1", claim: PAYLOAD, status: "failed", created_at: "2026-11-24", updated_at: "x", error: PAYLOAD }],
  }));
  const { container } = render(
    <MemoryRouter>
      <TracesPage />
    </MemoryRouter>,
  );
  await screen.findByTestId("run-row");
  expectInert(container);
});
