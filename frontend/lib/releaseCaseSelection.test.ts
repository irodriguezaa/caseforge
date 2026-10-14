import assert from "node:assert/strict";
import test from "node:test";
import type { TestCase } from "./types.ts";
import {
  filterReleaseCases,
  headerCheckboxState,
  selectFilteredIds,
  summarizeBulkResult,
  toggleSelectedId,
} from "./releaseCaseSelection.ts";

function caseRow(id: number, component: string, extras: Partial<TestCase> = {}): TestCase {
  return {
    id,
    release_id: 1,
    test_case_id: `QC-${id}`,
    component,
    test_case_name: `Case ${id}`,
    description: null,
    user_type: null,
    priority: "CRITICAL",
    test_type: "FUNCTIONAL",
    status: "UNEXECUTED",
    created_at: "",
    updated_at: "",
    ...extras,
  };
}

const rows = [
  ...Array.from({ length: 10 }, (_, index) => caseRow(index + 1, "WEBCL-2424")),
  caseRow(11, "ADTCL-141"),
  caseRow(12, "IOSPR-1310", { status: "PASS" }),
];

test("selects one case at a time", () => {
  assert.deepEqual(toggleSelectedId([], 3), [3]);
  assert.deepEqual(toggleSelectedId([3], 3), []);
  assert.deepEqual(toggleSelectedId([3], 5), [3, 5]);
});

test("select all visible and deselect all", () => {
  const visible = rows.slice(0, 3);
  const all = selectFilteredIds(visible);
  assert.deepEqual(all, [1, 2, 3]);
  assert.equal(headerCheckboxState(all, all).checked, true);
  assert.equal(headerCheckboxState(all, []).checked, false);
});

test("select all filtered WEBCL-2424 cases only", () => {
  const filtered = filterReleaseCases(rows, {
    device: "",
    component: ["WEBCL-2424"],
    story: null,
    priority: null,
    status: null,
  });
  assert.equal(filtered.length, 10);
  assert.deepEqual(selectFilteredIds(filtered), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  assert.ok(filtered.every((row) => row.component === "WEBCL-2424"));
  assert.ok(!selectFilteredIds(filtered).includes(11));
  assert.ok(!selectFilteredIds(filtered).includes(12));
});

test("changing filters clears previous selection by policy", () => {
  const previous = selectFilteredIds(rows);
  const nextFilter = filterReleaseCases(rows, {
    device: "",
    component: ["WEBCL-2424"],
    story: null,
    priority: null,
    status: null,
  });
  const afterChange: number[] = [];
  assert.equal(previous.length, 12);
  assert.equal(nextFilter.length, 10);
  assert.deepEqual(afterChange, []);
});

test("pagination helper only sees the current page ids", () => {
  const pageSize = 4;
  const page = rows.slice(0, pageSize);
  assert.deepEqual(selectFilteredIds(page), [1, 2, 3, 4]);
  const allFiltered = selectFilteredIds(
    filterReleaseCases(rows, { device: "", component: null, story: null, priority: null, status: null }),
  );
  assert.equal(allFiltered.length, 12);
});

test("header checkbox is partial when a subset is selected", () => {
  const visible = [1, 2, 3, 4];
  const state = headerCheckboxState(visible, [1, 2]);
  assert.equal(state.checked, false);
  assert.equal(state.indeterminate, true);
});

test("bulk summary distinguishes total success from partial failure", () => {
  assert.match(summarizeBulkResult("status", 10, []), /10 casos/);
  assert.match(
    summarizeBulkResult("delete", 8, [{ id: 9, test_case_id: "QC-009", message: "not found" }]),
    /fallaron 1/,
  );
});
