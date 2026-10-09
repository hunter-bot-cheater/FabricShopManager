import assert from 'node:assert/strict'
import test from 'node:test'
import { recentDateRange } from '../src/dateRange.js'

test('seven-day range includes today and the previous six calendar days', () => {
  assert.deepEqual(recentDateRange(7, new Date(2026, 9, 9, 15, 30)), {
    start: '2026-10-03',
    end: '2026-10-09',
  })
})

test('recent range crosses month and year boundaries without UTC shifts', () => {
  assert.deepEqual(recentDateRange(7, new Date(2026, 0, 3, 12)), {
    start: '2025-12-28',
    end: '2026-01-03',
  })
})
