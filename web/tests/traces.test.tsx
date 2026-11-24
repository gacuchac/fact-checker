import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { TracePage } from "../src/pages/TracePage";
import { TracesPage } from "../src/pages/TracesPage";
import type { Span } from "../src/types";
import { mockFetch } from "./helpers";

afterEach(() => vi.unstubAllGlobals());

function span(seq: number, overrides: Partial<Span>): Span {
  return {
    id: `s${seq}`,
    run_id: "r1",
    parent_id: null,
    seq,
    kind: "code",
    name: `step-${seq}`,
    started_at: "2026-11-24T10:00:00+00:00",
    ended_at: "2026-11-24T10:00:01.500+00:00",
    status: "ok",
    model: null,
    input: { a: 1 },
    output: { b: 2 },
    usage: null,
    error: null,
    ...overrides,
  };
}

it("lists runs", async () => {
  mockFetch(() => ({
    body: [{ id: "r1", claim: "Cats purr", status: "done", created_at: "2026-11-24", updated_at: "x", error: null }],
  }));
  render(
    <MemoryRouter>
      <TracesPage />
    </MemoryRouter>,
  );
  const row = await screen.findByTestId("run-row");
  expect(row).toHaveTextContent("Cats purr");
  expect(row).toHaveTextContent("done");
  expect(within(row).getByRole("link")).toHaveAttribute("href", "/traces/r1");
});

it("renders spans and expands input, output and llm prompts", async () => {
  const spans = [
    span(1, { kind: "user", name: "claim" }),
    span(2, {
      kind: "llm",
      name: "decompose",
      model: "claude-x",
      input: { system: "SYSTEM PROMPT TEXT", user: "USER MESSAGE TEXT", schema: "S" },
      output: { raw: "x" },
      usage: { input_tokens: 120, output_tokens: 30 },
    }),
  ];
  mockFetch(() => ({ body: { run_id: "r1", spans } }));
  render(
    <MemoryRouter initialEntries={["/traces/r1"]}>
      <Routes>
        <Route path="/traces/:runId" element={<TracePage />} />
      </Routes>
    </MemoryRouter>,
  );
  const rows = await screen.findAllByTestId("span-row");
  expect(rows).toHaveLength(2);
  expect(rows[1]).toHaveTextContent("llm");
  expect(rows[1]).toHaveTextContent("claude-x");
  expect(rows[1]).toHaveTextContent("1.5 s");
  expect(rows[1]).toHaveTextContent("120 → 30 tokens");
  expect(screen.queryByText(/SYSTEM PROMPT TEXT/)).toBeNull();

  await userEvent.click(within(rows[1]!).getByTestId("span-toggle"));
  expect(screen.getByText("SYSTEM PROMPT TEXT")).toBeInTheDocument();
  expect(screen.getByText("USER MESSAGE TEXT")).toBeInTheDocument();
  expect(rows[1]).toHaveTextContent('"raw": "x"');

  await userEvent.click(within(rows[0]!).getByTestId("span-toggle"));
  expect(rows[0]).toHaveTextContent('"a": 1');
  expect(within(rows[0]!).queryByText("System prompt")).toBeNull();
});
