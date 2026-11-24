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
