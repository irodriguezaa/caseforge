/**
 * Calculates business days (Monday through Friday only) between startDateStr and endDateStr (inclusive).
 * Saturday and Sunday are excluded.
 * Expects dates in YYYY-MM-DD format.
 */
export function calculateBusinessDays(startDateStr: string, endDateStr: string): number {
  if (!startDateStr || !endDateStr) {
    return 0;
  }

  // Parse YYYY-MM-DD into UTC or local date components to avoid timezone shifting
  const [startYear, startMonth, startDay] = startDateStr.split("-").map(Number);
  const [endYear, endMonth, endDay] = endDateStr.split("-").map(Number);

  if (!startYear || !startMonth || !startDay || !endYear || !endMonth || !endDay) {
    return 0;
  }

  const start = new Date(startYear, startMonth - 1, startDay);
  const end = new Date(endYear, endMonth - 1, endDay);

  if (start > end) {
    return 0;
  }

  let businessDays = 0;
  const current = new Date(start);

  while (current <= end) {
    const dayOfWeek = current.getDay(); // 0 = Sunday, 6 = Saturday
    if (dayOfWeek !== 0 && dayOfWeek !== 6) {
      businessDays += 1;
    }
    current.setDate(current.getDate() + 1);
  }

  return businessDays;
}
