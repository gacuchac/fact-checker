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

const PAYLOAD = '<img src=x onerror="window.__xss=1">';

async function openOnly(spans: Span[]): Promise<HTMLElement> {
  mockFetch(() => ({ body: { run_id: "r1", spans } }));
  render(
    <MemoryRouter initialEntries={["/traces/r1"]}>
      <Routes>
        <Route path="/traces/:runId" element={<TracePage />} />
      </Routes>
    </MemoryRouter>,
  );
  const [row] = await screen.findAllByTestId("span-row");
  await userEvent.click(within(row!).getByTestId("span-toggle"));
  return row!;
}

function valueOf(box: HTMLElement, label: string): HTMLElement {
  const term = within(box).getByText(label, { selector: "dt" });
  return term.nextElementSibling as HTMLElement;
}

describe("readable span input and output", () => {
  const output = {
    hits: [
      { passage_id: "p1", score: 0.82, text: "line one\nline two", verified: true, note: null },
      { passage_id: "p2", score: 0.5, text: "short", verified: false, note: null },
    ],
    servedModel: "m-1",
    [PAYLOAD]: [PAYLOAD],
  };

  it("shows objects as labelled rows with humanised keys and arrays as numbered items", async () => {
    const row = await openOnly([span(1, { kind: "tool", name: "retrieve", input: { query: "long context", per_doc: 2 }, output })]);
    const input = within(row).getByTestId("span-input");
    expect(valueOf(input, "Query")).toHaveTextContent(/^long context$/);
    expect(valueOf(input, "Per doc")).toHaveTextContent(/^2$/);

    const out = within(row).getByTestId("span-output");
    expect(valueOf(out, "Served model")).toHaveTextContent(/^m-1$/);
    const list = valueOf(out, "Hits").querySelector("ol");
    expect(list).not.toBeNull();
    const items = within(list!).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(valueOf(items[0]!, "Passage id")).toHaveTextContent(/^p1$/);
    expect(valueOf(items[0]!, "Score")).toHaveTextContent(/^0\.82$/);
    expect(valueOf(items[0]!, "Verified")).toHaveTextContent(/^true$/);
    expect(valueOf(items[1]!, "Verified")).toHaveTextContent(/^false$/);
    expect(valueOf(items[0]!, "Note")).toHaveTextContent(/^none$/);
    expect(valueOf(items[0]!, "Text").textContent).toBe("line one\nline two");

    expect(row.querySelector('img[src="x"]')).toBeNull();
    expect(within(out).getAllByText(PAYLOAD, { exact: false }).length).toBeGreaterThan(0);
  });

  it("keeps the exact JSON behind a Show raw JSON toggle in each box", async () => {
    const row = await openOnly([span(1, { kind: "tool", name: "retrieve", output })]);
    const out = within(row).getByTestId("span-output");
    const raw = within(out).getByTestId("raw-json");
    expect(raw).not.toBeVisible();
    await userEvent.click(within(out).getByText("Show raw JSON"));
    expect(raw).toBeVisible();
    expect(raw.textContent).toBe(JSON.stringify(output, null, 2));
    expect(within(out).getByText("Hide raw JSON")).toBeInTheDocument();
    expect(within(within(row).getByTestId("span-input")).getByText("Show raw JSON")).toBeInTheDocument();
  });

  it("does not repeat an llm span's prompts in its readable input", async () => {
    const input = { system: "SYSTEM TEXT", user: "USER TEXT", schema: "VerdictsOutput", effort: null };
    const row = await openOnly([span(1, { kind: "llm", name: "verify", model: "claude-x", input })]);
    const box = within(row).getByTestId("span-input");
    expect(valueOf(box, "Schema")).toHaveTextContent(/^VerdictsOutput$/);
    expect(within(box).queryByText("System", { selector: "dt" })).toBeNull();
    expect(within(box).queryByText("User", { selector: "dt" })).toBeNull();
    expect(screen.getByText("SYSTEM TEXT")).toBeInTheDocument();
  });
});
