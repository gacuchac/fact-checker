import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { CheckPage } from "../src/pages/CheckPage";
import type { ClaimRun, Statement } from "../src/types";
import { checkResult, mockFetch, type FetchCall, type Handler, scores, statement } from "./helpers";

afterEach(() => vi.unstubAllGlobals());

const proposed: Statement[] = [statement(1, "Cats are mammals"), statement(2, "Cats are large", { kind: "implicit_assumption" })];

function run(overrides: Partial<ClaimRun>): ClaimRun {
  return {
    run_id: "r1",
    claim: "claim",
    status: "verifying",
    proposed,
    confirmed: null,
    result: null,
    error: null,
    created_at: "t",
    updated_at: "t",
    ...overrides,
  };
}

function setup(handler: Handler): FetchCall[] {
  const calls = mockFetch((url, init) => {
    if (url === "/api/claims" && init.method === "POST") return { status: 201, body: { run_id: "r1", claim: "claim", proposed } };
    return handler(url, init);
  });
  render(
    <MemoryRouter>
      <CheckPage pollMs={10} />
    </MemoryRouter>,
  );
  return calls;
}

async function breakDown(): Promise<void> {
  await userEvent.type(screen.getByTestId("claim-input"), "Cats are large mammals");
  await userEvent.click(screen.getByTestId("decompose-button"));
  await screen.findAllByTestId("statement-row");
}

