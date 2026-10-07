export type TestDataRow = { label: string; value: string };

export type ParsedStoredTestData = {
  precondition: string | null;
  rows: TestDataRow[];
  notes: string | null;
};

const PRE_PREFIX = /^Precondición:\s*/i;
const MDP_PREFIX = /^MDP:\s*/i;
const JSON_OBJECT = /\{[^{}]+\}/g;
const KEY_VALUE = /["']([A-Za-z_][\w]*)["']\s*:\s*("[^"]*"|'[^']*'|true|false|null|-?\d+(?:\.\d+)?)/g;

function stringifyValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "null";
  }
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value);
}

function rowsFromJsonBlob(blob: string): TestDataRow[] {
  try {
    const parsed = JSON.parse(blob) as unknown;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return Object.entries(parsed as Record<string, unknown>).map(([label, value]) => ({
        label,
        value: stringifyValue(value),
      }));
    }
  } catch {
    /* loose pairs below */
  }
  const rows: TestDataRow[] = [];
  for (const match of blob.matchAll(KEY_VALUE)) {
    rows.push({ label: match[1], value: match[2].replace(/^["']|["']$/g, "") });
  }
  return rows;
}

function uniqueRows(rows: TestDataRow[]): TestDataRow[] {
  const seen = new Set<string>();
  const out: TestDataRow[] = [];
  for (const row of rows) {
    const key = `${row.label}\0${row.value}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    out.push(row);
  }
  return out;
}

export function parseStoredTestData(raw: string | null | undefined): ParsedStoredTestData | null {
  const text = (raw || "").trim();
  if (!text) {
    return null;
  }

  const blocks = text.split(/\n+/).map((block) => block.trim()).filter(Boolean);
  let precondition: string | null = null;
  const rows: TestDataRow[] = [];
  const noteParts: string[] = [];

  for (const block of blocks) {
    if (!precondition && PRE_PREFIX.test(block)) {
      precondition = block.replace(PRE_PREFIX, "").trim() || null;
      continue;
    }
    if (MDP_PREFIX.test(block)) {
      const value = block.replace(MDP_PREFIX, "").trim();
      if (value) {
        rows.push({ label: "MDP", value });
      }
      continue;
    }
    noteParts.push(block);
    for (const blob of block.match(JSON_OBJECT) ?? []) {
      rows.push(...rowsFromJsonBlob(blob));
    }
  }

  const notes = noteParts.join("\n").trim() || null;
  return {
    precondition,
    rows: uniqueRows(rows),
    notes,
  };
}
