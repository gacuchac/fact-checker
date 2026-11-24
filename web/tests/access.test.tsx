import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { App } from "../src/App";
import { mockFetch } from "./helpers";

afterEach(() => vi.unstubAllGlobals());

it("shows the access-code form on 401 and retries with the entered code", async () => {
  const calls = mockFetch((_url, init) =>
    new Headers(init.headers).get("X-Access-Code") === "abc" ? { body: [] } : { status: 401, body: { detail: "access code required" } },
  );
  render(
    <MemoryRouter initialEntries={["/traces"]}>
      <App />
    </MemoryRouter>,
  );
  await userEvent.type(await screen.findByTestId("access-code-input"), "abc");
  await userEvent.click(screen.getByTestId("access-code-submit"));
  expect(await screen.findByText("No runs yet.")).toBeInTheDocument();
  expect(calls.at(-1)?.headers.get("X-Access-Code")).toBe("abc");
  expect(localStorage.getItem("fc-access-code")).toBe("abc");
});

it("shows Wrong access code, clears the rejected code, and saves only an accepted one", async () => {
  localStorage.setItem("fc-access-code", "stale");
  mockFetch((_url, init) =>
    new Headers(init.headers).get("X-Access-Code") === "abc" ? { body: [] } : { status: 401, body: { detail: "access code required" } },
  );
  render(
    <MemoryRouter initialEntries={["/traces"]}>
      <App />
    </MemoryRouter>,
  );
  await userEvent.type(await screen.findByTestId("access-code-input"), "nope");
  await userEvent.click(screen.getByTestId("access-code-submit"));
  expect(await screen.findByText("Wrong access code")).toBeInTheDocument();
  expect(localStorage.getItem("fc-access-code")).toBeNull();
  await userEvent.type(screen.getByTestId("access-code-input"), "abc");
  await userEvent.click(screen.getByTestId("access-code-submit"));
  expect(await screen.findByText("No runs yet.")).toBeInTheDocument();
  expect(localStorage.getItem("fc-access-code")).toBe("abc");
});

it("offers Retry on a failed page load", async () => {
  let n = 0;
  mockFetch(() => (++n === 1 ? { status: 500, body: { detail: "boom" } } : { body: [] }));
  render(
    <MemoryRouter initialEntries={["/traces"]}>
      <App />
    </MemoryRouter>,
  );
  expect(await screen.findByText("boom")).toBeInTheDocument();
  await userEvent.click(screen.getByTestId("retry-button"));
  expect(await screen.findByText("No runs yet.")).toBeInTheDocument();
});
