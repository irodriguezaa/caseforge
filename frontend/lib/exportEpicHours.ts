import ExcelJS from "exceljs";
import { sanitizeExportFilenamePart } from "@/lib/exportGeneratedCandidates";

export async function downloadEpicHoursExcel(
  items: Array<{ label: string; value: number }>,
  releaseName: string,
): Promise<void> {
  const workbook = new ExcelJS.Workbook();
  const sheet = workbook.addWorksheet("Horas por EPC", {
    views: [{ state: "frozen", ySplit: 1 }],
  });
  sheet.columns = [
    { header: "Technical Epic", key: "label", width: 40 },
    { header: "Horas", key: "hours", width: 12 },
  ];
  for (const row of items) {
    sheet.addRow({ label: row.label, hours: row.value });
  }
  const filename = `CaseForge_${sanitizeExportFilenamePart(releaseName)}_Horas_EPC.xlsx`;
  const buffer = await workbook.xlsx.writeBuffer();
  const blob = new Blob([buffer], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
