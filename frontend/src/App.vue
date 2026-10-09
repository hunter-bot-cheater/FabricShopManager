<script setup>
import { computed, onMounted, onUpdated, reactive, ref, watch } from 'vue'
import DatePicker from './DatePicker.vue'
import FlowerSelect from './FlowerSelect.vue'
import VirtualTable from './VirtualTable.vue'
import { recentDateRange } from './dateRange.js'
import { dailyOverviewRows } from './overviewReport.js'
import {
  Activity, ArrowRight, ArrowUpRight, Boxes, CalendarDays,
  Check, CircleAlert, CircleCheck, CloudUpload,
  Database, FileSpreadsheet, Flower2, Gauge, LoaderCircle, Package,
  Plus, RefreshCw, Search, Settings2, ShieldCheck, ShoppingBag, SlidersHorizontal,
  Sparkles, TrendingUp, Truck, Wallet, X,
} from 'lucide-vue-next'

const menus = [
  { id: 'overview', label: '经营总览', icon: Gauge, group: '工作台' },
  { id: 'orders', label: '订单导入', icon: CloudUpload, group: '工作台' },
  { id: 'reports', label: '经营报表', icon: TrendingUp, group: '经营分析' },
  { id: 'inventory', label: '库存管理', icon: Boxes, group: '经营分析' },
  { id: 'products', label: '商品成本', icon: Flower2, group: '基础资料' },
  { id: 'settings', label: '系统设置', icon: Settings2, group: '基础资料' },
]

const page = ref('overview')
const system = reactive({ connected: false, initialized: false, message: '' })
const loading = ref(false)
const toast = ref('')
const sidebarWidth = ref(248)
const now = new Date()
const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
const startOfMonth = `${today.slice(0, 7)}-01`
const reportRange = reactive({ start: today, end: today, group: 'day' })
const dashboard = reactive({ weekReport: null, inventory: [], unmatched: [] })
const products = ref([])
const events = ref([])
const purchases = ref([])
const eventTotal = ref(0)
const purchaseTotal = ref(0)
const eventPage = ref(1)
const purchasePage = ref(1)
const eventSearch = ref('')
const purchaseSearch = ref('')
const eventSort = reactive({ by: 'created_at', order: 'desc' })
const purchaseSort = reactive({ by: 'received_date', order: 'desc' })
const unmatchedSort = reactive({ by: 'updated_at', order: 'desc' })
const ignoredSort = reactive({ by: 'updated_at', order: 'desc' })
const reportSort = reactive({ by: '', order: 'asc' })
const previewSort = reactive({ by: '', order: 'asc' })
const tablePageSize = 20
const recommendations = ref({ items: [] })
const unmatched = ref([])
const unmatchedTotal = ref(0)
const unmatchedOffset = ref(0)
const selectedUnmatched = ref([])
const ignored = ref([])
const ignoredTotal = ref(0)
const ignoredOffset = ref(0)
const ignoredVisible = ref(false)
const report = ref(null)
const refundReport = ref(null)
const inoutReport = ref(null)
const reportExportType = ref('daily')
const inventoryTab = ref('stock')
const stockAsOf = ref(today)
const selectedFile = ref(null)
const preview = ref(null)
const dragOver = ref(false)
const searchText = ref('')
const settings = reactive({
  mysql_host: '127.0.0.1', mysql_port: 3306, mysql_database: 'shop_data', mysql_user: 'root',
  mysql_password: '', has_password: false,
  output_daily: '', output_range: '', output_refund: '', output_inventory: '', output_inout: '',
  default_shipping_fee: 2.5,
  inventory_sales_window_days: 7, procurement_target_days: 14, procurement_batch_capacity_meters: 1350,
})
const settingsMessages = reactive({ database: '', paths: '', rules: '' })
const inventoryForm = reactive({ flower: '', operation: '采购入库', quantity: '', effective_date: today, reference: '' })
const productForm = reactive({ flower: '', cost_per_meter: '', roll_length_meters: 45, replenishment_days: 1, aliasesText: '' })
const editingFlower = ref('')
const editingAliases = ref([])
const aliasesDirty = ref(false)
const previewDirty = ref(false)
const allUnmatchedSelected = ref(false)
const excludedUnmatched = ref([])

