const LONG_TEXT = 80;

/** Return a data key as a label: "passage_id" -> "Passage id", "servedModel" -> "Served model"; a key with no words is returned unchanged. */
export function humanizeKey(key: string): string {
  const words = key
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[_-]+/g, " ")
    .trim()
    .toLowerCase();
  return words === "" ? key : words.charAt(0).toUpperCase() + words.slice(1);
}

/** Return true when text should read as a wrapped block rather than inline: it has a line break or is long. */
export function isLongText(text: string): boolean {
  return text.includes("\n") || text.length > LONG_TEXT;
}

/** Return true when value is a non-empty object or array, which reads best below its label rather than beside it. */
export function isNested(value: unknown): boolean {
  if (Array.isArray(value)) return value.length > 0;
  return typeof value === "object" && value !== null && Object.keys(value).length > 0;
}

/** Return value without the given keys when it is a plain object; any other value is returned unchanged. */
export function omitKeys(value: unknown, keys: string[]): unknown {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return value;
  return Object.fromEntries(Object.entries(value).filter(([key]) => !keys.includes(key)));
}
