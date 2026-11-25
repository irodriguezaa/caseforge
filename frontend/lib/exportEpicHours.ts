import ExcelJS from "exceljs";
import { sanitizeExportFilenamePart } from "@/lib/exportGeneratedCandidates";
import { epicProgressEstado, rankEpicProgress, type EpicProgressRow } from "@/lib/qcEffort";

const HEADER_FILL = "1F4E78";
const HEADER_FONT = "FFFFFF";
const TOTAL_FILL = "E8F4F8";
const BORDER_COLOR = "BFBFBF";
const HOURS_BAR = "FF00C2D1";
const ADVANCE_BAR = "FF4F8EF7";
const TITLE = "Horas / Avance por Technical Epic";

const edge: Partial<ExcelJS.Border> = { style: "thin", color: { argb: BORDER_COLOR } };
const thinBorder: Partial<ExcelJS.Borders> = { top: edge, left: edge, bottom: edge, right: edge };

function roundHours(value: number): number {
  return Math.round(value * 10) / 10;
}

function advancePercent(executed: number, total: number): number {
  if (total === 0) {
    return 0;
  }
  return Math.round((executed * 1000) / total) / 10;
}

function paintCell(cell: ExcelJS.Cell, options: { bold?: boolean; fill?: string; align?: "left" | "center" | "right"; color?: string }): void {
  cell.font = { name: "Calibri", size: 11, bold: options.bold, color: options.color ? { argb: options.color } : undefined };
  cell.alignment = { vertical: "middle", horizontal: options.align ?? "center" };
  cell.border = thinBorder;
  if (options.fill) {
    cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: options.fill } };
  }
}

function dataBar(ref: string, color: string, max: number): ExcelJS.ConditionalFormattingOptions {
  return {
    ref,
    rules: [
      {
        type: "dataBar",
        gradient: false,
        showValue: true,
        cfvo: [
          { type: "num", value: 0 },
          { type: "num", value: max },
        ],
        color: { argb: color },
      } as unknown as ExcelJS.ConditionalFormattingRule,
    ],
  };
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, width: number, height: number, radius: number): void {
  const r = Math.min(radius, width / 2, height / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + width, y, x + width, y + height, r);
  ctx.arcTo(x + width, y + height, x, y + height, r);
  ctx.arcTo(x, y + height, x, y, r);
  ctx.arcTo(x, y, x + width, y, r);
  ctx.closePath();
  ctx.fill();
}

function chartPng(title: string, labels: string[], values: number[], max: number, color: string, suffix: string): string | null {
  if (typeof document === "undefined") {
    return null;
  }
  const width = 640;
  const rowHeight = 28;
  const height = 52 + Math.max(1, labels.length) * rowHeight + 12;
  const canvas = document.createElement("canvas");
  const scale = 2;
  canvas.width = width * scale;
  canvas.height = height * scale;
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    return null;
  }
  ctx.scale(scale, scale);
  ctx.fillStyle = "#F7FBFC";
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = "#D5E3EA";
  ctx.strokeRect(0.5, 0.5, width - 1, height - 1);
  ctx.fillStyle = "#1F4E78";
  ctx.font = "600 16px Calibri, Segoe UI, sans-serif";
  ctx.fillText(title, 16, 28);
  labels.forEach((label, index) => {
    const y = 44 + index * rowHeight;
    ctx.fillStyle = "#3D4A54";
    ctx.font = "12px Calibri, Segoe UI, sans-serif";
    const shown = label.length > 18 ? `${label.slice(0, 17)}…` : label;
    ctx.fillText(shown, 16, y + 16);
    const trackX = 168;
    const trackW = 360;
    ctx.fillStyle = "#E3EEF3";
    roundRect(ctx, trackX, y + 7, trackW, 10, 5);
    const portion = max <= 0 ? 0 : Math.max(0, values[index] / max);
    if (portion > 0) {
      ctx.fillStyle = color;
      roundRect(ctx, trackX, y + 7, Math.max(4, portion * trackW), 10, 5);
    }
    ctx.fillStyle = "#1F4E78";
    ctx.font = "600 12px Calibri, Segoe UI, sans-serif";
    ctx.fillText(`${values[index].toFixed(1)}${suffix}`, trackX + trackW + 12, y + 16);
  });
  const dataUrl = canvas.toDataURL("image/png");
  const encoded = dataUrl.split(",")[1];
  return encoded || null;
}

