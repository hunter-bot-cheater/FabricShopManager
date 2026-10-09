<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({ modelValue: { type: String, default: '' }, label: { type: String, default: '日期' } })
const emit = defineEmits(['update:modelValue'])
const open = ref(false)
const month = ref(parseDate(props.modelValue) || new Date())
let lastWheelTime = 0
const weekdays = ['一', '二', '三', '四', '五', '六', '日']

function parseDate(value) {
  if (!value) return null
  const [year, number] = value.split('-').map(Number)
  return new Date(year, number - 1, 1, 12)
}
function dateText(value) {
  const date = new Date(value.getFullYear(), value.getMonth(), value.getDate(), 12)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}
function startOfMonth(value) { return new Date(value.getFullYear(), value.getMonth(), 1, 12) }
const monthLabel = computed(() => `${month.value.getFullYear()}年${month.value.getMonth() + 1}月`)
const cells = computed(() => {
  const first = startOfMonth(month.value)
  const offset = (first.getDay() + 6) % 7
  const start = new Date(first.getFullYear(), first.getMonth(), 1 - offset, 12)
  return Array.from({ length: 42 }, (_, index) => {
    const date = new Date(start.getFullYear(), start.getMonth(), start.getDate() + index, 12)
    return { date, key: dateText(date), currentMonth: date.getMonth() === month.value.getMonth() }
  })
})
const selected = computed(() => props.modelValue || '')
function moveMonth(delta) { month.value = new Date(month.value.getFullYear(), month.value.getMonth() + delta, 1, 12) }
function handleWheel(event) {
  event.preventDefault()
  const now = performance.now()
  if (now - lastWheelTime < 180) return
  lastWheelTime = now
  moveMonth(event.deltaY > 0 ? 1 : -1)
}
function choose(date) {
  emit('update:modelValue', dateText(date))
  month.value = startOfMonth(date)
  open.value = false
}
function chooseToday() { choose(new Date()) }
function closePicker(event) { if (!event.target.closest('.date-picker')) open.value = false }
watch(() => props.modelValue, value => { const date = parseDate(value); if (date) month.value = date })
onMounted(() => window.addEventListener('click', closePicker))
onBeforeUnmount(() => window.removeEventListener('click', closePicker))
</script>

<template>
  <label class="field date-picker">
    <span>{{ label }}</span>
    <button class="date-picker-trigger" type="button" @click.stop="open = !open">
      <span>{{ modelValue || '选择日期' }}</span><span aria-hidden="true">▦</span>
    </button>
    <div v-if="open" class="calendar-popover" @click.stop @wheel="handleWheel">
      <div class="calendar-head"><button type="button" aria-label="上个月" @click="moveMonth(-1)">‹</button><b>{{ monthLabel }}</b><button type="button" aria-label="下个月" @click="moveMonth(1)">›</button></div>
      <div class="calendar-weekdays"><span v-for="day in weekdays" :key="day">{{ day }}</span></div>
      <div class="calendar-days" :data-month="String(month.getMonth() + 1).padStart(2, '0')">
        <button v-for="cell in cells" :key="cell.key" type="button"
          :class="{ muted: !cell.currentMonth, selected: cell.key === selected, today: cell.key === dateText(new Date()) }"
          @click="choose(cell.date)">{{ cell.date.getDate() }}</button>
      </div>
      <div class="calendar-foot"><button type="button" @click="emit('update:modelValue', ''); open = false">清除</button><button type="button" @click="chooseToday">今天</button></div>
      <small class="calendar-hint">滚动鼠标滚轮切换月份</small>
    </div>
  </label>
</template>

<style scoped>
.date-picker{position:relative}
.date-picker-trigger{height:35px;border:1px solid #dfe4ed;border-radius:7px;padding:0 10px;background:#fff;color:#39465b;display:flex;align-items:center;justify-content:space-between;gap:12px;font-size:14px;text-align:left}
.date-picker-trigger span:last-child{color:#7582dd;font-size:17px}
.calendar-popover{position:absolute;top:calc(100% + 7px);left:0;width:272px;padding:12px;background:#fff;border:1px solid #e4e8ef;border-radius:10px;box-shadow:0 14px 40px #1f2e4a26;z-index:20;user-select:none}
.calendar-head{display:flex;align-items:center;justify-content:space-between;height:32px;color:#364257}
.calendar-head b{font-size:14px}
.calendar-head button,.calendar-foot button{border:0;background:transparent;color:#5b68d9;font-size:21px;width:30px;height:30px;border-radius:6px;cursor:pointer}
.calendar-head button:hover,.calendar-foot button:hover{background:#f2f3ff}
.calendar-weekdays,.calendar-days{display:grid;grid-template-columns:repeat(7,1fr);text-align:center}
.calendar-weekdays{margin:8px 0 3px;color:#8a94a5;font-size:11px}
.calendar-weekdays span{height:25px;display:grid;place-items:center}
.calendar-days{position:relative;isolation:isolate}
.calendar-days:after{content:attr(data-month);position:absolute;z-index:-1;pointer-events:none;left:0;right:0;top:46px;text-align:center;color:#f5f6fb;font-size:72px;font-weight:700;line-height:1}
.calendar-days button{height:31px;border:0;background:transparent;border-radius:6px;color:#3c475a;font-size:12px;cursor:pointer}
.calendar-days button:hover{background:#edf0ff;color:#4f5fd5}
.calendar-days button.muted{color:#c0c6d0}
.calendar-days button.selected{background:#5b69e5;color:white;font-weight:700}
.calendar-days button.today:not(.selected){outline:1px solid #8c96e9}
.calendar-foot{display:flex;align-items:center;justify-content:space-between;border-top:1px solid #f0f2f6;margin-top:6px;padding-top:5px}
.calendar-foot button{font-size:12px;width:auto;padding:0 8px}
.calendar-hint{display:block;text-align:center;color:#a0a8b5;font-size:10px;margin-top:4px}
</style>
