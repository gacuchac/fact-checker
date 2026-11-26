import type { ReactNode } from "react";

const MEANING = "if this statement is false, the whole claim is false. Only load-bearing statements decide the overall verdict; the others are still checked but do not change it.";

/** The tooltip text for anything labelled "load-bearing": the term and what it means. */
export const LOAD_BEARING_TITLE = `Load-bearing: ${MEANING}`;

interface Props {
  id: string;
  children?: ReactNode;
}

/** A visible explanation of "load-bearing", followed by children; id is what aria-describedby points at. */
export function LoadBearingHint({ id, children }: Props): JSX.Element {
  return (
    <p className="hint" id={id} data-testid="load-bearing-hint">
      <strong>Load-bearing</strong>: {MEANING}
      {children}
    </p>
  );
}