export async function buildEpicProgressWorkbook(rows: EpicProgressRow[], releaseName: string): Promise<ExcelJS.Workbook> {
  const ranked = rankEpicProgress(rows);
  const workbook = new ExcelJS.Workbook();
  workbook.creator = "CaseForge";
  workbook.title = TITLE;
  const sheet = workbook.addWorksheet("Horas y avance", {
    views: [{ state: "frozen", ySplit: 4, showGridLines: false }],
    pageSetup: { orientation: "landscape", fitToPage: true, fitToWidth: 1, fitToHeight: 0 },
  });
  sheet.columns = [
    { width: 18 },
    { width: 42 },
    { width: 12 },
    { width: 14 },
    { width: 14 },
    { width: 14 },
    { width: 16 },
  ];

  sheet.mergeCells("A1:G1");
  const title = sheet.getCell("A1");
  title.value = TITLE;
  title.font = { name: "Calibri", size: 18, bold: true, color: { argb: HEADER_FILL } };
  title.alignment = { vertical: "middle", horizontal: "left" };
  sheet.getRow(1).height = 28;

  sheet.mergeCells("A2:G2");
  const subtitle = sheet.getCell("A2");
  subtitle.value = releaseName;
  subtitle.font = { name: "Calibri", size: 12, color: { argb: "5B6770" } };
  subtitle.alignment = { vertical: "middle", horizontal: "left" };

  const headers = ["EPC", "Nombre", "Casos", "Horas", "Ejecutados", "Avance %", "Estado"];
  const headerRow = sheet.getRow(4);
  headerRow.height = 22;
  headers.forEach((header, index) => {
    const cell = headerRow.getCell(index + 1);
    cell.value = header;
    paintCell(cell, { bold: true, fill: HEADER_FILL, color: HEADER_FONT });
  });

  const firstData = 5;
  ranked.forEach((row, index) => {
    const excelRow = sheet.getRow(firstData + index);
    excelRow.height = row.name && row.name.length > 48 ? 32 : 20;
    const values: Array<string | number> = [
      row.key,
      row.name || "",
      row.total,
      row.hours,
      row.executed,
      row.percent,
      epicProgressEstado(row),
    ];
    values.forEach((value, column) => {
      const cell = excelRow.getCell(column + 1);
      cell.value = value;
      paintCell(cell, { align: column === 0 || column === 1 || column === 6 ? "left" : "right" });
      if (column === 1) {
        cell.alignment = { vertical: "middle", horizontal: "left", wrapText: true };
      }
      if (column === 3) {
        cell.numFmt = '0.0" h"';
      }
      if (column === 5) {
        cell.numFmt = '0.0"%"';
      }
    });
  });

  const totals = ranked.reduce(
    (acc, row) => ({ total: acc.total + row.total, executed: acc.executed + row.executed, hours: acc.hours + row.hours }),
    { total: 0, executed: 0, hours: 0 },
  );
  const totalRowNumber = firstData + ranked.length;
  const totalRow = sheet.getRow(totalRowNumber);
  totalRow.height = 22;
  const totalValues: Array<string | number> = [
    "Total",
    "",
    totals.total,
    roundHours(totals.hours),
    totals.executed,
    advancePercent(totals.executed, totals.total),
    "",
  ];
  totalValues.forEach((value, column) => {
    const cell = totalRow.getCell(column + 1);
    cell.value = value;
    paintCell(cell, { bold: true, fill: TOTAL_FILL, align: column === 0 || column === 1 ? "left" : "right" });
    if (column === 3) {
      cell.numFmt = '0.0" h"';
    }
    if (column === 5) {
      cell.numFmt = '0.0"%"';
    }
  });

  const lastData = firstData + ranked.length - 1;
  const maxHours = ranked.reduce((max, row) => Math.max(max, row.hours), 0);
  if (ranked.length > 0 && maxHours > 0) {
    sheet.addConditionalFormatting(dataBar(`D${firstData}:D${lastData}`, HOURS_BAR, maxHours));
  }
  if (ranked.length > 0) {
    sheet.addConditionalFormatting(dataBar(`F${firstData}:F${lastData}`, ADVANCE_BAR, 100));
  }

  const hoursChart = chartPng(
    "Horas por Technical Epic",
    ranked.map((row) => row.key),
    ranked.map((row) => row.hours),
    maxHours,
    "#00C2D1",
    " h",
  );
  const advanceChart = chartPng(
    "Avance por Technical Epic",
    ranked.map((row) => row.key),
    ranked.map((row) => row.percent),
    100,
    "#4F8EF7",
    "%",
  );
  const chartHeight = 52 + Math.max(1, ranked.length) * 28 + 12;
  if (hoursChart) {
    const imageId = workbook.addImage({ base64: hoursChart, extension: "png" });
    sheet.addImage(imageId, { tl: { col: 8, row: 3 }, ext: { width: 640, height: chartHeight } });
  }
  if (advanceChart) {
    const imageId = workbook.addImage({ base64: advanceChart, extension: "png" });
    const rowOffset = Math.ceil(chartHeight / 18) + 1;
    sheet.addImage(imageId, { tl: { col: 8, row: 3 + rowOffset }, ext: { width: 640, height: chartHeight } });
  }

  if (ranked.length > 0) {
    sheet.autoFilter = { from: { row: 4, column: 1 }, to: { row: lastData, column: 7 } };
  }
  return workbook;
}

export async function downloadEpicHoursExcel(rows: EpicProgressRow[], releaseName: string): Promise<void> {
  const workbook = await buildEpicProgressWorkbook(rows, releaseName);
  const filename = `CaseForge_${sanitizeExportFilenamePart(releaseName)}_Horas_Avance.xlsx`;
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