const pageTitle = computed(() => menus.find(item => item.id === page.value)?.label || '经营总览')
const currentTimeLabel = computed(() => new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' }).format(now))
const overviewDateRange = computed(() => recentDateRange(7, now))
const overviewDailyRows = computed(() => dailyOverviewRows(
  dashboard.weekReport?.rows || [], overviewDateRange.value.start, overviewDateRange.value.end,
))
const filteredInventory = computed(() => dashboard.inventory.filter(item => !searchText.value || item.flower.includes(searchText.value)))
const filteredProducts = computed(() => products.value.filter(item => !searchText.value || item.flower.includes(searchText.value)))
const filteredReport = computed(() => {
  if (reportExportType.value === 'refund') return refundReport.value?.rows || []
  if (reportExportType.value === 'inout') return inoutReport.value?.rows || []
  const rows = report.value?.rows || []
  return reportExportType.value === 'daily' ? rows.filter(row => row.日期 === reportRange.start) : rows
})
const visibleReport = computed(() => filteredReport.value)
const reportVisibleTotals = computed(() => filteredReport.value.reduce((total, row) => {
  for (const key of ['订单行数', '米数', '营业额', '成本', '运费', '利润']) total[key] = (total[key] || 0) + Number(row[key] || 0)
  return total
}, {}))
const visibleRecommendations = computed(() => recommendations.value.items || [])
const unmatchedPage = computed(() => Math.floor(unmatchedOffset.value / 20) + 1)
const unmatchedPageCount = computed(() => Math.max(1, Math.ceil(unmatchedTotal.value / 20)))
const ignoredPage = computed(() => Math.floor(ignoredOffset.value / 20) + 1)
const ignoredPageCount = computed(() => Math.max(1, Math.ceil(ignoredTotal.value / 20)))
const unmatchedPages = computed(() => pageWindow(unmatchedPage.value, unmatchedPageCount.value))
const ignoredPages = computed(() => pageWindow(ignoredPage.value, ignoredPageCount.value))
const eventPageCount = computed(() => Math.max(1, Math.ceil(eventTotal.value / tablePageSize)))
const purchasePageCount = computed(() => Math.max(1, Math.ceil(purchaseTotal.value / tablePageSize)))
const activeProducts = computed(() => products.value.filter(item => item.active))
const selectedUnmatchedCount = computed(() => allUnmatchedSelected.value
  ? Math.max(0, unmatchedTotal.value - excludedUnmatched.value.length)
  : selectedUnmatched.value.length)
function previewSortValue(item, key) {
  if (key === 'order_no') return item.row.order_no || ''
  if (key === 'product') return `${item.row.product || ''} ${item.row.product_spec || ''}`
  if (key === 'flower') return item.suggested_flower || ''
  if (key === 'status') return `${item.row.order_status || ''} ${item.row.after_sale_status || ''}`
  if (key === 'order_date') return item.order_date || ''
  if (key === 'meters') return Number(item.meters || 0)
  if (key === 'stock_action') return Number(item.stock_effect_meters || 0)
  return item.needs_attention ? '待处理' : item.state
}
const orderedPreviewGroups = computed(() => {
  const groups = [
    { key: 'flower', label: '待处理：花型未匹配', rows: [] },
    { key: 'meters', label: '待处理：规格未识别米数', rows: [] },
    { key: 'other', label: '待处理：其他信息需核对', rows: [] },
    { key: 'ready', label: '可正常处理', rows: [] },
  ]
  for (const item of preview.value?.rows || []) {
    const key = !item.suggested_flower ? 'flower'
      : item.unit_meters <= 0 ? 'meters'
        : item.needs_attention ? 'other' : 'ready'
    groups.find(group => group.key === key).rows.push(item)
  }
  if (previewSort.by) for (const group of groups) group.rows.sort((left, right) => {
    const a = previewSortValue(left, previewSort.by)
    const b = previewSortValue(right, previewSort.by)
    const comparison = typeof a === 'number' && typeof b === 'number'
      ? a - b
      : String(a).localeCompare(String(b), 'zh-CN', { numeric: true, sensitivity: 'base' })
    return previewSort.order === 'asc' ? comparison : -comparison
  })
  return groups.filter(group => group.rows.length)
})
const previewEntries = computed(() => orderedPreviewGroups.value.flatMap(group => [
  { kind: 'group', key: `group:${group.key}`, group, height: 34 },
  ...group.rows.flatMap(item => {
    const key = `${item.row.order_no}-${item.row.line_key}`
    const rows = [{ kind: 'order', key: `order:${key}`, item, height: 64 }]
    if (item.showEditor) rows.push({ kind: 'editor', key: `editor:${key}`, item, height: 440 })
    return rows
  }),
]))
const reportEntries = computed(() => {
  const rows = [...visibleReport.value]
  const { by, order } = reportSort
  if (by) rows.sort((left, right) => {
    const a = left[by] ?? ''
    const b = right[by] ?? ''
    const comparison = typeof a === 'number' && typeof b === 'number'
      ? a - b
      : String(a).localeCompare(String(b), 'zh-CN', { numeric: true, sensitivity: 'base' })
    return order === 'asc' ? comparison : -comparison
  })
  return rows.map((row, index) => ({
  key: `report:${index}:${row.日期 || ''}:${row.花型 || ''}:${row.平台 || ''}`,
  row,
  height: 50,
  }))
})
const editableOrderFields = [
  ['order_no', '订单号', 'text'], ['parent_order_no', '主订单号', 'text'], ['product', '商品名称', 'text'],
  ['product_spec', '商品规格 / 米数', 'text'], ['product_id', '商品编码', 'text'],
  ['merchant_code_product', '商家商品编码', 'text'], ['merchant_code_spec', '商家规格编码', 'text'],
  ['flower', '标准花型', 'flower'],
  ['product_quantity', '商品数量', 'number'], ['merchant_income', '商家实收', 'number'],
  ['postage', '订单邮费', 'number'], ['product_total', '商品金额', 'number'], ['user_payment', '买家实付', 'number'],
  ['order_status', '订单状态', 'text'], ['after_sale_status', '售后状态', 'text'],
  ['payment_time', '付款时间', 'date'], ['order_time', '下单时间', 'date'],
  ['delivery_time', '发货时间', 'date'], ['receive_time', '签收时间', 'date'],
  ['express_company', '快递公司', 'text'], ['express_no', '快递单号', 'text'], ['merchant_remark', '商家备注', 'text'],
]

function pageWindow(current, total) {
  const count = Math.min(5, Math.max(1, total))
  const first = Math.max(1, Math.min(current - 2, total - count + 1))
  return Array.from({ length: count }, (_, index) => first + index)
}

function money(value) { return `¥${Number(value || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` }
function number(value, digits = 2) { return Number(value || 0).toLocaleString('zh-CN', { maximumFractionDigits: digits }) }
function percent(value) { return `${(Number(value || 0) * 100).toFixed(2)}%` }
function notify(message) {
  toast.value = message
  window.setTimeout(() => { if (toast.value === message) toast.value = '' }, 3600)
}
async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, options)
  const type = response.headers.get('content-type') || ''
  if (!response.ok) {
    const body = type.includes('json') ? await response.json() : { detail: await response.text() }
    throw new Error(body.detail || body.message || '请求失败')
  }
  return type.includes('json') ? response.json() : response
}
async function refreshStatus() {
  await loadSettings()
  try {
    Object.assign(system, await api('/system/status'))
  } catch (error) {
    system.connected = false
    system.message = error.message
  }
  if (system.connected && system.initialized) await loadWorkspace()
}
async function loadSettings() {
  try { Object.assign(settings, await api('/settings')) } catch { /* setup page will show connection status */ }
}
async function loadWorkspace() {
  loading.value = true
  try {
    const eventQuery = new URLSearchParams({ limit: tablePageSize, offset: (eventPage.value - 1) * tablePageSize,
      sort_by: eventSort.by, sort_order: eventSort.order, search: eventSearch.value })
    const purchaseQuery = new URLSearchParams({ limit: tablePageSize, offset: (purchasePage.value - 1) * tablePageSize,
      sort_by: purchaseSort.by, sort_order: purchaseSort.order, search: purchaseSearch.value })
    const unmatchedQuery = new URLSearchParams({ limit: 20, offset: unmatchedOffset.value,
      sort_by: unmatchedSort.by, sort_order: unmatchedSort.order })
    const [inventoryRows, productRows, eventRows, unmatchedRows, ignoredCount, purchaseRows, restock] = await Promise.all([
      api(`/inventory?as_of=${stockAsOf.value}`), api('/products'), api(`/inventory/events?${eventQuery}`),
      api(`/orders/unmatched?${unmatchedQuery}`),
      api('/orders/unmatched/ignored?limit=1'), api(`/inventory/purchases?${purchaseQuery}`), api('/inventory/recommendations'),
    ])
    dashboard.inventory = inventoryRows
    products.value = productRows
    events.value = eventRows.items
    eventTotal.value = eventRows.total
    unmatched.value = unmatchedRows.items
    unmatchedTotal.value = unmatchedRows.total
    ignoredTotal.value = ignoredCount.total
    purchases.value = purchaseRows.items
    purchaseTotal.value = purchaseRows.total
    recommendations.value = restock
    await loadOverviewReport()
  } catch (error) { notify(error.message) }
  finally { loading.value = false }
}
async function loadInventory() {
  try { dashboard.inventory = await api(`/inventory?as_of=${stockAsOf.value}`) }
  catch (error) { notify(error.message) }
}
watch(stockAsOf, () => { if (system.connected && system.initialized) loadInventory() })
async function loadPagedTable(kind) {
  if (kind === 'events') eventPage.value = Math.min(eventPage.value, eventPageCount.value)
  else purchasePage.value = Math.min(purchasePage.value, purchasePageCount.value)
  await loadWorkspace()
}
function sortServerTable(kind, key, header) {
  const state = ({ events: eventSort, purchases: purchaseSort, unmatched: unmatchedSort, ignored: ignoredSort })[kind]
  if (!state) return
  if (state.by === key) state.order = state.order === 'asc' ? 'desc' : 'asc'
  else { state.by = key; state.order = 'asc' }
  const table = header?.closest('table')
  table?.querySelectorAll('thead th').forEach(cell => {
    cell.classList.toggle('sort-active', cell === header)
    cell.removeAttribute('data-sort-order')
  })
  if (header) header.dataset.sortOrder = state.order === 'asc' ? '↑' : '↓'
  if (kind === 'events') { eventPage.value = 1; loadPagedTable(kind) }
  else if (kind === 'purchases') { purchasePage.value = 1; loadPagedTable(kind) }
  else if (kind === 'unmatched') { unmatchedOffset.value = 0; loadUnmatched() }
  else { ignoredOffset.value = 0; loadIgnored() }
}
function gotoTablePage(kind, pageNumber) {
  if (kind === 'events') eventPage.value = pageNumber
  else purchasePage.value = pageNumber
  loadPagedTable(kind)
}
async function loadReport() {
  if (reportRange.end < reportRange.start) {
    notify('结束日期不能早于开始日期')
    return
  }
  try {
    const query = `start_date=${reportRange.start}&end_date=${reportRange.end}`
    const [daily, refunds, inout] = await Promise.all([
      api(`/reports?${query}&group_by=day`), api(`/reports/refunds?${query}`), api(`/reports/inout?${query}`),
    ])
    report.value = daily
    refundReport.value = refunds
    inoutReport.value = inout
  } catch (error) { notify(error.message); return }
}
async function loadOverviewReport() {
  const { start, end } = overviewDateRange.value
  try {
    dashboard.weekReport = await api(`/reports?start_date=${start}&end_date=${end}&group_by=day`)
  } catch (error) { notify(error.message) }
}
async function initializeLegacy() {
  if (!window.confirm('将旧系统的商品成本、当前库存及订单状态复制到新系统基线。旧表不会被修改或删除。继续吗？')) return
  loading.value = true
  try {
    const result = await api('/system/initialize', { method: 'POST' })
    system.initialized = true
    notify(result.already_initialized ? '兼容基线已存在' : `基线已建立：${result.products} 个花型，${result.orders} 条历史订单`)
    await loadWorkspace()
  } catch (error) { notify(error.message) }
  finally { loading.value = false }
}
async function saveSettings(scope = 'general', silent = false) {
  try {
    const payload = { ...settings }
    delete payload.has_password
    delete payload.defaults
    if (!payload.mysql_password) delete payload.mysql_password
    const result = await api('/settings', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
    Object.assign(settings, result)
    settings.mysql_password = ''
    const messages = { database: '数据库配置已保存', paths: 'Excel 输出路径已保存', rules: '经营计算规则已保存' }
    if (scope in settingsMessages) settingsMessages[scope] = messages[scope]
    let refreshWarning = ''
    if (scope === 'rules' && system.connected && system.initialized) {
      try {
        const [inventoryRows, restock] = await Promise.all([
          api(`/inventory?as_of=${stockAsOf.value}`), api('/inventory/recommendations'),
        ])
        dashboard.inventory = inventoryRows
        recommendations.value = restock
      } catch (error) { refreshWarning = `规则已保存，但刷新库存建议失败：${error.message}` }
    }
    if (!silent) notify(refreshWarning || messages[scope] || '系统配置已保存')
    return true
  } catch (error) {
    const message = `保存失败：${error.message}`
    if (scope in settingsMessages) settingsMessages[scope] = message
    if (!silent) notify(message)
    return false
  }
}
async function testConnection() {
  try {
    if (!await saveSettings('database', true)) return
    const result = await api('/settings/test-connection', { method: 'POST' })
    settingsMessages.database = `连接成功 · MySQL ${result.version}`
    notify(settingsMessages.database)
    await refreshStatus()
  } catch (error) { settingsMessages.database = `连接测试失败：${error.message}`; notify(settingsMessages.database) }
}
async function chooseFolder(key) {
  if (!window.pywebview?.api?.choose_folder) {
    const entered = window.prompt('请填写文件夹完整路径', settings[key])
    if (entered !== null) { settings[key] = entered; notify('已更新路径，请点击“保存输出路径”保存') }
    return
  }
  const path = await window.pywebview.api.choose_folder()
  if (path) { settings[key] = path; notify('已选择输出目录，请点击“保存输出路径”保存') }
}
function openFilePicker() { document.querySelector('#order-file').click() }
function onFileChange(event) {
  const file = event.target.files?.[0] || null
  if (file && !/\.(xlsx|xls|csv)$/i.test(file.name)) { notify('仅支持 XLSX / XLS / CSV 格式'); event.target.value = ''; return }
  selectedFile.value = file
  preview.value = null
}
function onDrop(event) {
  dragOver.value = false
  const file = event.dataTransfer.files?.[0] || null
  if (file && !/\.(xlsx|xls|csv)$/i.test(file.name)) { notify('仅支持 XLSX / XLS / CSV 格式'); return }
  selectedFile.value = file
  preview.value = null
}
async function createPreview() {
  if (!selectedFile.value) return
  const body = new FormData()
  body.append('file', selectedFile.value)
  loading.value = true
  try {
    preview.value = await api('/orders/preview', { method: 'POST', body })
    previewDirty.value = false
    notify(`识别到 ${preview.value.total} 条订单行，请核对后确认导入`)
  } catch (error) { notify(error.message) }
  finally { loading.value = false }
}
function editPreviewField(item, field, value) {
  if (field === 'flower') item.flower = value
  else item.row[field] = value
  item.edited_fields[field] = value
  previewDirty.value = true
}
async function recalculatePreview() {
  if (!preview.value) return
  loading.value = true
  try {
    const edits = preview.value.rows.map((item, row_index) => ({ row_index, fields: item.edited_fields || {} }))
      .filter(edit => Object.keys(edit.fields).length)
    const result = await api('/orders/preview/recalculate', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: preview.value.token, edits }) })
    preview.value.rows = result.rows
    preview.value.counts = result.counts
    previewDirty.value = false
    notify('订单预览已重新计算，请复核米数和库存影响')
  } catch (error) { notify(error.message) }
  finally { loading.value = false }
}
async function commitPreview() {
  if (previewDirty.value) { notify('订单内容有修改，请先点击“重新计算预览”'); return }
  if (!preview.value || !window.confirm('确认导入？状态变化会立即写入库存流水；退款订单将自动回补。')) return
  loading.value = true
  try {
    const edits = preview.value.rows.map((item, row_index) => ({ row_index, fields: item.edited_fields || {} }))
      .filter(edit => Object.keys(edit.fields).length)
    const result = await api('/orders/commit', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: preview.value.token, edits }) })
    notify(`导入完成：${result.imported} 行，库存变更 ${result.stock_movements} 笔，未匹配 ${result.unmatched} 行`)
    preview.value = null
    previewDirty.value = false
    selectedFile.value = null
    document.querySelector('#order-file').value = ''
    await loadWorkspace()
  } catch (error) { notify(error.message) }
  finally { loading.value = false }
}
async function saveMovement() {
  try {
    const purchase = inventoryForm.operation === '采购入库'
    const payload = purchase
      ? { flower: inventoryForm.flower, roll_count: Number(inventoryForm.quantity), received_date: inventoryForm.effective_date, reference: inventoryForm.reference }
      : { ...inventoryForm, quantity: Number(inventoryForm.quantity) }
    const result = await api(purchase ? '/inventory/receipts' : '/inventory/movements', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    })
    notify(purchase
      ? `${result.flower} 已登记到货 ${result.roll_count} 卷，共 ${number(result.meters)} 米`
      : `${result.flower} ${result.operation}已登记 · 库存 ${number(result.before_stock)} → ${number(result.after_stock)}${result.warning ? ` · ${result.warning}` : ''}`)
    inventoryForm.quantity = ''
    inventoryForm.reference = ''
    await loadWorkspace()
  } catch (error) { notify(error.message) }
}
function clearProductForm() {
  editingFlower.value = ''
  editingAliases.value = []
  aliasesDirty.value = false
  Object.assign(productForm, { flower: '', cost_per_meter: '', roll_length_meters: '45', replenishment_days: '1', aliasesText: '' })
}
function selectProductFlower(item) {
  editingFlower.value = item.flower
  Object.assign(productForm, { flower: item.flower, cost_per_meter: String(item.cost_per_meter),
    roll_length_meters: String(item.roll_length_meters || 45), replenishment_days: String(item.replenishment_days || 1), aliasesText: '' })
  editingAliases.value = [...(item.aliases || [])]
  aliasesDirty.value = false
}
function editProduct(item) {
  selectProductFlower(item)
  window.scrollTo({ top: 0, behavior: 'smooth' })
}
function removeEditingAlias(alias) {
  editingAliases.value = editingAliases.value.filter(value => value !== alias)
  aliasesDirty.value = true
}
async function saveProduct() {
  const flower = productForm.flower.trim()
  const cost = String(productForm.cost_per_meter).trim()
  const roll = String(productForm.roll_length_meters).trim()
  const lead = String(productForm.replenishment_days).trim()
  if (!editingFlower.value && !flower) { notify('请选择或输入标准花型名'); return }
  if (cost && !/^\d+(?:\.\d{1,2})?$/.test(cost)) { notify('成本单价须为非负数，最多两位小数'); return }
  if (roll && !/^[1-9]\d*$/.test(roll)) { notify('每卷米数必须是正整数'); return }
  if (lead && !/^[1-9]\d*$/.test(lead)) { notify('预计到店天数必须是正整数'); return }
  if (!editingFlower.value && !cost) { notify('请填写成本单价'); return }
  const aliasesEntered = productForm.aliasesText.split(/[，,、]/).map(value => value.trim()).filter(Boolean)
  const payload = {}
  if (flower) payload.flower = flower
  if (cost) payload.cost_per_meter = Number(cost)
  if (roll) payload.roll_length_meters = Number(roll)
  if (lead) payload.replenishment_days = Number(lead)
  if (!editingFlower.value || aliasesDirty.value || aliasesEntered.length) {
    payload.aliases = [...new Set([...editingAliases.value, ...aliasesEntered])]
  }
  if (!editingFlower.value) {
    payload.roll_length_meters ??= 45
    payload.replenishment_days ??= 1
  }
  try {
    const options = { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }
    if (editingFlower.value) {
      await api(`/products/${encodeURIComponent(editingFlower.value)}`, { ...options, method: 'PUT' })
      notify('花型、成本及别名已更新；可重新匹配历史待匹配订单')
    } else {
      await api('/products', { ...options, method: 'POST' })
      notify('商品成本已保存')
    }
    clearProductForm()
    await loadWorkspace()
  } catch (error) { notify(error.message) }
}
async function rematchUnmatched() {
  try {
    const result = await api('/orders/unmatched/rematch', { method: 'POST' })
    notify(`重新匹配完成：${result.matched} 行已匹配，仍有 ${result.unmatched} 行待处理`)
    await loadWorkspace()
  } catch (error) { notify(error.message) }
}
async function archiveProduct(item) {
  const action = item.active ? '停用' : '恢复'
  if (!window.confirm(`${action}“${item.flower}”？停用会保留历史订单、库存和流水，可随时恢复。`)) return
  try {
    if (item.active) {
      await api(`/products/${encodeURIComponent(item.flower)}`, { method: 'DELETE' })
      notify('花型已停用，历史记录已保留')
    } else {
      await api('/products', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ flower: item.flower, cost_per_meter: Number(item.cost_per_meter),
          roll_length_meters: Number(item.roll_length_meters || 45), replenishment_days: Number(item.replenishment_days || 1) }) })
      notify('花型已恢复')
    }
    await loadWorkspace()
  } catch (error) { notify(error.message) }
}
async function exportReport(kind) {
  try {
    const endDate = kind === 'daily' ? reportRange.start : reportRange.end
    const response = await api(`/reports/export?start_date=${reportRange.start}&end_date=${endDate}&kind=${kind}`)
    notify(`Excel 已保存至：${response.path}`)
  } catch (error) { notify(error.message) }
}
async function exportInoutReport() {
  try {
    const response = await api(`/reports/inout-export?start_date=${reportRange.start}&end_date=${reportRange.end}`)
    notify(`出库入库明细已保存至：${response.path}`)
  } catch (error) { notify(error.message) }
}
async function exportRefundReport() {
  try {
    const response = await api(`/reports/refunds/export?start_date=${reportRange.start}&end_date=${reportRange.end}`)
    notify(`退款明细已保存至：${response.path}`)
  } catch (error) { notify(error.message) }
}
async function exportSelectedReport() {
  if (reportExportType.value === 'inout') return exportInoutReport()
  if (reportExportType.value === 'refund') return exportRefundReport()
  if (reportExportType.value === 'daily') return exportReport('daily')
  return exportReport('range')
}
function setReportType(type) { reportExportType.value = type }
async function loadIgnored() {
  try {
    const query = new URLSearchParams({ limit: 20, offset: ignoredOffset.value,
      sort_by: ignoredSort.by, sort_order: ignoredSort.order })
    const result = await api(`/orders/unmatched/ignored?${query}`)
    ignored.value = result.items
    ignoredTotal.value = result.total
  } catch (error) { notify(error.message) }
}
async function loadUnmatched() {
  try {
    const query = new URLSearchParams({ limit: 20, offset: unmatchedOffset.value,
      sort_by: unmatchedSort.by, sort_order: unmatchedSort.order })
    const result = await api(`/orders/unmatched?${query}`)
    unmatched.value = result.items
    unmatchedTotal.value = result.total
  } catch (error) { notify(error.message) }
}
async function gotoUnmatchedPage(pageNumber) {
  unmatchedOffset.value = (pageNumber - 1) * 20
  selectedUnmatched.value = []
  await loadWorkspace()
}
async function gotoIgnoredPage(pageNumber) {
  ignoredOffset.value = (pageNumber - 1) * 20
  await loadIgnored()
}
async function toggleIgnored() {
  ignoredVisible.value = !ignoredVisible.value
  if (ignoredVisible.value) await loadIgnored()
}
function toggleAllUnmatched() {
  allUnmatchedSelected.value = !allUnmatchedSelected.value
  excludedUnmatched.value = []
  selectedUnmatched.value = []
}
function toggleUnmatchedSelection(id, checked) {
  if (allUnmatchedSelected.value) {
    excludedUnmatched.value = checked ? excludedUnmatched.value.filter(value => value !== id)
      : [...new Set([...excludedUnmatched.value, id])]
  } else {
    selectedUnmatched.value = checked ? [...new Set([...selectedUnmatched.value, id])]
      : selectedUnmatched.value.filter(value => value !== id)
  }
}
async function ignoreSelected() {
  if (!selectedUnmatchedCount.value) return
  try {
    const ignoredNow = selectedUnmatchedCount.value
    await api('/orders/unmatched/ignore', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ all: allUnmatchedSelected.value, order_ids: selectedUnmatched.value,
        exclude_order_ids: excludedUnmatched.value }) })
    allUnmatchedSelected.value = false
    excludedUnmatched.value = []
    selectedUnmatched.value = []
    const nextTotal = unmatchedTotal.value - ignoredNow
    if (unmatchedOffset.value >= nextTotal && unmatchedOffset.value > 0) unmatchedOffset.value = Math.max(0, Math.floor((nextTotal - 1) / 20) * 20)
    await loadWorkspace()
    if (ignoredVisible.value) await loadIgnored()
    notify('已忽略所选待匹配订单')
  } catch (error) { notify(error.message) }
}
async function restoreIgnored(item) {
  try {
    await api('/orders/unmatched/restore', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ order_ids: [item.id] }) })
    if (ignoredOffset.value >= ignoredTotal.value - 1 && ignoredOffset.value > 0) ignoredOffset.value = Math.max(0, ignoredOffset.value - 20)
    await loadWorkspace()
    await loadIgnored()
    notify('订单已恢复到待匹配列表')
  } catch (error) { notify(error.message) }
}
function sortTableRows(table, column, header) {
  const rows = [...table.tBodies[0].rows].filter(row => !row.querySelector('.empty-cell'))
  const direction = table.dataset.sortColumn === String(column) && table.dataset.sortDirection === 'asc' ? 'desc' : 'asc'
  table.dataset.sortColumn = String(column)
  table.dataset.sortDirection = direction
  table.querySelectorAll('thead th').forEach(cell => { cell.classList.remove('sort-active'); cell.removeAttribute('data-sort-order') })
  header.classList.add('sort-active')
  header.dataset.sortOrder = direction === 'asc' ? '↑' : '↓'
  const value = row => row.cells[column]?.textContent.trim() || ''
  rows.sort((a, b) => {
    const normalize = text => text.replace(/[¥￥,\s]/g, '').replace(/(?:米|m|件|卷|天|种)$/i, '')
    const left = normalize(value(a))
    const right = normalize(value(b))
    const numeric = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/
    const bothNumeric = numeric.test(left) && numeric.test(right)
    const leftNumber = bothNumeric ? Number(left) : 0
    const rightNumber = bothNumeric ? Number(right) : 0
    const longIdentifier = bothNumeric && /^\d{16,}$/.test(left) && /^\d{16,}$/.test(right)
    const order = longIdentifier
      ? left.localeCompare(right, 'zh-CN', { numeric: true })
      : bothNumeric ? leftNumber - rightNumber : left.localeCompare(right, 'zh-CN', { numeric: true, sensitivity: 'base' })
    return direction === 'asc' ? order : -order
  })
  rows.forEach(row => table.tBodies[0].appendChild(row))
}
function handleTableSort(event) {
  const header = event.target.closest('th')
  if (!header || header.classList.contains('no-sort')) return
  const table = header.closest('table')
  if (header.closest('.preview-table') && header.dataset.sortKey) {
    const key = header.dataset.sortKey
    if (previewSort.by === key) previewSort.order = previewSort.order === 'asc' ? 'desc' : 'asc'
    else { previewSort.by = key; previewSort.order = 'asc' }
    table?.querySelectorAll('thead th').forEach(cell => {
      cell.classList.toggle('sort-active', cell === header)
      cell.removeAttribute('data-sort-order')
    })
    header.dataset.sortOrder = previewSort.order === 'asc' ? '↑' : '↓'
    return
  }
  if (header.closest('.report-virtual-table') && header.dataset.sortKey) {
    const key = header.dataset.sortKey
    if (reportSort.by === key) reportSort.order = reportSort.order === 'asc' ? 'desc' : 'asc'
    else { reportSort.by = key; reportSort.order = 'asc' }
    table?.querySelectorAll('thead th').forEach(cell => {
      cell.classList.toggle('sort-active', cell === header)
      cell.removeAttribute('data-sort-order')
    })
    header.dataset.sortOrder = reportSort.order === 'asc' ? '↑' : '↓'
    return
  }
  if (table?.dataset.serverSort && header.dataset.sortKey) {
    sortServerTable(table.dataset.serverSort, header.dataset.sortKey, header)
    return
  }
  const rows = [...header.closest('thead').rows]
  const occupied = []
  let index = -1
  for (let rowIndex = 0; rowIndex < rows.length && index < 0; rowIndex += 1) {
    occupied[rowIndex] ||= []
    let column = 0
    for (const cell of rows[rowIndex].cells) {
      while (occupied[rowIndex][column]) column += 1
      const start = column
      const rowSpan = cell.rowSpan || 1
      const colSpan = cell.colSpan || 1
      for (let row = rowIndex; row < Math.min(rows.length, rowIndex + rowSpan); row += 1) {
        occupied[row] ||= []
        for (let col = start; col < start + colSpan; col += 1) occupied[row][col] = true
      }
      if (cell === header) { index = start; break }
      column += colSpan
    }
  }
  if (table?.tBodies.length && index >= 0) sortTableRows(table, index, header)
}
function markActionColumns() {
  document.querySelectorAll('table').forEach(table => {
    const headers = table.querySelectorAll('thead th')
    headers.forEach((header, index) => {
      if ([...table.tBodies].some(body => [...body.rows].some(row => row.cells[index]?.querySelector('.row-actions')))) {
        header.classList.add('no-sort')
      }
      if (header.textContent.trim() === '操作') header.classList.add('no-sort')
    })
  })
}
onUpdated(markActionColumns)
async function exportInventory() {
  try {
    const response = await api('/inventory/export')
    notify(`库存明细已保存至：${response.path}`)
  } catch (error) { notify(error.message) }
}
function startSidebarResize(event) {
  if (event.button !== 0) return
  event.preventDefault()
  document.body.classList.add('resizing-sidebar')
  const move = pointer => { sidebarWidth.value = Math.max(210, Math.min(360, pointer.clientX)) }
  const stop = () => {
    document.body.classList.remove('resizing-sidebar')
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', stop)
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', stop, { once: true })
}
function selectMenu(id) {
  page.value = id
  searchText.value = ''
  if (id === 'reports' && system.initialized) loadReport()
  if (id === 'overview' && system.initialized) loadOverviewReport()
}

onMounted(() => {
  markActionColumns()
  refreshStatus()
})
</script>

<template>
  <div class="app-shell" :style="{ '--sidebar-width': `${sidebarWidth}px` }" @click.capture="handleTableSort">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark"><Flower2 :size="21" /></div>
        <div><strong>布店经营台</strong><span>FABRIC BUSINESS DESK</span></div>
      </div>
      <div class="side-shop"><div class="shop-avatar">布</div><div><b>我的店铺</b><small>个人经营空间</small></div></div>
      <div v-for="group in [...new Set(menus.map(item => item.group))]" :key="group" class="nav-group">
        <div class="nav-label">{{ group }}</div>
        <button v-for="item in menus.filter(menu => menu.group === group)" :key="item.id"
          class="nav-item" :class="{ active: page === item.id }" @click="selectMenu(item.id)">
          <component :is="item.icon" :size="18" :stroke-width="1.8" />
          <span>{{ item.label }}</span>
          <span v-if="item.id === 'orders' && unmatchedTotal" class="nav-count">{{ unmatchedTotal }}</span>
        </button>
      </div>
      <div class="sidebar-bottom">
        <div class="privacy-card"><ShieldCheck :size="17"/><div><b>本地私有运行</b><span>数据保存在自己的数据库</span></div></div>
        <div class="profile-button"><div class="profile-avatar">我</div><span><b>店铺管理员</b><small>独立管理</small></span></div>
      </div>
    </aside>
    <div class="sidebar-resizer" role="separator" aria-orientation="vertical" aria-label="拖动调整导航栏宽度" @pointerdown="startSidebarResize"></div>

    <main class="main-area">
      <header class="topbar">
        <div class="breadcrumbs"><strong>{{ pageTitle }}</strong></div>
        <div class="top-actions">
          <div class="date-pill"><CalendarDays :size="16"/>{{ currentTimeLabel }}</div>
          <button class="icon-button" title="刷新" @click="refreshStatus"><RefreshCw :size="17"/></button>
          <button class="avatar-button" title="系统设置" @click="selectMenu('settings')">我</button>
        </div>
      </header>

      <section v-if="!system.connected" class="setup-banner danger-banner">
        <div class="banner-icon"><Database :size="20"/></div><div class="banner-copy"><b>还没有连接到 MySQL 数据库</b><span>先在系统设置中填写数据库连接信息，测试通过后即可开始初始化。</span><small v-if="system.message">连接诊断：{{ system.message }}</small></div>
        <button class="button button-dark" @click="selectMenu('settings')">前往设置 <ArrowRight :size="15"/></button>
      </section>
      <section v-else-if="!system.initialized" class="setup-banner">
        <div class="banner-icon"><Sparkles :size="20"/></div><div class="banner-copy"><b>欢迎使用新经营台 · 建立旧数据兼容基线</b><span>将旧系统商品成本、当前库存和历史订单状态复制进新表；不会修改旧表。</span></div>
        <button class="button button-dark" :disabled="loading" @click="initializeLegacy">{{ loading ? '处理中…' : '安全初始化' }} <ArrowRight :size="15"/></button>
      </section>

      <div v-if="page === 'overview'" class="page-content">
        <div class="page-heading"><div><div class="eyebrow">OVERVIEW <span class="eyebrow-dot"></span> {{ currentTimeLabel }}</div><h1>经营总览</h1><p>今日营业额、近 7 天利润与库存，一眼掌握。</p></div></div>
        <template v-if="system.initialized">
          <div class="metric-grid">
            <article class="metric-card"><div class="metric-top"><span>近 7 天营业额</span><div class="metric-icon coral"><Wallet :size="18"/></div></div><div class="metric-value">{{ money(dashboard.weekReport?.totals?.营业额) }}</div><div class="metric-foot"><span class="metric-muted">{{ overviewDateRange.start }} 至 {{ overviewDateRange.end }}</span><span class="metric-link" @click="selectMenu('reports')">查看报表 <ArrowUpRight :size="13"/></span></div></article>
            <article class="metric-card"><div class="metric-top"><span>近 7 天利润</span><div class="metric-icon green"><TrendingUp :size="18"/></div></div><div class="metric-value green-text">{{ money(dashboard.weekReport?.totals?.利润) }}</div><div class="metric-foot"><span class="metric-muted">{{ overviewDateRange.start }} 至 {{ overviewDateRange.end }}</span><span class="pill positive"><ArrowUpRight :size="13"/> 实时计算</span></div></article>
            <article class="metric-card"><div class="metric-top"><span>在售花型</span><div class="metric-icon purple"><Flower2 :size="18"/></div></div><div class="metric-value">{{ products.filter(item => item.active).length }}<small> 种</small></div><div class="metric-foot"><span class="metric-muted">商品成本档案</span><span class="metric-link" @click="selectMenu('products')">管理商品 <ArrowUpRight :size="13"/></span></div></article>
            <article class="metric-card clickable-metric" role="button" tabindex="0" @click="selectMenu('orders')" @keydown.enter="selectMenu('orders')"><div class="metric-top"><span>待处理匹配</span><div class="metric-icon amber"><CircleAlert :size="18"/></div></div><div class="metric-value">{{ unmatchedTotal }}<small> 行</small></div><div class="metric-foot"><span class="metric-muted">不计入库存和日报</span><span class="metric-link">{{ unmatchedTotal ? '前往处理' : '全部已匹配' }} <ArrowUpRight :size="13"/></span></div></article>
          </div>
          <div class="content-grid overview-grid">
            <section class="panel panel-large"><div class="panel-head"><div><h2>近 7 天每日经营汇总</h2><p>{{ overviewDateRange.start }} 至 {{ overviewDateRange.end }} · 每天的营业额和利润</p></div><button class="text-button" @click="selectMenu('reports')">完整报表 <ArrowRight :size="14"/></button></div>
              <div v-if="dashboard.weekReport" class="table-wrap"><table><thead><tr><th>日期</th><th>有效订单行</th><th>营业额</th><th class="align-right">利润</th></tr></thead><tbody><tr v-for="row in overviewDailyRows" :key="row.日期"><td>{{ row.日期 }}</td><td>{{ row.订单行数 }}</td><td>{{ money(row.营业额) }}</td><td class="align-right"><b class="profit-amount">{{ money(row.利润) }}</b></td></tr></tbody><tfoot><tr><td><b>近 7 天合计</b></td><td>{{ dashboard.weekReport.totals?.订单行数 || 0 }}</td><td><b>{{ money(dashboard.weekReport.totals?.营业额) }}</b></td><td class="align-right"><b class="profit-amount">{{ money(dashboard.weekReport.totals?.利润) }}</b></td></tr></tfoot></table></div>
              <div v-else class="empty-state"><div class="empty-icon"><ShoppingBag :size="22"/></div><b>暂时无法获取近 7 天经营数据</b><span>检查数据库连接后刷新页面。</span></div>
            </section>
            <section class="panel inventory-peek"><div class="panel-head"><div><h2>库存概况</h2><p>当前可用库存 · 单位：米</p></div><button class="icon-button small" @click="selectMenu('inventory')"><ArrowUpRight :size="15"/></button></div>
              <div v-if="dashboard.inventory.length" class="stock-peek-list"><div v-for="item in dashboard.inventory" :key="item.flower" class="stock-peek-row"><div class="flower-dot">{{ item.flower.slice(0, 1) }}</div><div class="stock-name"><b>{{ item.flower }}</b><span>成本 {{ money(item.cost_per_meter) }}/米</span></div><div class="stock-value" :class="{ 'low-stock': item.low_stock }"><b>{{ number(item.current_stock) }}</b><small>米</small></div></div></div>
              <div v-else class="empty-state compact"><span>连接并完成基线初始化后显示库存</span></div>
              <button class="inventory-footer" @click="selectMenu('inventory')">管理库存与流水 <ArrowRight :size="14"/></button>
            </section>
          </div>
        </template>
      </div>

      <div v-else-if="page === 'orders'" class="page-content">
        <div class="page-heading"><div><div class="eyebrow">ORDER CENTER <span class="eyebrow-dot"></span> 订单自动入库</div><h1>订单导入</h1><p>支持拼多多、淘宝、抖音订单表。导入后按订单状态自动维护库存。</p></div><div class="status-chip"><span></span> 库存联动已开启</div></div>
        <div class="content-grid import-grid">
          <section class="panel upload-panel"><div class="panel-head"><div><h2>上传订单文件</h2><p>可重复导入；相同订单不会重复扣库存。</p></div><div class="step-badge">01 <span>/</span> 02</div></div>
            <div class="drop-zone" :class="{ 'drop-active': dragOver, 'has-file': selectedFile }" @click="openFilePicker" @dragover.prevent="dragOver = true" @dragleave.prevent="dragOver = false" @drop.prevent="onDrop">
              <input id="order-file" type="file" accept=".xlsx,.xls,.csv" hidden @change="onFileChange" />
              <div v-if="!selectedFile" class="upload-art"><CloudUpload :size="27"/></div><div v-else class="upload-art file-art"><FileSpreadsheet :size="25"/></div>
              <b>{{ selectedFile ? selectedFile.name : '将订单文件拖到这里' }}</b><span>{{ selectedFile ? `${(selectedFile.size / 1024).toFixed(1)} KB · 点击可重新选择` : '或者点击选择文件，支持 XLSX / XLS / CSV 格式' }}</span>
              <button class="button button-outline" type="button" @click.stop="openFilePicker">{{ selectedFile ? '重新选择' : '选择文件' }}</button>
            </div>
            <div class="import-notes"><div><Check :size="15"/><span>支持三平台订单格式自动识别</span></div><div><Check :size="15"/><span>每次导入先预览匹配与库存变更</span></div><div><Check :size="15"/><span>退款状态变更自动回补库存</span></div></div>
            <div class="panel-actions"><button class="button button-primary" :disabled="!selectedFile || loading || !system.initialized" @click="createPreview"><LoaderCircle v-if="loading" class="spin" :size="16"/><Search v-else :size="16"/> 解析并预览</button><span class="muted-note">{{ system.initialized ? '确认导入后立即更新库存' : '请先完成系统初始化' }}</span></div>
          </section>
          <section class="panel rule-panel"><div class="panel-head"><div><h2>自动处理规则</h2><p>规则在每次导入时生效</p></div><div class="rule-icon"><Activity :size="18"/></div></div>
            <div class="rule-list"><div class="rule-row"><div class="rule-index">01</div><div><b>首次导入为已发货</b><span>按规格米数与数量扣减对应花型库存。</span></div></div><div class="rule-row"><div class="rule-index">02</div><div><b>后续更新为退款成功</b><span>自动回补库存；生效日记录为首次观察到退款的导入日。</span></div></div><div class="rule-row"><div class="rule-index">03</div><div><b>首次导入已退款</b><span>不扣库存，也不计入日报利润。</span></div></div><div class="rule-row"><div class="rule-index">04</div><div><b>花型暂未匹配</b><span>清晰提示并保留订单；匹配后重新导入即可处理。</span></div></div></div>
          </section>
        </div>
        <section v-if="preview" class="panel preview-panel"><div class="panel-head"><div><div class="eyebrow">IMPORT PREVIEW · {{ preview.platform_name }}</div><h2>导入预览</h2><p>以下状态变更在确认后才会写入数据库和库存流水。</p></div><div class="step-badge">02 <span>/</span> 02</div></div>
          <div class="preview-stats"><div><b>{{ preview.total }}</b><span>订单行</span></div><div><b>{{ preview.counts.new }}</b><span>新增</span></div><div><b>{{ preview.counts.changed }}</b><span>状态变化</span></div><div class="warn-stat"><b>{{ preview.counts.unmatched }}</b><span>待处理</span></div><div><b>{{ preview.counts.refund }}</b><span>退款状态</span></div></div>
          <div v-if="previewDirty" class="preview-edit-warning"><CircleAlert :size="15"/> 订单字段已修改；先重新计算预览，确认米数和库存动作后再导入。</div>
          <VirtualTable class="preview-table" :items="previewEntries" :columns="8" :column-widths="['14%', '22%', '11%', '15%', '10%', '8%', '10%', '10%']" :row-height="64" :max-height="360">
            <template #header><tr><th data-sort-key="order_no">订单号</th><th data-sort-key="product">商品 / 规格</th><th data-sort-key="flower">花型匹配</th><th data-sort-key="status">源订单状态</th><th data-sort-key="order_date">业务日期</th><th data-sort-key="meters">购买米数</th><th data-sort-key="stock_action">库存动作</th><th data-sort-key="handling">处理情况</th></tr></template>
            <template #row="{ item: entry }">
              <tr v-if="entry.kind === 'group'" class="preview-group-heading" :class="{ 'preview-group-ready': entry.group.key === 'ready' }"><td colspan="8"><b>{{ entry.group.label }}</b><span>{{ entry.group.rows.length }} 行</span></td></tr>
              <tr v-else-if="entry.kind === 'order'" class="preview-data-row" :class="{ 'attention-row': entry.item.needs_attention }">
                <td class="mono">{{ entry.item.row.order_no }}</td><td><b>{{ entry.item.row.product || '—' }}</b><small class="sub-cell">{{ entry.item.row.product_spec || '规格未填写' }}</small></td>
                <td><span v-if="entry.item.suggested_flower" class="matched-flower"><Flower2 :size="13"/>{{ entry.item.suggested_flower }}</span><span v-else class="unmatched-label"><CircleAlert :size="13"/>待匹配</span></td>
                <td><span class="state-tag" :class="entry.item.state === '退款成功' ? 'state-refund' : entry.item.state === '已取消' ? 'state-muted' : entry.item.needs_attention ? 'state-warning' : 'state-ok'">{{ entry.item.row.order_status || '—' }}</span><small v-if="entry.item.row.after_sale_status && entry.item.row.after_sale_status !== '-'" class="sub-cell">售后：{{ entry.item.row.after_sale_status }}</small></td>
                <td>{{ entry.item.order_date || '—' }}</td><td>{{ number(entry.item.meters) }} m<small v-if="entry.item.needs_attention" class="sub-cell">{{ entry.item.attention_reason }}</small></td>
                <td>{{ entry.item.stock_effect_meters ? `扣减 ${number(entry.item.stock_effect_meters)} m` : entry.item.state === '退款成功' ? '不扣库存' : '无变更' }}<small v-if="entry.item.previous_stock_effect_meters && entry.item.state === '退款成功'" class="sub-cell refund-note">回补 {{ number(entry.item.previous_stock_effect_meters) }} m</small></td>
                <td><span class="state-tag" :class="entry.item.needs_attention ? 'state-warning' : entry.item.state === '退款成功' ? 'state-refund' : entry.item.state === '已取消' ? 'state-muted' : 'state-ok'">{{ entry.item.needs_attention ? '待处理' : entry.item.state }}</span><button class="table-action" @click="entry.item.showEditor = !entry.item.showEditor">{{ entry.item.showEditor ? '收起编辑' : '编辑字段' }}</button></td>
              </tr>
              <tr v-else class="preview-edit-row"><td colspan="8"><details open><summary>{{ entry.item.needs_attention ? `核对：${entry.item.attention_reason || '订单信息'}` : '编辑订单全部可识别字段' }}</summary><div class="preview-fields"><label v-for="field in editableOrderFields" :key="field[0]" class="field"><span>{{ field[1] }}</span><FlowerSelect v-if="field[0] === 'flower'" :model-value="entry.item.flower || entry.item.suggested_flower || ''" :flowers="activeProducts" placeholder="选择或搜索花型" @update:model-value="editPreviewField(entry.item, 'flower', $event)"/><input v-else :type="field[2]" :value="field[2] === 'date' ? String(entry.item.row[field[0]] || '').slice(0, 10) : entry.item.row[field[0]] ?? ''" @input="editPreviewField(entry.item, field[0], $event.target.value)" /></label></div></details></td></tr>
            </template>
            <template #empty><tr v-if="!previewEntries.length"><td colspan="8" class="empty-cell">没有可显示的订单行</td></tr></template>
          </VirtualTable>
          <div class="preview-foot"><span><CircleAlert :size="15"/> 花型或规格未识别的行会保留待处理；未成功交易、退款和取消订单仍不计入库存与利润。</span><div><button class="button button-outline" @click="preview = null; previewDirty = false">取消</button><button class="button button-outline" :disabled="loading || !previewDirty" @click="recalculatePreview"><RefreshCw :size="15"/> 重新计算预览</button><button class="button button-primary" :disabled="loading || previewDirty" @click="commitPreview"><Check :size="16"/> 确认导入并更新库存</button></div></div>
        </section>
        <section class="unmatched-toolbar" v-if="unmatchedTotal || ignoredTotal"><div><b>待处理订单</b><span>{{ unmatchedTotal }} 条花型或规格未识别，不影响利润与库存</span></div><button class="compact-button" @click="toggleIgnored">{{ ignoredVisible ? '收起已忽略' : '已忽略 ' + ignoredTotal + ' 条 · 查看记录' }}</button></section>
        <section class="panel unmatched-table-panel" v-if="unmatchedTotal"><div class="panel-head"><div><h2>待匹配订单</h2><p>过时商品可批量忽略；需要时可在“已忽略”中恢复。</p></div><div class="table-tools"><button class="button button-outline" @click="toggleAllUnmatched">{{ allUnmatchedSelected ? '取消全选所有' : '全选所有' }}</button><button class="button button-outline" @click="rematchUnmatched"><RefreshCw :size="14"/> 重新匹配</button><button class="button button-outline danger-action" :disabled="!selectedUnmatchedCount" @click="ignoreSelected">忽略所选（{{ selectedUnmatchedCount }}）</button></div></div><div class="table-wrap"><table data-server-sort="unmatched"><thead><tr><th class="no-sort"><input type="checkbox" :checked="allUnmatchedSelected ? unmatched.every(item => !excludedUnmatched.includes(item.id)) : unmatched.length > 0 && unmatched.every(item => selectedUnmatched.includes(item.id))" @change="toggleAllUnmatched" aria-label="全选所有待匹配订单" /></th><th data-sort-key="order_no">订单号</th><th data-sort-key="product">商品</th><th data-sort-key="product_spec">规格</th><th data-sort-key="status">状态</th><th data-sort-key="order_date">业务日期</th><th data-sort-key="merchant_income">金额</th></tr></thead><tbody><tr v-for="item in unmatched" :key="item.id"><td><input type="checkbox" :checked="allUnmatchedSelected ? !excludedUnmatched.includes(item.id) : selectedUnmatched.includes(item.id)" @change="toggleUnmatchedSelection(item.id, $event.target.checked)" :aria-label="'选择订单 ' + item.order_no" /></td><td class="mono">{{ item.order_no }}</td><td>{{ item.product }}</td><td>{{ item.product_spec }}</td><td>{{ item.order_status }} {{ item.after_sale_status }}</td><td>{{ item.order_date || '—' }}</td><td>{{ money(item.merchant_income) }}</td></tr></tbody></table></div><div class="table-pagination"><span>第 {{ unmatchedPage }} / {{ unmatchedPageCount }} 页 · 共 {{ unmatchedTotal }} 条</span><div class="pagination-controls"><button class="button button-outline" :disabled="unmatchedPage <= 1" @click="gotoUnmatchedPage(unmatchedPage - 1)">上一页</button><button v-for="pageNumber in unmatchedPages" :key="pageNumber" class="page-number" :class="{ active: unmatchedPage === pageNumber }" @click="gotoUnmatchedPage(pageNumber)">{{ pageNumber }}</button><select class="page-jump" :value="unmatchedPage" @change="gotoUnmatchedPage(Number($event.target.value))"><option v-for="pageNumber in unmatchedPageCount" :key="pageNumber" :value="pageNumber">第 {{ pageNumber }} 页</option></select><button class="button button-outline" :disabled="unmatchedPage >= unmatchedPageCount" @click="gotoUnmatchedPage(unmatchedPage + 1)">下一页</button></div></div></section>
        <section class="panel unmatched-table-panel ignored-panel" v-if="ignoredVisible"><div class="panel-head"><div><h2>已忽略订单</h2><p>共 {{ ignoredTotal }} 条。恢复后会重新出现在待匹配列表。</p></div><span class="pill">已忽略 {{ ignoredTotal }} 条</span></div><div class="table-wrap"><table data-server-sort="ignored"><thead><tr><th data-sort-key="order_no">订单号</th><th data-sort-key="product">商品</th><th data-sort-key="product_spec">规格</th><th data-sort-key="status">状态</th><th data-sort-key="order_date">业务日期</th><th data-sort-key="merchant_income">金额</th><th class="no-sort">操作</th></tr></thead><tbody><tr v-for="item in ignored" :key="item.id"><td class="mono">{{ item.order_no }}</td><td>{{ item.product }}</td><td>{{ item.product_spec }}</td><td>{{ item.order_status }} {{ item.after_sale_status }}</td><td>{{ item.order_date || '—' }}</td><td>{{ money(item.merchant_income) }}</td><td><button class="table-action restore-action" @click="restoreIgnored(item)">恢复</button></td></tr><tr v-if="!ignored.length"><td colspan="7" class="empty-cell">没有已忽略的订单</td></tr></tbody></table></div><div class="table-pagination"><span>第 {{ ignoredPage }} / {{ ignoredPageCount }} 页 · 共 {{ ignoredTotal }} 条</span><div class="pagination-controls"><button class="button button-outline" :disabled="ignoredPage <= 1" @click="gotoIgnoredPage(ignoredPage - 1)">上一页</button><button v-for="pageNumber in ignoredPages" :key="pageNumber" class="page-number" :class="{ active: ignoredPage === pageNumber }" @click="gotoIgnoredPage(pageNumber)">{{ pageNumber }}</button><button class="button button-outline" :disabled="ignoredPage >= ignoredPageCount" @click="gotoIgnoredPage(ignoredPage + 1)">下一页</button></div></div></section>
      </div>

      <div v-else-if="page === 'inventory'" class="page-content">
        <div class="page-heading"><div><div class="eyebrow">INVENTORY CONTROL <span class="eyebrow-dot"></span> 库存与流水</div><h1>库存管理</h1><p>订单导入自动扣减/退款回补；手工入库、出库、盘点可指定实际生效日期。</p></div><div class="inventory-heading-actions"><button v-if="inventoryTab === 'stock'" class="button button-outline" @click="exportInventory"><FileSpreadsheet :size="15"/> 导出库存快照</button><div class="inventory-total"><span>管理花型</span><b>{{ dashboard.inventory.length }} <small>种</small></b></div></div></div>
        <nav class="inventory-tabs" aria-label="库存管理分类"><button :class="{ active: inventoryTab === 'stock' }" @click="inventoryTab = 'stock'"><Boxes :size="16"/> 花型库存</button><button :class="{ active: inventoryTab === 'recommendations' }" @click="inventoryTab = 'recommendations'"><Sparkles :size="16"/> 智能补货建议</button><button :class="{ active: inventoryTab === 'movement' }" @click="inventoryTab = 'movement'"><Plus :size="16"/> 登记库存操作</button><button :class="{ active: inventoryTab === 'purchases' }" @click="inventoryTab = 'purchases'"><Truck :size="16"/> 采购到货记录</button><button :class="{ active: inventoryTab === 'events' }" @click="inventoryTab = 'events'"><Activity :size="16"/> 库存流水</button></nav>
        <section v-if="inventoryTab === 'recommendations'" class="panel data-panel">
          <div class="panel-head"><div><h2>智能补货建议</h2><p>近 {{ recommendations.sales_window_days || settings.inventory_sales_window_days }} 天销量用于估算日均需求；显示预计卖完日，并按 {{ number(recommendations.batch_capacity_meters || settings.procurement_batch_capacity_meters) }} 米单次容量排采购计划。</p></div><span class="pill positive"><Sparkles :size="14"/> 目标覆盖 {{ recommendations.target_coverage_days || settings.procurement_target_days }} 天</span></div>
          <div class="table-wrap"><table><thead><tr><th>优先级</th><th>花型</th><th>库存</th><th>近 {{ recommendations.sales_window_days || settings.inventory_sales_window_days }} 天销量</th><th>日均销量</th><th>预计卖完</th><th>状态</th><th>建议进货日</th><th>预计到店</th><th>计划卷数 / 米数</th></tr></thead><tbody><tr v-for="item in visibleRecommendations" :key="item.flower"><td>{{ item.priority ? `#${item.priority}` : '—' }}</td><td><div class="flower-cell"><div class="flower-dot">{{ item.flower.slice(0, 1) }}</div><b>{{ item.flower }}</b></div></td><td>{{ number(item.current_stock) }} 米</td><td>{{ number(item.recent_sales) }} 米</td><td>{{ number(item.daily_use) }} 米</td><td>{{ item.sellout_label }}</td><td><span class="state-tag" :class="item.status === '立即关注' || item.current_stock <= 0 ? 'state-warning' : 'state-ok'">{{ item.current_stock <= 0 ? '已无库存' : item.status }}</span></td><td>{{ item.order_date || '—' }}</td><td>{{ item.arrival_date || '—' }}</td><td><template v-if="item.roll_count">{{ item.roll_count }} 卷 / {{ number(item.meters) }} 米</template><span v-else>{{ item.plan_issue || '暂不需要' }}</span></td></tr><tr v-if="!recommendations.items?.length"><td colspan="10" class="empty-cell">暂无可用补货建议</td></tr></tbody></table></div>
          <div class="restock-strategy" v-if="recommendations.strategy?.length"><h3>按进货日期安排（同日超出单次容量会列为额外趟次）</h3><div class="table-wrap"><table><thead><tr><th>进货日期</th><th>趟次</th><th>花型及卷数</th><th>本趟米数 / 上限</th><th>预计到店</th><th>估算成本</th></tr></thead><tbody><template v-for="day in recommendations.strategy" :key="day.order_date"><tr v-for="batch in day.batches" :key="`${day.order_date}-${batch.trip}`"><td>{{ day.order_date }}</td><td>{{ batch.trip === 1 ? '第 1 趟' : `额外第 ${batch.trip} 趟` }}</td><td><span v-for="planned in batch.items" :key="planned.flower" class="strategy-flower">{{ planned.flower }} {{ planned.roll_count }} 卷</span></td><td>{{ number(batch.total_meters) }} / {{ number(recommendations.batch_capacity_meters) }} 米</td><td><span v-for="planned in batch.items" :key="`${planned.flower}-arrival`" class="strategy-arrival">{{ planned.flower }}：{{ planned.arrival_date }}</span></td><td>{{ money(batch.estimated_cost) }}</td></tr></template></tbody></table></div></div>
          <div class="restock-foot"><CircleAlert :size="14"/><span>预计卖完日按当前库存 ÷ 近 {{ recommendations.sales_window_days || settings.inventory_sales_window_days }} 天日均销量估算；进货按整卷装载、每趟不超过设定米数。无近期销量时不虚构补货量。建议仅供参考，不会自动下单。</span></div>
        </section>
        <section v-else-if="inventoryTab === 'stock'" class="panel data-panel">
          <div class="panel-head"><div><h2>花型库存</h2><p>选择某一天查看历史库存；盘点日同时显示账面理论数、实盘数及差值。</p></div><div class="table-tools"><DatePicker v-model="stockAsOf" label="库存日期"/><div class="search-box"><Search :size="15"/><input v-model="searchText" placeholder="搜索花型" /></div><button class="icon-button small" title="刷新库存" @click="loadInventory"><RefreshCw :size="15"/></button></div></div>
          <div class="table-wrap"><table><thead><tr><th>花型</th><th>成本 / 米</th><th>理论库存</th><th v-if="dashboard.inventory.some(row => row.counted_stock !== null)">盘点库存</th><th v-if="dashboard.inventory.some(row => row.counted_stock !== null)">差值</th><th>近 {{ settings.inventory_sales_window_days }} 天净出库</th><th>动态预警线</th><th>库存状态</th></tr></thead><tbody><tr v-for="item in filteredInventory" :key="item.flower"><td><div class="flower-cell"><div class="flower-dot">{{ item.flower.slice(0, 1) }}</div><b>{{ item.flower }}</b></div></td><td>{{ money(item.cost_per_meter) }}</td><td><b class="stock-number" :class="{ 'low-stock': item.low_stock }">{{ number(item.theoretical_stock) }}</b> 米</td><td v-if="dashboard.inventory.some(row => row.counted_stock !== null)">{{ item.counted_stock === null ? '—' : `${number(item.counted_stock)} 米` }}</td><td v-if="dashboard.inventory.some(row => row.counted_stock !== null)">{{ item.inventory_difference === null ? '—' : `${number(item.inventory_difference)} 米` }}</td><td>{{ number(item.recent_sales) }} 米</td><td>{{ number(item.reorder_level) }} 米</td><td><span class="state-tag" :class="item.low_stock ? 'state-warning' : 'state-ok'">{{ item.low_stock ? '库存偏低' : '正常' }}</span></td></tr><tr v-if="!filteredInventory.length"><td colspan="8" class="empty-cell">暂无花型库存</td></tr></tbody></table></div>
        </section>
        <section v-else-if="inventoryTab === 'purchases'" class="panel data-panel">
          <div class="panel-head"><div><h2>采购到货记录</h2><p>按登记的实际到店日期记录到货卷数与米数</p></div><div class="table-tools"><span class="pill">共 {{ purchaseTotal }} 条</span><div class="search-box"><Search :size="15"/><input v-model="purchaseSearch" placeholder="搜索采购记录" @keyup.enter="purchasePage = 1; loadPagedTable('purchases')"/></div><button class="icon-button small" title="搜索采购记录" @click="purchasePage = 1; loadPagedTable('purchases')"><Search :size="15"/></button></div></div><div class="table-wrap"><table data-server-sort="purchases"><thead><tr><th data-sort-key="received_date">到店日期</th><th data-sort-key="flower">花型</th><th data-sort-key="roll_count">卷数</th><th data-sort-key="roll_length_meters">每卷长度</th><th data-sort-key="total_meters">入库米数</th><th data-sort-key="reference">备注</th></tr></thead><tbody><tr v-for="item in purchases" :key="item.id"><td>{{ item.received_date }}</td><td><b>{{ item.flower }}</b></td><td>{{ item.roll_count }} 卷</td><td>{{ number(item.roll_length_meters) }} 米</td><td>{{ number(item.total_meters) }} 米</td><td>{{ item.reference || '—' }}</td></tr><tr v-if="!purchases.length"><td colspan="6" class="empty-cell">暂无采购到货记录</td></tr></tbody></table></div><div class="table-pagination"><span>第 {{ purchasePage }} / {{ purchasePageCount }} 页 · 共 {{ purchaseTotal }} 条</span><div class="pagination-controls"><button class="button button-outline" :disabled="purchasePage <= 1" @click="gotoTablePage('purchases', purchasePage - 1)">上一页</button><button v-for="pageNumber in pageWindow(purchasePage, purchasePageCount)" :key="pageNumber" class="page-number" :class="{ active: purchasePage === pageNumber }" @click="gotoTablePage('purchases', pageNumber)">{{ pageNumber }}</button><select class="page-jump" :value="purchasePage" @change="gotoTablePage('purchases', Number($event.target.value))"><option v-for="pageNumber in purchasePageCount" :key="pageNumber" :value="pageNumber">第 {{ pageNumber }} 页</option></select><button class="button button-outline" :disabled="purchasePage >= purchasePageCount" @click="gotoTablePage('purchases', purchasePage + 1)">下一页</button></div></div>
        </section>
        <section v-else-if="inventoryTab === 'movement'" class="panel data-panel movement-panel"><div class="panel-head"><div><h2>登记库存操作</h2><p>采购入库按每个花型的固定卷长整卷增加；也支持回溯日期的主动出库和盘点。</p></div><div class="movement-icon"><Package :size="18"/></div></div>
          <form class="form-grid" @submit.prevent="saveMovement"><label class="field span-2"><span>花型</span><FlowerSelect v-model="inventoryForm.flower" :flowers="activeProducts" placeholder="选择或搜索花型"/></label><label class="field"><span>操作类型</span><select v-model="inventoryForm.operation"><option>采购入库</option><option>主动出库</option><option>盘点</option></select></label><label class="field"><span>{{ inventoryForm.operation === '采购入库' ? '进货卷数 (整卷)' : inventoryForm.operation === '盘点' ? '盘点后实存 (米)' : '出库数量 (米)' }}</span><input v-model.number="inventoryForm.quantity" min="0" :step="inventoryForm.operation === '采购入库' ? 1 : 0.5" :max="inventoryForm.operation === '采购入库' ? 10000 : undefined" type="number" required :placeholder="inventoryForm.operation === '采购入库' ? '例如 1 卷' : '例如 12.5 米'" /></label><DatePicker v-model="inventoryForm.effective_date" :label="inventoryForm.operation === '采购入库' ? '实际到店日期' : '生效日期'"/><label class="field"><span>备注 / 供应商</span><input v-model="inventoryForm.reference" maxlength="240" placeholder="可选"/></label><button class="button button-primary span-2" type="submit"><Plus :size="16"/> 保存库存流水</button></form>
          <div class="form-hint"><CircleAlert :size="14"/>采购按整卷入库；盘点填写实存米数，流水调整值为“实存 − 理论库存”，库存页差值显示“理论 − 盘点”。</div>
        </section>
        <section v-else class="panel data-panel"><div class="panel-head"><div><h2>库存流水</h2><p>自动记录订单出库、退款回补与手工操作；排序作用于全部记录</p></div><div class="table-tools"><span class="pill">共 {{ eventTotal }} 条</span><div class="search-box"><Search :size="15"/><input v-model="eventSearch" placeholder="搜索流水" @keyup.enter="eventPage = 1; loadPagedTable('events')"/></div><button class="icon-button small" title="搜索流水" @click="eventPage = 1; loadPagedTable('events')"><Search :size="15"/></button></div></div><div class="table-wrap"><table data-server-sort="events"><thead><tr><th data-sort-key="effective_date">生效日期</th><th data-sort-key="flower">花型</th><th data-sort-key="event_type">操作</th><th data-sort-key="change_qty">变动</th><th data-sort-key="before_stock">变动前</th><th data-sort-key="after_stock">变动后</th><th data-sort-key="reference">备注 / 订单号</th><th data-sort-key="created_at">登记时间</th></tr></thead><tbody><tr v-for="item in events" :key="item.id"><td>{{ item.effective_date }}</td><td><b>{{ item.flower }}</b></td><td><span class="event-type" :class="item.change_qty >= 0 ? 'event-in' : 'event-out'">{{ item.event_type }}</span></td><td :class="item.change_qty >= 0 ? 'green-text' : 'red-text'">{{ item.change_qty > 0 ? '+' : '' }}{{ number(item.change_qty) }} 米</td><td>{{ number(item.before_stock) }}</td><td><b>{{ number(item.after_stock) }}</b></td><td class="reference-cell">{{ item.reference || '—' }}</td><td>{{ String(item.created_at || '').slice(0, 16) }}</td></tr><tr v-if="!events.length"><td colspan="8" class="empty-cell">暂无库存流水</td></tr></tbody></table></div><div class="table-pagination"><span>第 {{ eventPage }} / {{ eventPageCount }} 页 · 共 {{ eventTotal }} 条</span><div class="pagination-controls"><button class="button button-outline" :disabled="eventPage <= 1" @click="gotoTablePage('events', eventPage - 1)">上一页</button><button v-for="pageNumber in pageWindow(eventPage, eventPageCount)" :key="pageNumber" class="page-number" :class="{ active: eventPage === pageNumber }" @click="gotoTablePage('events', pageNumber)">{{ pageNumber }}</button><select class="page-jump" :value="eventPage" @change="gotoTablePage('events', Number($event.target.value))"><option v-for="pageNumber in eventPageCount" :key="pageNumber" :value="pageNumber">第 {{ pageNumber }} 页</option></select><button class="button button-outline" :disabled="eventPage >= eventPageCount" @click="gotoTablePage('events', eventPage + 1)">下一页</button></div></div></section>
      </div>

      <div v-else-if="page === 'reports'" class="page-content">
        <div class="page-heading"><div><div class="eyebrow">PROFIT & REPORTS <span class="eyebrow-dot"></span> 实时计算</div><h1>经营报表</h1><p>日报、区间报告、出库入库明细和退款明细；Excel 只保存到设置的输出目录。</p></div></div>
        <section class="panel filter-panel"><div class="report-filters"><DatePicker v-model="reportRange.start" label="开始日期" /><DatePicker v-model="reportRange.end" label="结束日期" /><button class="button button-primary report-go" @click="loadReport"><Search :size="16"/> 查询</button></div><div class="date-presets"><button @click="reportRange.start = today; reportRange.end = today; loadReport()">今天</button><button @click="reportRange.start = startOfMonth; reportRange.end = today; loadReport()">本月</button></div><div class="report-generator"><div class="report-type-tabs"><button :class="{ active: reportExportType === 'daily' }" @click="setReportType('daily')">日报</button><button :class="{ active: reportExportType === 'range' }" @click="setReportType('range')">区间报告</button><button :class="{ active: reportExportType === 'inout' }" @click="setReportType('inout')">出库入库明细</button><button :class="{ active: reportExportType === 'refund' }" @click="setReportType('refund')">退款明细</button></div><div class="report-export-slot"><button class="button button-outline report-export" @click="exportSelectedReport"><FileSpreadsheet :size="16"/> {{ reportExportType === 'daily' ? '生成日报 Excel' : reportExportType === 'range' ? '生成区间报告 Excel' : reportExportType === 'inout' ? '生成出库入库明细' : '生成退款明细 Excel' }}</button><small>{{ reportExportType === 'daily' ? '日报按开始日期生成。' : reportExportType === 'refund' ? '仅统计已发货/已收货成功退款，费率沿用旧金额口径。' : '按所选日期范围生成。' }}</small></div></div></section>
        <div v-if="['daily','range'].includes(reportExportType)" class="report-metrics"><div class="report-metric"><span><ShoppingBag :size="15"/> 订单行数</span><b>{{ reportVisibleTotals.订单行数 || 0 }}</b></div><div class="report-metric"><span><Wallet :size="15"/> 营业额</span><b>{{ money(reportVisibleTotals.营业额) }}</b></div><div class="report-metric"><span><Package :size="15"/> 商品成本</span><b>{{ money(reportVisibleTotals.成本) }}</b></div><div class="report-metric emphasis"><span><TrendingUp :size="15"/> 净利润</span><b>{{ money(reportVisibleTotals.利润) }}</b></div></div>
        <div v-else-if="reportExportType === 'refund'" class="report-metrics refund-metrics"><div class="report-metric emphasis"><span><Wallet :size="15"/> 退款金额</span><b>{{ money(refundReport?.totals?.退款金额) }}</b></div><div class="report-metric"><span><TrendingUp :size="15"/> 金额退款率</span><b>{{ percent(refundReport?.totals?.退款率) }}</b></div><div class="report-metric"><span><ShoppingBag :size="15"/> 同期有效营业额</span><b>{{ money(refundReport?.totals?.退款基数) }}</b></div></div>
        <div v-else class="report-metrics"><div class="report-metric"><span><Boxes :size="15"/> 花型数</span><b>{{ inoutReport?.rows?.length || 0 }}</b></div><div class="report-metric"><span><Plus :size="15"/> 入库米数</span><b>{{ number(inoutReport?.rows?.reduce((sum, row) => sum + row.入库米数, 0)) }} m</b></div><div class="report-metric"><span><Activity :size="15"/> 出库米数</span><b>{{ number(inoutReport?.rows?.reduce((sum, row) => sum + row.出库米数, 0)) }} m</b></div><div class="report-metric emphasis"><span><CalendarDays :size="15"/> 日期范围</span><b class="range-value">{{ reportRange.start }} 至 {{ reportRange.end }}</b></div></div>

        <section v-if="['daily','range'].includes(reportExportType)" class="panel data-panel report-table"><div class="panel-head"><div><h2>{{ reportExportType === 'daily' ? '日报经营汇总' : '区间经营汇总' }}</h2><p>{{ reportExportType === 'daily' ? reportRange.start : `${reportRange.start} 至 ${reportRange.end}` }} · 退款、关闭订单不计入</p></div><span class="pill positive"><CircleCheck :size="14"/> 数据已同步</span></div>
          <VirtualTable class="report-virtual-table" :items="reportEntries" :columns="9" :column-widths="['10%', '18%', '11%', '9%', '8%', '11%', '11%', '9%', '13%']" :row-height="50" :max-height="'min(65vh, 640px)'">
            <template #header><tr><th data-sort-key="日期">日期</th><th data-sort-key="花型">花型</th><th data-sort-key="平台">平台</th><th data-sort-key="订单行数">订单行数</th><th data-sort-key="米数">米数</th><th data-sort-key="营业额">营业额</th><th data-sort-key="成本">面料成本</th><th data-sort-key="运费">运费</th><th class="align-right" data-sort-key="利润">净利润</th></tr></template>
            <template #row="{ item }"><tr><td>{{ item.row.日期 }}</td><td><b>{{ item.row.花型 }}</b></td><td><span class="platform-tag">{{ item.row.平台 }}</span></td><td>{{ item.row.订单行数 }}</td><td>{{ number(item.row.米数) }} m</td><td>{{ money(item.row.营业额) }}</td><td>{{ money(item.row.成本) }}</td><td>{{ money(item.row.运费) }}</td><td class="align-right"><b class="profit-amount">{{ money(item.row.利润) }}</b></td></tr></template>
            <template #empty><tr v-if="!filteredReport.length"><td colspan="9" class="empty-cell">该日期范围暂无符合统计口径的订单</td></tr></template>
            <template #footer><tr v-if="filteredReport.length"><td colspan="3"><b>合计</b></td><td>{{ reportVisibleTotals.订单行数 }}</td><td>{{ number(reportVisibleTotals.米数) }} m</td><td>{{ money(reportVisibleTotals.营业额) }}</td><td>{{ money(reportVisibleTotals.成本) }}</td><td>{{ money(reportVisibleTotals.运费) }}</td><td class="align-right"><b class="profit-amount">{{ money(reportVisibleTotals.利润) }}</b></td></tr></template>
          </VirtualTable>
        </section>
        <section v-else-if="reportExportType === 'refund'" class="panel data-panel report-table"><div class="panel-head"><div><h2>退款金额与退款率（{{ reportRange.start }} 至 {{ reportRange.end }}）</h2><p>仅纳入已发货 / 已收货成功退款；退款金额及费率按旧版金额口径计算。</p></div><span class="pill warning">未发货退款不计</span></div><div class="table-wrap"><table class="refund-report-table"><thead><tr><th rowspan="2">花型</th><th v-for="platform in refundReport?.platforms || []" :key="platform" colspan="3">{{ platform }}</th><th colspan="3">汇总</th></tr><tr><template v-for="platform in refundReport?.platforms || []" :key="platform"><th>退款金额</th><th>有效营业额</th><th>退款率</th></template><th>退款金额</th><th>有效营业额</th><th>退款率</th></tr></thead><tbody><tr v-for="row in visibleReport" :key="row.花型"><td><b>{{ row.花型 }}</b></td><template v-for="platform in refundReport?.platforms || []" :key="platform"><td>{{ money(row[`${platform}_退款金额`]) }}</td><td>{{ money(row[`${platform}_退款基数`]) }}</td><td>{{ percent(row[`${platform}_退款率`]) }}</td></template><td><b>{{ money(row.汇总_退款金额) }}</b></td><td>{{ money(row.汇总_退款基数) }}</td><td><b>{{ percent(row.汇总_退款率) }}</b></td></tr><tr v-if="!filteredReport.length"><td colspan="13" class="empty-cell">该日期范围暂无已发货或已收货的成功退款</td></tr></tbody><tfoot v-if="refundReport"><tr><td><b>合计</b></td><template v-for="platform in refundReport.platforms" :key="platform"><td>{{ money(refundReport.platform_totals[platform].退款金额) }}</td><td>{{ money(refundReport.platform_totals[platform].退款基数) }}</td><td>{{ percent(refundReport.platform_totals[platform].退款率) }}</td></template><td><b>{{ money(refundReport.totals.退款金额) }}</b></td><td>{{ money(refundReport.totals.退款基数) }}</td><td><b>{{ percent(refundReport.totals.退款率) }}</b></td></tr></tfoot></table></div></section>
        <section v-else-if="reportExportType === 'inout'" class="panel data-panel report-table"><div class="panel-head"><div><h2>出库入库汇总</h2><p>{{ reportRange.start }} 至 {{ reportRange.end }} · 明细 Excel 保持旧版模板</p></div></div><div class="table-wrap"><table><thead><tr><th>花型</th><th>期初库存</th><th>入库米数</th><th>出库米数</th><th>期末库存</th></tr></thead><tbody><tr v-for="row in visibleReport" :key="row.花型"><td><b>{{ row.花型 }}</b></td><td>{{ number(row.期初库存) }} m</td><td>{{ number(row.入库米数) }} m</td><td>{{ number(row.出库米数) }} m</td><td><b>{{ number(row.期末库存) }} m</b></td></tr><tr v-if="!filteredReport.length"><td colspan="5" class="empty-cell">该日期范围内没有库存变化</td></tr></tbody></table></div></section>

        <div v-if="['daily','range'].includes(reportExportType)" class="report-note"><CircleAlert :size="15"/><span>利润口径：商家实收 − 花型成本 × 米数 − 每个识别包裹一次固定运费（{{ money(settings.default_shipping_fee) }}）；不读取订单表邮费列。未匹配订单不计入。</span></div>
      </div>

      <div v-else-if="page === 'products'" class="page-content">
        <div class="page-heading"><div><div class="eyebrow">PRODUCT CATALOG <span class="eyebrow-dot"></span> 商品与成本</div><h1>商品成本</h1><p>维护花型标准名和每米成本，用于订单匹配、利润和库存计算。</p></div><div class="catalog-count"><Flower2 :size="17"/><b>{{ products.length }}</b> 个花型</div></div>
        <div class="content-grid product-grid"><section class="panel add-product-panel"><div class="panel-head"><div><h2>{{ editingFlower ? '编辑花型' : '添加 / 更新花型' }}</h2><p>{{ editingFlower ? `正在更新：${editingFlower}` : '新花型默认每卷 45 米，可按花型调整。' }}</p></div><div class="movement-icon"><Plus :size="18"/></div></div><form class="form-grid" @submit.prevent="saveProduct"><label class="field span-2"><span>标准花型名</span><FlowerSelect v-model="productForm.flower" :flowers="activeProducts" placeholder="例如：灰白底腰果花" @select="selectProductFlower"/></label><div class="field span-2"><span>匹配别名（可添加多个）</span><div v-if="editingAliases.length" class="alias-chips"><button v-for="alias in editingAliases" :key="alias" type="button" class="alias-chip" @click="removeEditingAlias(alias)">{{ alias }} <X :size="12"/></button></div><input v-model="productForm.aliasesText" maxlength="1000" placeholder="例如：腰果花；留空表示不改已有别名" @input="aliasesDirty = true" /></div><label class="field span-2"><span>成本单价 (元 / 米)</span><input v-model="productForm.cost_per_meter" inputmode="decimal" placeholder="例如：6.00" /></label><label class="field"><span>每卷米数</span><input v-model="productForm.roll_length_meters" inputmode="numeric" placeholder="45" /></label><label class="field"><span>预计到店天数</span><input v-model="productForm.replenishment_days" inputmode="numeric" placeholder="1" /></label><div class="span-2 form-button-row"><button class="button button-primary" type="submit"><Check :size="16"/> {{ editingFlower ? '保存修改' : '保存商品' }}</button><button v-if="editingFlower" class="button button-outline" type="button" @click="clearProductForm">取消</button></div></form><div class="form-hint"><CircleAlert :size="14"/>示例：标准名“灰白底腰果花”、别名“腰果花”、成本 6 元/米；编辑时数值留空表示不变。</div></section><section class="panel product-tip"><div class="tip-art"><Flower2 :size="29"/></div><div class="eyebrow">MATCHING TIP</div><h2>维护标准名与别名</h2><p>别名用于处理平台规格名称不统一的情况，例如把“腰果花”匹配到一个明确的标准花型，减少待匹配订单。</p><div class="tip-flow"><span>导入订单</span><ArrowRight :size="14"/><span>别名匹配</span><ArrowRight :size="14"/><span>利润与库存</span></div></section></div>
        <section class="panel data-panel"><div class="panel-head"><div><h2>花型成本档案</h2><p>更新成本会用于报表重算；改名同步更新新系统关联记录，停用不删除历史。</p></div><div class="search-box"><Search :size="15"/><input v-model="searchText" placeholder="搜索花型" /></div></div><div class="table-wrap"><table><thead><tr><th>花型</th><th>匹配别名</th><th>每米成本</th><th>每卷米数</th><th>预计到店天数</th><th>当前库存</th><th>最近更新</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="item in filteredProducts" :key="item.flower"><td><div class="flower-cell"><div class="flower-dot">{{ item.flower.slice(0, 1) }}</div><b>{{ item.flower }}</b></div></td><td>{{ item.aliases?.join('，') || '—' }}</td><td><b>{{ money(item.cost_per_meter) }}</b> / 米</td><td>{{ number(item.roll_length_meters) }} 米</td><td>{{ item.replenishment_days }} 天</td><td>{{ number(item.current_stock) }} 米</td><td>{{ String(item.updated_at || '').slice(0, 16) || '—' }}</td><td><span class="state-tag" :class="item.active ? 'state-ok' : 'state-muted'">{{ item.active ? '在售' : '已停用' }}</span></td><td><div class="row-actions"><button class="table-action" @click="editProduct(item)">编辑</button><button class="table-action" :class="item.active ? 'danger-action' : 'restore-action'" @click="archiveProduct(item)">{{ item.active ? '停用' : '恢复' }}</button></div></td></tr><tr v-if="!filteredProducts.length"><td colspan="9" class="empty-cell">还没有花型，添加第一条成本档案吧。</td></tr></tbody></table></div></section>
      </div>

      <div v-else-if="page === 'settings'" class="page-content">
        <div class="page-heading"><div><div class="eyebrow">PREFERENCES <span class="eyebrow-dot"></span> 本机配置</div><h1>系统设置</h1><p>配置 MySQL 数据库与报表输出位置。密码使用 Windows 凭据管理器加密保存。</p></div><div class="settings-secure"><ShieldCheck :size="16"/> 单人本机使用 · API 仅监听本机</div></div>
        <div class="settings-layout"><section class="panel settings-panel"><div class="panel-head"><div class="section-title"><div class="section-icon blue"><Database :size="18"/></div><div><h2>MySQL 数据库连接</h2><p>只需在第一次使用时配置，旧表不会被修改。</p></div></div><span class="connection-indicator" :class="system.connected ? 'online' : 'offline'"><i></i>{{ system.connected ? '已连接' : '未连接' }}</span></div><div class="settings-form"><label class="field"><span>数据库地址</span><input v-model="settings.mysql_host" placeholder="127.0.0.1" /></label><label class="field"><span>端口</span><input v-model.number="settings.mysql_port" type="number" min="1" max="65535" /></label><label class="field"><span>数据库名</span><input v-model="settings.mysql_database" placeholder="shop_data" /></label><label class="field"><span>用户名</span><input v-model="settings.mysql_user" autocomplete="username" /></label><label class="field span-2"><span>数据库密码 <small v-if="settings.has_password" class="saved-secret"><ShieldCheck :size="12"/> 已安全保存；留空保持不变</small></span><input v-model="settings.mysql_password" type="password" autocomplete="new-password" placeholder="输入数据库密码" /></label></div><div class="settings-actions"><button class="button button-outline" @click="saveSettings('database')"><Check :size="15"/> 保存数据库配置</button><button class="button button-primary" @click="testConnection"><Database :size="15"/> 保存并测试连接</button></div><div v-if="settingsMessages.database" class="connection-message" :class="settingsMessages.database.includes('成功') || settingsMessages.database.includes('已保存') ? 'success-message' : 'error-message'">{{ settingsMessages.database }}</div><div class="settings-footnote"><ShieldCheck :size="14"/>密码不会写入配置文件，也不会在界面/API 响应中回显。</div></section>
        <section class="panel settings-panel output-panel"><div class="panel-head"><div class="section-title"><div class="section-icon orange"><FileSpreadsheet :size="18"/></div><div><h2>Excel 输出路径</h2><p>文件只保存到所选目录，不会下载到浏览器默认目录。</p></div></div></div><label class="field folder-field"><span>日报输出目录</span><div class="path-input"><input v-model="settings.output_daily"/><button class="button button-outline" @click="chooseFolder('output_daily')">浏览</button></div></label><label class="field folder-field"><span>区间报告输出目录</span><div class="path-input"><input v-model="settings.output_range"/><button class="button button-outline" @click="chooseFolder('output_range')">浏览</button></div></label><label class="field folder-field"><span>退款明细输出目录</span><div class="path-input"><input v-model="settings.output_refund"/><button class="button button-outline" @click="chooseFolder('output_refund')">浏览</button></div></label><label class="field folder-field"><span>出库入库明细输出目录</span><div class="path-input"><input v-model="settings.output_inout"/><button class="button button-outline" @click="chooseFolder('output_inout')">浏览</button></div></label><label class="field folder-field"><span>库存快照输出目录</span><div class="path-input"><input v-model="settings.output_inventory"/><button class="button button-outline" @click="chooseFolder('output_inventory')">浏览</button></div></label><div class="output-actions"><button class="button button-primary save-paths" @click="saveSettings('paths')"><Check :size="15"/> 保存输出路径</button><span v-if="settingsMessages.paths" :class="settingsMessages.paths.includes('已保存') ? 'success-text' : 'error-text'">{{ settingsMessages.paths }}</span></div></section></div>
        <section class="panel settings-rules"><div class="panel-head"><div class="section-title"><div class="section-icon orange"><SlidersHorizontal :size="18"/></div><div><h2>经营计算规则</h2><p>这些参数无需改代码，在这里直接调整。</p></div></div></div><div class="rule-settings-grid"><label class="field"><span>每包固定运费 (元)</span><input v-model.number="settings.default_shipping_fee" type="number" min="0" step="0.1" /></label><label class="field"><span>库存预警销量周期（天）</span><input v-model.number="settings.inventory_sales_window_days" type="number" min="1" max="90" step="1" /></label><label class="field"><span>补货后目标覆盖天数</span><input v-model.number="settings.procurement_target_days" type="number" min="1" max="90" step="1" /></label><label class="field"><span>单次进货上限 (米)</span><input v-model.number="settings.procurement_batch_capacity_meters" type="number" min="1" max="1000000" step="1" /></label></div><div class="rule-settings-foot"><span><CircleAlert :size="14"/>日均销量 = 近周期净销量 ÷ 天数；预计卖完日 = 当前库存 ÷ 日均销量；预警线 = 日均销量 ×（预计到店天数 + 1）。补货后达到目标覆盖天数，并按整卷装载、每趟不超过进货上限。未知米数可在导入预览里修改后导入。</span><div class="rule-save"><button class="button button-primary" @click="saveSettings('rules')"><Check :size="15"/> 保存经营规则</button><span v-if="settingsMessages.rules" :class="settingsMessages.rules.includes('已保存') ? 'success-text' : 'error-text'">{{ settingsMessages.rules }}</span></div></div></section>
        <section class="panel baseline-panel"><div class="baseline-icon"><Database :size="19"/></div><div><b>兼容旧系统数据</b><span>首次初始化会将当前库存作为新系统起点，并复制历史订单状态用于报表。旧表仅读取，绝不重置库存或重放历史扣减。</span></div><span v-if="system.initialized" class="pill positive"><Check :size="14"/> 已完成</span><button v-else class="button button-outline" @click="initializeLegacy">开始初始化</button></section>
        <div class="local-note"><ShieldCheck :size="15"/><span>桌面版仅绑定 127.0.0.1，供本机单人使用。不要将本地服务端口暴露到公网。</span></div>
      </div>

      <footer class="app-footer"><span><span class="footer-mark">✦</span> 布店经营台 <i>·</i> 本地经营助手</span><span><i class="footer-status" :class="system.connected ? 'connected' : ''"></i>{{ system.connected ? '数据库已连接' : '等待数据库连接' }} <i>·</i> v1.0.0</span></footer>
    </main>
    <Transition name="toast"><div v-if="toast" class="toast-message"><CircleCheck :size="17"/>{{ toast }}<button @click="toast = ''"><X :size="15"/></button></div></Transition>
    <div v-if="loading && page === 'overview'" class="loading-corner"><LoaderCircle class="spin" :size="15"/> 正在同步</div>
  </div>
</template>

<style>
.restock-strategy{border-top:1px solid #eef1f5;margin-top:5px;padding:15px 18px 0}
.restock-strategy h3{font-size:12px;color:#4a5669;margin:0 0 9px}
.strategy-flower,.strategy-arrival{display:inline-block;margin:2px 9px 2px 0;white-space:nowrap}
.strategy-arrival{display:block;color:#8590a1;font-size:10px}
.restock-foot{align-items:flex-start;line-height:1.6}
</style>
