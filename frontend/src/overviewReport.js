const DAILY_FIELDS = ['订单行数', '营业额', '利润']

export function dailyOverviewRows(reportRows, startDate, endDate) {
  const totalsByDate = new Map()
  for (const row of reportRows) {
    const totals = totalsByDate.get(row.日期) || Object.fromEntries(DAILY_FIELDS.map(field => [field, 0]))
    for (const field of DAILY_FIELDS) totals[field] += Number(row[field] || 0)
    totalsByDate.set(row.日期, totals)
  }

  const dates = []
  const date = new Date(`${startDate}T00:00:00`)
  const lastDate = new Date(`${endDate}T00:00:00`)
  while (date <= lastDate) {
    const key = [date.getFullYear(), String(date.getMonth() + 1).padStart(2, '0'),
      String(date.getDate()).padStart(2, '0')].join('-')
    const totals = totalsByDate.get(key) || Object.fromEntries(DAILY_FIELDS.map(field => [field, 0]))
    dates.push({ 日期: key, ...totals })
    date.setDate(date.getDate() + 1)
  }
  return dates
}
