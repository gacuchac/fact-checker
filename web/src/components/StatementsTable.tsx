import { useState } from "react";
import type { AddedRow, Row } from "../edits";
import type { ConfirmIssue } from "../types";

interface Props {
  rows: Row[];
  added: AddedRow[];
  issues: ConfirmIssue[];
  onRows: (rows: Row[]) => void;
  onAdded: (added: AddedRow[]) => void;
}

function replaceAt<T>(items: T[], index: number, item: T): T[] {
  return items.map((existing, i) => (i === index ? item : existing));
}

interface TextCellProps {
  text: string;
  onSave: (text: string) => void;
}

function TextCell({ text, onSave }: TextCellProps): JSX.Element {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(text);
  if (!editing) {
    return (
      <>
        <span>{text}</span>{" "}
        <button type="button" className="link" data-testid="statement-edit" onClick={() => { setDraft(text); setEditing(true); }}>
          Edit
        </button>
      </>
    );
  }
  return (
    <>
      <input data-testid="statement-edit-input" value={draft} onChange={(e) => setDraft(e.target.value)} />{" "}
      <button type="button" data-testid="statement-edit-save" onClick={() => { onSave(draft); setEditing(false); }}>
        Save
      </button>
    </>
  );
}

export function StatementsTable({ rows, added, issues, onRows, onAdded }: Props): JSX.Element {
  const [nextKey, setNextKey] = useState(1);
  const known = new Set(rows.map((r) => r.statement.id));
  const unmatched = issues.filter((issue) => !known.has(issue.statement_id));

  return (
    <div>
      {unmatched.map((issue, i) => (
        <p key={i} className="issue" data-testid="issue">
          Statement {issue.statement_id}: {issue.reason}
        </p>
      ))}
      <table className="statements">
        <thead>
          <tr>
            <th>Id</th>
            <th>Statement</th>
            <th>Kind</th>
            <th>Load-bearing</th>
            <th>Implied by</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={row.statement.id} data-testid="statement-row" className={row.dropped ? "dropped" : undefined}>
              <td>{row.statement.id}</td>
              <td>
                {row.dropped ? (
                  <s>{row.text}</s>
                ) : (
                  <TextCell text={row.text} onSave={(text) => onRows(replaceAt(rows, index, { ...row, text }))} />
                )}
                {issues
                  .filter((issue) => issue.statement_id === row.statement.id)
                  .map((issue, i) => (
                    <div key={i} className="issue" data-testid="issue">
                      {issue.reason}
                    </div>
                  ))}
              </td>
              <td>{row.statement.kind}</td>
              <td>
                <input
                  type="checkbox"
                  aria-label={`load-bearing ${row.statement.id}`}
                  data-testid="statement-load-bearing"
                  checked={row.loadBearing}
                  disabled={row.dropped}
                  onChange={() => onRows(replaceAt(rows, index, { ...row, loadBearing: !row.loadBearing }))}
                />
              </td>
              <td className="span">{row.statement.implied_by}</td>
              <td>
                <button
                  type="button"
                  data-testid={row.dropped ? "statement-restore" : "statement-drop"}
                  onClick={() => onRows(replaceAt(rows, index, { ...row, dropped: !row.dropped }))}
                >
                  {row.dropped ? "Restore" : "Drop"}
                </button>
              </td>
            </tr>
          ))}
          {added.map((item, index) => (
            <tr key={`added-${item.key}`} data-testid="added-row">
              <td>new</td>
              <td colSpan={4}>
                <input
                  data-testid="added-input"
                  placeholder="New statement"
                  value={item.text}
                  onChange={(e) => onAdded(replaceAt(added, index, { ...item, text: e.target.value }))}
                />
              </td>
              <td>
                <button type="button" onClick={() => onAdded(added.filter((_, i) => i !== index))}>
                  Remove
                </button>
              </td>
            </tr>
          ))}
          <tr>
            <td colSpan={6}>
              <button
                type="button"
                data-testid="add-statement"
                onClick={() => {
                  onAdded([...added, { key: nextKey, text: "" }]);
                  setNextKey(nextKey + 1);
                }}
              >
                Add statement
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
