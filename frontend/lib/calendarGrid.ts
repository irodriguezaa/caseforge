import type { QcCalendarEvent } from "@/lib/types";

export const HOUR_PX = 52;
export const START_HOUR = 8;
export const END_HOUR = 20;
export const WEEK_DAY_COUNT = 5;

export interface PlacedEvent {
  event: QcCalendarEvent;
  top: number;
  height: number;
  col: number;
  colCount: number;
  cancelled: boolean;
}

export function ymdLocal(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function parseYmd(value: string): Date {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, (month || 1) - 1, day || 1);
}

export function addDays(value: string, days: number): string {
  const date = parseYmd(value);
  date.setDate(date.getDate() + days);
  return ymdLocal(date);
}

export function mondayOf(value: string): string {
  const date = parseYmd(value);
  const weekday = (date.getDay() + 6) % 7;
  date.setDate(date.getDate() - weekday);
  return ymdLocal(date);
}

export function isCancelledTitle(title: string): boolean {
  return /^(cancelad[ao]|canceled)\s*:/i.test(title.trim());
}

export function isAllDayEvent(event: QcCalendarEvent): boolean {
  const start = new Date(event.start);
  const end = new Date(event.end);
  const hours = (end.getTime() - start.getTime()) / 3_600_000;
  if (hours >= 20) return true;
  return start.getHours() === 0 && start.getMinutes() === 0 && end.getHours() === 0 && end.getMinutes() === 0;
}

export function formatHourLabel(hour: number): string {
  if (hour === 0) return "12 a.m.";
  if (hour === 12) return "12 p.m.";
  if (hour < 12) return `${hour} a.m.`;
  return `${hour - 12} p.m.`;
}

export function formatWeekRange(weekStart: string): string {
  const start = parseYmd(weekStart);
  const end = parseYmd(addDays(weekStart, WEEK_DAY_COUNT - 1));
  const startMonth = start.toLocaleDateString("es-MX", { month: "long" });
  const endMonth = end.toLocaleDateString("es-MX", { month: "long" });
  const year = end.getFullYear();
  if (start.getMonth() === end.getMonth()) {
    return `${start.getDate()} – ${end.getDate()} de ${endMonth} de ${year}`;
  }
  return `${start.getDate()} de ${startMonth} – ${end.getDate()} de ${endMonth} de ${year}`;
}

export function formatDayHeading(value: string): string {
  const date = parseYmd(value);
  const weekday = date.toLocaleDateString("es-MX", { weekday: "short" }).replace(".", "");
  return `${weekday} ${date.getDate()}`;
}

export function formatLongDay(value: string): string {
  return parseYmd(value).toLocaleDateString("es-MX", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export function gmtOffsetLabel(date: Date): string {
  const offsetMin = -date.getTimezoneOffset();
  const sign = offsetMin >= 0 ? "+" : "-";
  const hours = Math.floor(Math.abs(offsetMin) / 60);
  return `GMT${sign}${hours}`;
}

function minutesFromStart(date: Date): number {
  return (date.getHours() - START_HOUR) * 60 + date.getMinutes();
}

export function placeTimedEvents(events: QcCalendarEvent[], dayYmd: string): PlacedEvent[] {
  const dayStart = parseYmd(dayYmd);
  const windowStart = new Date(dayStart);
  windowStart.setHours(START_HOUR, 0, 0, 0);
  const windowEnd = new Date(dayStart);
  windowEnd.setHours(END_HOUR - 1, 0, 0, 0);
  const timed = events
    .filter((event) => !isAllDayEvent(event))
    .map((event) => {
      const start = new Date(event.start);
      const end = new Date(event.end);
      return { event, start, end, startMs: start.getTime(), endMs: end.getTime() };
    })
    .filter((row) => Number.isFinite(row.startMs) && Number.isFinite(row.endMs))
    .filter((row) => row.endMs > windowStart.getTime() && row.startMs < windowEnd.getTime())
    .map((row) => {
      const clampedStart = row.start < windowStart ? windowStart : row.start;
      const clampedEnd = row.end > windowEnd ? windowEnd : row.end;
      return {
        ...row,
        start: clampedStart,
        end: clampedEnd,
        startMs: clampedStart.getTime(),
        endMs: Math.max(clampedEnd.getTime(), clampedStart.getTime() + 15 * 60_000),
      };
    })
    .sort((a, b) => a.startMs - b.startMs || a.endMs - b.endMs);

  const colByIndex = assignOverlapColumns(timed);
  const maxCols = Math.max(1, ...colByIndex.map((item) => item.colCount));

  return timed.map((row, index) => {
    const top = Math.max(0, (minutesFromStart(row.start) / 60) * HOUR_PX);
    const durationMin = (row.endMs - row.startMs) / 60_000;
    const maxHeight = (END_HOUR - START_HOUR) * HOUR_PX - top;
    const height = Math.min(maxHeight, Math.max(22, (durationMin / 60) * HOUR_PX));
    return {
      event: row.event,
      top,
      height,
      col: colByIndex[index]?.col ?? 0,
      colCount: colByIndex[index]?.colCount ?? maxCols,
      cancelled: isCancelledTitle(row.event.title),
    };
  });
}

function assignOverlapColumns(
  items: Array<{ startMs: number; endMs: number }>,
): Array<{ col: number; colCount: number }> {
  const result = items.map(() => ({ col: 0, colCount: 1 }));
  let clusterStart = 0;
  while (clusterStart < items.length) {
    let clusterEnd = clusterStart;
    let latest = items[clusterStart].endMs;
    for (let index = clusterStart + 1; index < items.length; index += 1) {
      if (items[index].startMs < latest) {
        latest = Math.max(latest, items[index].endMs);
        clusterEnd = index;
      } else {
        break;
      }
    }
    const colEnd: number[] = [];
    for (let index = clusterStart; index <= clusterEnd; index += 1) {
      let col = 0;
      while (col < colEnd.length && items[index].startMs < colEnd[col]) {
        col += 1;
      }
      if (col === colEnd.length) {
        colEnd.push(items[index].endMs);
      } else {
        colEnd[col] = items[index].endMs;
      }
      result[index].col = col;
    }
    const colCount = Math.max(1, colEnd.length);
    for (let index = clusterStart; index <= clusterEnd; index += 1) {
      result[index].colCount = colCount;
    }
    clusterStart = clusterEnd + 1;
  }
  return result;
}
