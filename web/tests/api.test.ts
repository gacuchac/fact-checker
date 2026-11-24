import { ApiError, request, saveAccessCode, setAccessCodePrompt } from "../src/api";
import { mockFetch } from "./helpers";

afterEach(() => {
  setAccessCodePrompt(null);
  vi.unstubAllGlobals();
});

describe("api client", () => {
  it("sends the stored access code as X-Access-Code", async () => {
    saveAccessCode("secret");
    const calls = mockFetch(() => ({ body: { ok: true } }));
    await request("/api/health");
    expect(calls[0]?.headers.get("X-Access-Code")).toBe("secret");
  });

  it("sends no header when no code is stored", async () => {
    const calls = mockFetch(() => ({ body: {} }));
    await request("/api/health");
    expect(calls[0]?.headers.has("X-Access-Code")).toBe(false);
  });

  it("works when localStorage throws", async () => {
    const spy = vi.spyOn(localStorage, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    mockFetch(() => ({ body: { ok: true } }));
    await expect(request("/api/health")).resolves.toEqual({ ok: true });
    spy.mockRestore();
  });

  it("on 401 asks for a code, saves it and retries", async () => {
    const calls = mockFetch((_url, init) =>
      new Headers(init.headers).get("X-Access-Code") === "good"
        ? { body: { data: 1 } }
        : { status: 401, body: { detail: "access code required" } },
    );
    setAccessCodePrompt(() => Promise.resolve("good"));
    await expect(request("/api/runs")).resolves.toEqual({ data: 1 });
    expect(calls).toHaveLength(2);
    expect(localStorage.getItem("fc-access-code")).toBe("good");
  });

  it("throws ApiError with the status and body on other errors", async () => {
    mockFetch(() => ({ status: 422, body: { issues: [] } }));
    await expect(request("/api/x")).rejects.toMatchObject({ status: 422, body: { issues: [] } });
    await expect(request("/api/x")).rejects.toBeInstanceOf(ApiError);
  });

  it("throws on 401 when no prompt is registered", async () => {
    mockFetch(() => ({ status: 401, body: { detail: "access code required" } }));
    await expect(request("/api/x")).rejects.toMatchObject({ status: 401 });
  });
});
