import { humanizeKey, isLongText, isNested } from "../readable";

function Empty({ text }: { text: string }): JSX.Element {
  return <span className="rv-empty">{text}</span>;
}

function ReadableText({ text }: { text: string }): JSX.Element {
  if (text === "") return <Empty text="empty text" />;
  return isLongText(text) ? <div className="rv-text">{text}</div> : <span>{text}</span>;
}

function ReadableList({ items }: { items: unknown[] }): JSX.Element {
  if (items.length === 0) return <Empty text="no items" />;
  return (
    <ol className="rv-list">
      {items.map((item, i) => (
        <li key={i}>
          <ReadableValue value={item} />
        </li>
      ))}
    </ol>
  );
}

function ReadableObject({ value }: { value: object }): JSX.Element {
  const entries = Object.entries(value);
  if (entries.length === 0) return <Empty text="no fields" />;
  return (
    <dl className="rv-obj">
      {entries.map(([key, item]) => (
        <div className={isNested(item) ? "rv-row rv-nested" : "rv-row"} key={key}>
          <dt>{humanizeKey(key)}</dt>
          <dd>
            <ReadableValue value={item} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** Render any JSON value for reading, as React text only: objects as labelled rows, arrays as numbered lists. */
export function ReadableValue({ value }: { value: unknown }): JSX.Element {
  if (value === null || value === undefined) return <Empty text="none" />;
  if (typeof value === "string") return <ReadableText text={value} />;
  if (Array.isArray(value)) return <ReadableList items={value} />;
  if (typeof value === "object") return <ReadableObject value={value} />;
  return <span className="rv-plain">{String(value)}</span>;
}