describe("Check page", () => {
  it("renders one row per proposed statement", async () => {
    setup(() => undefined);
    await breakDown();
    const rows = screen.getAllByTestId("statement-row");
    expect(rows).toHaveLength(2);
    expect(within(rows[1]!).getByText("implicit_assumption")).toBeInTheDocument();
  });

  it("drop and approve sends the drop edit then verify", async () => {
    const calls = setup((url) => {
      if (url.endsWith("/confirm")) return { body: { confirmed: {} } };
      if (url.endsWith("/verify")) return { status: 202, body: { run_id: "r1", status: "verifying" } };
      return { body: run({}) };
    });
    await breakDown();
    await userEvent.click(screen.getAllByTestId("statement-drop")[1]!);
    await userEvent.click(screen.getByTestId("approve-button"));
    await screen.findByTestId("progress");
    const confirm = calls.find((c) => c.url === "/api/claims/r1/confirm");
    expect(confirm?.body).toEqual({ edits: [{ op: "drop", id: 2, value: null }] });
    expect(calls.some((c) => c.url === "/api/claims/r1/verify" && c.method === "POST")).toBe(true);
  });

  it("sends edit, flip and add edits", async () => {
    const calls = setup((url) => (url.endsWith("/confirm") ? { status: 422, body: { issues: [] } } : undefined));
    await breakDown();
    const row = screen.getAllByTestId("statement-row")[0]!;
    await userEvent.click(within(row).getByTestId("statement-edit"));
    const input = within(row).getByTestId("statement-edit-input");
    await userEvent.clear(input);
    await userEvent.type(input, "Cats are animals");
    await userEvent.click(within(row).getByTestId("statement-edit-save"));
    await userEvent.click(within(row).getByTestId("statement-load-bearing"));
    await userEvent.click(screen.getByTestId("add-statement"));
    await userEvent.type(screen.getByTestId("added-input"), "Cats purr");
    await userEvent.click(screen.getByTestId("approve-button"));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/confirm"))).toBe(true));
    expect(calls.find((c) => c.url.endsWith("/confirm"))?.body).toEqual({
      edits: [
        { op: "edit", id: 1, value: "Cats are animals" },
        { op: "flip_load_bearing", id: 1, value: null },
        { op: "add", id: null, value: "Cats purr" },
      ],
    });
  });

  it("renders 422 issues next to their statement and does not verify", async () => {
    const calls = setup((url) =>
      url.endsWith("/confirm") ? { status: 422, body: { issues: [{ statement_id: 2, reason: "not in the claim" }] } } : undefined,
    );
    await breakDown();
    await userEvent.click(screen.getByTestId("approve-button"));
    const issue = await screen.findByTestId("issue");
    expect(issue).toHaveTextContent("not in the claim");
    expect(screen.getAllByTestId("statement-row")[1]).toContainElement(issue);
    expect(calls.some((c) => c.url.endsWith("/verify"))).toBe(false);
  });

  it("polls until done, stops, and renders the result", async () => {
    let polls = 0;
    const result = checkResult({
      scores: scores({ needs_attention: true }),
      revised: true,
      first_final: { ...checkResult().final, overall: { verdict: "contradicted", rule: 1 } },
    });
    const calls = setup((url) => {
      if (url.endsWith("/confirm")) return { body: { confirmed: {} } };
      if (url.endsWith("/verify")) return { status: 202, body: { run_id: "r1", status: "verifying" } };
      polls += 1;
      return { body: polls < 3 ? run({}) : run({ status: "done", result }) };
    });
    await breakDown();
    await userEvent.click(screen.getByTestId("approve-button"));
    expect(await screen.findByTestId("progress")).toHaveTextContent("Verifying");
    expect(await screen.findByTestId("result-overall")).toHaveTextContent("supported");
    const seen = calls.filter((c) => c.method === "GET").length;
    await new Promise((r) => setTimeout(r, 60));
    expect(calls.filter((c) => c.method === "GET").length).toBe(seen);

    expect(screen.queryByTestId("progress")).toBeNull();
    const quote = screen.getByTestId("evidence-quote");
    expect(quote).toHaveTextContent("models struggle to use long contexts well");
    expect(quote).toHaveTextContent("Lost in the Middle");
    expect(quote).toHaveTextContent("Nelson Liu, Kevin Lin");
    expect(quote).toHaveTextContent("2023-07-06");
    expect(within(quote).getByRole("link")).toHaveAttribute("href", "https://arxiv.org/abs/2307.03172v3");
    expect(screen.getByTestId("statement-verdict")).toHaveTextContent("supported");
    expect(screen.getByTestId("review-panel")).toHaveTextContent("evidence relevance");
    expect(screen.getByTestId("needs-attention")).toBeInTheDocument();
    expect(screen.getByTestId("revised-banner")).toBeInTheDocument();
    expect(screen.getByTestId("final-message")).toHaveTextContent("FINAL MESSAGE TEXT");
    expect(screen.getByTestId("view-trace")).toHaveAttribute("href", "/traces/r1");

    expect(screen.queryByTestId("first-answer")).toBeNull();
    await userEvent.click(screen.getByTestId("first-answer-toggle"));
    expect(within(screen.getByTestId("first-answer")).getByTestId("result-overall")).toHaveTextContent("contradicted");
  });

  it("says when the code consistency check caused the revision and lists its flags", async () => {
    const result = checkResult({
      revised: true,
      first_scores: scores({ needs_attention: false }),
      consistency_flags: [
        { statement_id: 1, dimension: "unknown_calibration", reason: "Code check: every kept quote supports the statement" },
      ],
    });
    setup((url) => {
      if (url.endsWith("/confirm")) return { body: { confirmed: {} } };
      if (url.endsWith("/verify")) return { status: 202, body: { run_id: "r1", status: "verifying" } };
      return { body: run({ status: "done", result }) };
    });
    await breakDown();
    await userEvent.click(screen.getByTestId("approve-button"));
    const banner = await screen.findByTestId("revised-banner");
    expect(banner).toHaveTextContent("Revised after the code consistency check.");
    expect(screen.getByTestId("consistency-flags")).toHaveTextContent("Statement 1: Code check: every kept quote supports");
  });

  it("shows the code flags even when the review failed and nothing was revised", async () => {
    const result = checkResult({
      scores: null,
      review_error: "down",
      consistency_flags: [{ statement_id: 0, dimension: "unknown_calibration", reason: "Code check: one-sided" }],
    });
    setup((url) => {
      if (url.endsWith("/confirm")) return { body: { confirmed: {} } };
      if (url.endsWith("/verify")) return { status: 202, body: { run_id: "r1", status: "verifying" } };
      return { body: run({ status: "done", result }) };
    });
    await breakDown();
    await userEvent.click(screen.getByTestId("approve-button"));
    await screen.findByTestId("result-overall");
    expect(screen.queryByTestId("revised-banner")).toBeNull();
    expect(screen.getByTestId("consistency-flags")).toHaveTextContent("Statement 0: Code check: one-sided");
  });

  it("shows no banner or needs-attention for a plain result", async () => {
    setup((url) => {
      if (url.endsWith("/confirm")) return { body: { confirmed: {} } };
      if (url.endsWith("/verify")) return { status: 202, body: { run_id: "r1", status: "verifying" } };
      return { body: run({ status: "done", result: checkResult() }) };
    });
    await breakDown();
    await userEvent.click(screen.getByTestId("approve-button"));
    await screen.findByTestId("result-overall");
    expect(screen.queryByTestId("revised-banner")).toBeNull();
    expect(screen.queryByTestId("needs-attention")).toBeNull();
  });

  it("shows the error when the run fails", async () => {
    setup((url) => {
      if (url.endsWith("/confirm")) return { body: { confirmed: {} } };
      if (url.endsWith("/verify")) return { status: 202, body: { run_id: "r1", status: "verifying" } };
      return { body: run({ status: "failed", error: "model unavailable" }) };
    });
    await breakDown();
    await userEvent.click(screen.getByTestId("approve-button"));
    expect(await screen.findByText(/model unavailable/)).toBeInTheDocument();
  });

  it("after verify fails, retry only calls verify and shows the error", async () => {
    let verifies = 0;
    const calls = setup((url) => {
      if (url.endsWith("/confirm")) return { body: { confirmed: {} } };
      if (url.endsWith("/verify")) {
        verifies += 1;
        return verifies === 1
          ? { status: 429, body: { detail: "daily cap reached" } }
          : { status: 202, body: { run_id: "r1", status: "verifying" } };
      }
      return { body: run({}) };
    });
    await breakDown();
    await userEvent.click(screen.getByTestId("approve-button"));
    expect(await screen.findByText(/daily cap reached/)).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("retry-verify-button"));
    await screen.findByTestId("progress");
    expect(calls.filter((c) => c.url.endsWith("/confirm"))).toHaveLength(1);
    expect(verifies).toBe(2);
  });

  it("disables Add statement at five kept statements and shows a hint", async () => {
    setup(() => undefined);
    await breakDown();
    for (let i = 0; i < 3; i++) await userEvent.click(screen.getByTestId("add-statement"));
    expect(screen.getByTestId("add-statement")).toBeDisabled();
    expect(screen.getByTestId("add-limit-hint")).toBeInTheDocument();
    await userEvent.click(screen.getAllByTestId("statement-drop")[0]!);
    expect(screen.getByTestId("add-statement")).toBeEnabled();
  });

  it("renders a 422 with a detail message above the table", async () => {
    setup((url) => (url.endsWith("/confirm") ? { status: 422, body: { detail: "too many statements" } } : undefined));
    await breakDown();
    await userEvent.click(screen.getByTestId("approve-button"));
    expect(await screen.findByText(/too many statements/)).toBeInTheDocument();
  });
});
