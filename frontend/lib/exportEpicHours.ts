import ExcelJS from "exceljs";
import type { EpicHoursGroup } from "@/lib/qcEffort";
import { estimateCaseMinutes } from "@/lib/qcEffort";

function caseHours(row: EpicHoursGroup["cases"][number]): number {
  if (row.estimation_hours != null && Number.isFinite(Number(row.estimation_hours))) {
    return Math.round(Number(row.estimation_hours) * 10) / 10;
  }
  return Math.round((estimateCaseMinutes(row.priority, row.complexity) / 60) * 10) / 10;
}

export async function exportEpicHoursWorkbook(
  groups: EpicHoursGroup[],
  downloadName: string,
): Promise<void> {
  const workbook = new ExcelJS.Workbook();
  const summary = workbook.addWorksheet("Por EPC");
  summary.columns = [
    { header: "EPC", key: "epc", width: 22 },
    { header: "Horas", key: "hours", width: 12 },
    { header: "Casos", key: "cases", width: 10 },
  ];
  for (const group of groups) {
    summary.addRow({ epc: group.key, hours: group.hours, cases: group.cases.length });
  }

  const detail = workbook.addWorksheet("Detalle");
  detail.columns = [
    { header: "EPC", key: "epc", width: 22 },
    { header: "ID", key: "id", width: 12 },
    { header: "Nombre", key: "name", width: 50 },
    { header: "Prioridad", key: "priority", width: 12 },
    { header: "Estado", key: "status", width: 14 },
    { header: "Horas", key: "hours", width: 12 },
  ];
  for (const group of groups) {
    for (const row of group.cases) {
      detail.addRow({
        epc: group.key,
        id: row.test_case_id,
        name: row.test_case_name,
        priority: row.priority || "",
        status: row.status || "",
        hours: caseHours(row),
      });
    }
  }

  const buffer = await workbook.xlsx.writeBuffer();
  const blob = new Blob([buffer], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = downloadName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
