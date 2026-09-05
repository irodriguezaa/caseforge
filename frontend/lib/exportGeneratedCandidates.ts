import ExcelJS from "exceljs";
import { stripDeviceFromCaseName } from "@/lib/qcEffort";
import type { GeneratedCaseCandidate } from "@/lib/types";

export const CANDIDATE_EXPORT_HEADERS = [
  "ID",
  "Grupo Funcional",
  "Technical Epic",
  "Technical Story",
  "Caso de Prueba",
  "Tipo de Usuario",
  "Test Steps",
  "Resultado Esperado",
  "Datos de Prueba",
  "Prioridad",
  "Requiere Condición",
  "Evidencia",
  "Justificación",
  "Posible Duplicado",
  "Confianza",
  "Estado Revisión QC",
] as const;

const COLUMN_WIDTHS = [10, 22, 16, 16, 42, 16, 40, 40, 28, 12, 16, 24, 32, 20, 12, 18];
const HEADER_FILL = "1F4E78";
const HEADER_FONT = "FFFFFF";
const BORDER_COLOR = "BFBFBF";
const MAX_EVIDENCE_LINE = 180;

function cell(value: string | boolean | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "";
  }
  if (typeof value === "boolean") {
    return value ? "Sí" : "No";
  }
  return value;
}

function uniqueLines(parts: Array<string | null | undefined>): string {
  const seen = new Set<string>();
  const lines: string[] = [];
  for (const part of parts) {
    const trimmed = (part ?? "").trim();
    if (!trimmed || seen.has(trimmed)) {
      continue;
    }
    seen.add(trimmed);
    lines.push(trimmed);
  }
  return lines.join("\n");
}

function formatSteps(candidate: GeneratedCaseCandidate): string {
  return candidate.steps.map((step) => `${step.step_number}. ${step.action}`.trim()).join("\n");
}

function formatExpected(candidate: GeneratedCaseCandidate): string {
  return candidate.steps
    .map((step) => `${step.step_number}. ${step.expected_result}`.trim())
    .join("\n");
}

function formatTestData(candidate: GeneratedCaseCandidate): string {
  return uniqueLines([
    candidate.precondition,
    candidate.test_data,
    ...candidate.steps.map((step) => step.test_data),
  ]);
}

function formatEvidence(candidate: GeneratedCaseCandidate): string {
  const firstLine = (candidate.evidence ?? "").split(/\r?\n/, 1)[0]?.trim() ?? "";
  const compactPointer =
    firstLine.length > 0 && firstLine.length <= MAX_EVIDENCE_LINE ? firstLine : "";
  return uniqueLines([candidate.related_rn, compactPointer]);
}

function sequentialId(index: number): string {
  return `TC-${String(index + 1).padStart(3, "0")}`;
}

export function candidateToExportRow(
  candidate: GeneratedCaseCandidate,
  index: number,
): string[] {
  return [
    sequentialId(index),
    cell(candidate.related_functionality),
    cell(candidate.related_functionality),
    cell(candidate.related_jira),
    cell(stripDeviceFromCaseName(candidate.name, candidate.device)),
    cell(candidate.user_type),
    formatSteps(candidate),
    formatExpected(candidate),
    formatTestData(candidate),
    cell(
      candidate.priority === "BLOCKER"
        ? "Blocker"
        : candidate.priority === "CRITICAL"
          ? "Critical"
          : candidate.priority,
    ),
    cell(candidate.requires_condition),
    formatEvidence(candidate),
    cell(candidate.justification),
    cell(candidate.possible_duplicate_of),
    cell(candidate.confidence),
    "",
  ];
}

export function sanitizeExportFilenamePart(name: string): string {
  const cleaned = name
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, "_")
    .replace(/\s+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_|_$/g, "")
    .slice(0, 80);
  return cleaned || "Release";
}

function thinBorder(): Partial<ExcelJS.Borders> {
  const edge: Partial<ExcelJS.Border> = { style: "thin", color: { argb: BORDER_COLOR } };
  return { top: edge, left: edge, bottom: edge, right: edge };
}

function estimateRowHeight(values: string[]): number {
  const maxLines = Math.max(
    1,
    ...values.map((value) => value.split(/\r?\n/).length),
  );
  return Math.min(90, Math.max(22, 14 + maxLines * 13));
}

export async function buildCandidatesWorkbook(
  candidates: GeneratedCaseCandidate[],
): Promise<ExcelJS.Workbook> {
  const workbook = new ExcelJS.Workbook();
  workbook.creator = "CaseForge";
  const sheet = workbook.addWorksheet("Casos de Prueba", {
    views: [{ state: "frozen", ySplit: 1, showGridLines: true }],
  });

  sheet.columns = CANDIDATE_EXPORT_HEADERS.map((header, index) => ({
    header,
    width: COLUMN_WIDTHS[index],
  }));
  CANDIDATE_EXPORT_HEADERS.forEach((_, index) => {
    sheet.getColumn(index + 1).width = COLUMN_WIDTHS[index];
  });

  const headerRow = sheet.getRow(1);
  headerRow.height = 32;
  headerRow.eachCell((excelCell) => {
    excelCell.font = { name: "Calibri", size: 11, bold: true, color: { argb: HEADER_FONT } };
    excelCell.fill = {
      type: "pattern",
      pattern: "solid",
      fgColor: { argb: HEADER_FILL },
    };
    excelCell.alignment = { wrapText: true, vertical: "middle", horizontal: "center" };
    excelCell.border = thinBorder();
  });

  candidates.forEach((candidate, index) => {
    const values = candidateToExportRow(candidate, index);
    const row = sheet.addRow(values);
    row.height = estimateRowHeight(values);
    row.eachCell({ includeEmpty: true }, (excelCell, colNumber) => {
      excelCell.font = { name: "Calibri", size: 11 };
      excelCell.border = thinBorder();
      const longText = colNumber === 5 || colNumber === 7 || colNumber === 8 || colNumber === 9 || colNumber === 12 || colNumber === 13;
      excelCell.alignment = {
        wrapText: true,
        vertical: "top",
        horizontal: longText ? "left" : "center",
      };
    });
  });

  const lastRow = Math.max(1, candidates.length + 1);
  sheet.autoFilter = {
    from: { row: 1, column: 1 },
    to: { row: lastRow, column: CANDIDATE_EXPORT_HEADERS.length },
  };

  return workbook;
}

export async function downloadCandidatesExcel(
  candidates: GeneratedCaseCandidate[],
  releaseName: string,
): Promise<void> {
  const workbook = await buildCandidatesWorkbook(candidates);
  const filename = `CaseForge_${sanitizeExportFilenamePart(releaseName)}_Candidatos.xlsx`;
  const buffer = await workbook.xlsx.writeBuffer();
  const blob = new Blob([buffer], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  if (blob.size < 64) {
    throw new Error("El Excel exportado llegó vacío.");
  }
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
