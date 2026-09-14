/** Next QC-XXX label: highest existing QC/TC number in the release + 1, padded to 3 digits. */
const ID_NUMBER = /^(?:QC|TC)-(\d+)$/i;

export function nextTestCaseId(existingIds: string[]): string {
  let highest = 0;
  for (const label of existingIds) {
    const match = ID_NUMBER.exec((label || "").trim());
    if (match) {
      highest = Math.max(highest, Number(match[1]));
    }
  }
  return `QC-${String(highest + 1).padStart(3, "0")}`;
}
