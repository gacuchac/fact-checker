import type { Span } from "./types";

/** Return the span's duration in milliseconds, or null when a timestamp does not parse. */
export function durationMs(span: Span): number | null {
  const ms = Date.parse(span.ended_at) - Date.parse(span.started_at);
  return Number.isNaN(ms) ? null : ms;
}

export function formatDuration(ms: number | null): string {
  if (ms === null) return "–";
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

/** Return "in → out tokens" from a span's usage, or an empty string when it has none. */
export function formatTokens(usage: unknown): string {
  if (typeof usage !== "object" || usage === null) return "";
  const { input_tokens: input, output_tokens: output } = usage as Record<string, unknown>;
  if (typeof input !== "number" || typeof output !== "number") return "";
  return `${input} → ${output} tokens`;
}

/** Return the system and user texts of an llm span's input, or null when it holds neither. */
export function llmPrompt(input: unknown): { system: string; user: string } | null {
  if (typeof input !== "object" || input === null) return null;
  const { system, user } = input as Record<string, unknown>;
  return typeof system === "string" && typeof user === "string" ? { system, user } : null;
}
