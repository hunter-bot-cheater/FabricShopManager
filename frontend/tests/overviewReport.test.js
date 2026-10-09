import assert from 'node:assert/strict'
import test from 'node:test'
import { dailyOverviewRows } from '../src/overviewReport.js'

test('homepage report aggregates turnover and profit by each date and fills empty days', () => {
  const result = dailyOverviewRows([
    { 日期: '2026-10-03', 订单行数: 2, 营业额: 30.5, 利润: 10.5 },
    { 日期: '2026-10-03', 订单行数: 1, 营业额: 12, 利润: 4 },
    { 日期: '2026-10-05', 订单行数: 3, 营业额: 60, 利润: 18 },
  ], '2026-10-03', '2026-10-05')

  assert.deepEqual(result, [
    { 日期: '2026-10-03', 订单行数: 3, 营业额: 42.5, 利润: 14.5 },
    { 日期: '2026-10-04', 订单行数: 0, 营业额: 0, 利润: 0 },
    { 日期: '2026-10-05', 订单行数: 3, 营业额: 60, 利润: 18 },
  ])
})
