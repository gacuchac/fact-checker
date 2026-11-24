import { type FormEvent, type ReactNode, useEffect, useRef, useState } from "react";
import { setAccessCodePrompt } from "../api";

interface Props {
  children: ReactNode;
}

export function AccessCodeGate({ children }: Props): JSX.Element {
  const [asking, setAsking] = useState(false);
  const [wrong, setWrong] = useState(false);
  const [value, setValue] = useState("");
  const resolver = useRef<((code: string) => void) | null>(null);

  useEffect(() => {
    setAccessCodePrompt(
      (wasWrong) =>
        new Promise<string>((resolve) => {
          resolver.current = resolve;
          setWrong(wasWrong);
          setAsking(true);
        }),
    );
    return () => setAccessCodePrompt(null);
  }, []);

  function submit(event: FormEvent): void {
    event.preventDefault();
    resolver.current?.(value.trim());
    resolver.current = null;
    setAsking(false);
    setValue("");
  }

  return (
    <>
      {children}
      {asking && (
        <div className="overlay">
          <form className="card access-form" onSubmit={submit}>
            <h2>Access code</h2>
            <p>This server needs an access code.</p>
            {wrong && <p className="issue">Wrong access code</p>}
            <input
              data-testid="access-code-input"
              type="password"
              autoFocus
              value={value}
              onChange={(e) => setValue(e.target.value)}
            />
            <button data-testid="access-code-submit" type="submit">Continue</button>
          </form>
        </div>
      )}
    </>
  );
}
