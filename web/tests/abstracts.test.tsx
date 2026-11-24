import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AbstractsPage } from "../src/pages/AbstractsPage";
import { DocPage } from "../src/pages/DocPage";
import { mockFetch } from "./helpers";

afterEach(() => vi.unstubAllGlobals());

it("searches and renders paper rows", async () => {
  const calls = mockFetch(() => ({
    body: [
      { doc_id: "2307.03172v3", title: "Lost in the Middle", authors: ["A B", "C D"], published: "2023-07-06" },
      { doc_id: "2001.00001v1", title: "Other paper", authors: ["E F"], published: "2020-01-01" },
    ],
  }));
  render(
    <MemoryRouter>
      <AbstractsPage />
    </MemoryRouter>,
  );
  await userEvent.type(screen.getByTestId("doc-search"), "long context{enter}");
  const rows = await screen.findAllByTestId("doc-row");
  expect(rows).toHaveLength(2);
  expect(rows[0]).toHaveTextContent("Lost in the Middle");
  expect(rows[0]).toHaveTextContent("A B, C D");
  expect(rows[0]).toHaveTextContent("2023-07-06");
  expect(calls[0]?.url).toBe("/api/docs?q=long%20context&limit=20");
});

it("shows the abstract of one paper", async () => {
  mockFetch(() => ({
    body: { doc_id: "d1", base_id: "d", title: "T", authors: ["A"], published: "2023", abstract: "THE ABSTRACT" },
  }));
  render(
    <MemoryRouter initialEntries={["/abstracts/d1"]}>
      <Routes>
        <Route path="/abstracts/:docId" element={<DocPage />} />
      </Routes>
    </MemoryRouter>,
  );
  expect(await screen.findByTestId("doc-abstract")).toHaveTextContent("THE ABSTRACT");
});
