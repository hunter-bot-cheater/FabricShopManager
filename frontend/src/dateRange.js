export function recentDateRange(days, endDate = new Date()) {
  const end = new Date(endDate.getFullYear(), endDate.getMonth(), endDate.getDate())
  const start = new Date(end)
  start.setDate(start.getDate() - days + 1)
  const format = date => [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, '0'),
    String(date.getDate()).padStart(2, '0'),
  ].join('-')
  return { start: format(start), end: format(end) }
}
