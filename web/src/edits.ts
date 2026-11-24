import type { Edit, Statement } from "./types";

export interface Row {
  statement: Statement;
  text: string;
  loadBearing: boolean;
  dropped: boolean;
}

export interface AddedRow {
  key: number;
  text: string;
}

export function rowsFrom(statements: Statement[]): Row[] {
  return statements.map((statement) => ({
    statement,
    text: statement.text,
    loadBearing: statement.load_bearing,
    dropped: false,
  }));
}

/** Turn the user's changes to the proposed statements into the ordered Edit records the confirm call takes. */
export function buildEdits(rows: Row[], added: AddedRow[]): Edit[] {
  const edits: Edit[] = [];
  for (const row of rows) {
    const id = row.statement.id;
    if (row.dropped) {
      edits.push({ op: "drop", id, value: null });
      continue;
    }
    if (row.text !== row.statement.text) edits.push({ op: "edit", id, value: row.text });
    if (row.loadBearing !== row.statement.load_bearing) edits.push({ op: "flip_load_bearing", id, value: null });
  }
  for (const item of added) {
    if (item.text.trim() !== "") edits.push({ op: "add", id: null, value: item.text.trim() });
  }
  return edits;
}
