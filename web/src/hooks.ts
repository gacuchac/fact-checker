import { useEffect, useState } from "react";

export type Loaded<T> =
  | { state: "loading" }
  | { state: "error"; message: string; retry: () => void }
  | { state: "ready"; data: T };

/** Load a value with load() whenever key changes; the result is loading, an error message with a retry function, or the data. */
export function useLoad<T>(load: () => Promise<T>, key: string): Loaded<T> {
  const [result, setResult] = useState<Loaded<T> | { state: "loading" }>({ state: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    setResult({ state: "loading" });
    load().then(
      (data) => live && setResult({ state: "ready", data }),
      (error: unknown) =>
        live &&
        setResult({
          state: "error",
          message: error instanceof Error ? error.message : String(error),
          retry: () => setAttempt((n) => n + 1),
        }),
    );
    return () => {
      live = false;
    };
  }, [key, attempt]);
  return result;
}
