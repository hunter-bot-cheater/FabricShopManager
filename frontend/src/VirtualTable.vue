<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'

const props = defineProps({
  items: { type: Array, default: () => [] },
  columns: { type: Number, required: true },
  columnWidths: { type: Array, default: () => [] },
  rowHeight: { type: Number, default: 48 },
  maxHeight: { type: [Number, String], default: 560 },
  overscan: { type: Number, default: 10 },
})

const host = ref(null)
const head = ref(null)
const scrollTop = ref(0)
const viewportHeight = ref(360)
const headerHeight = ref(44)

const layout = computed(() => {
  let top = 0
  const entries = props.items.map((item, index) => {
    const height = Math.max(1, Number(item?.height) || props.rowHeight)
    const entry = { item, index, top, bottom: top + height }
    top += height
    return entry
  })
  return { entries, total: top }
})

const visible = computed(() => {
  const { entries, total } = layout.value
  if (!entries.length) return { entries: [], before: 0, after: 0 }

  const bodyTop = scrollTop.value
  const bodyBottom = bodyTop + Math.max(0, viewportHeight.value - headerHeight.value)
  let low = 0
  let high = entries.length
  while (low < high) {
    const middle = (low + high) >>> 1
    if (entries[middle].bottom <= bodyTop) low = middle + 1
    else high = middle
  }

  const start = Math.max(0, low - props.overscan)
  let end = low
  while (end < entries.length && entries[end].top < bodyBottom) end += 1
  end = Math.min(entries.length, end + props.overscan)
  const rendered = entries.slice(start, end)
  const last = rendered[rendered.length - 1]
  return {
    entries: rendered,
    before: entries[start]?.top || 0,
    after: last ? total - last.bottom : total,
  }
})

function measure() {
  if (!host.value) return
  viewportHeight.value = host.value.clientHeight
  headerHeight.value = head.value?.offsetHeight || headerHeight.value
}

function onScroll(event) {
  scrollTop.value = event.currentTarget.scrollTop
  viewportHeight.value = event.currentTarget.clientHeight
}

watch(() => props.items, async () => {
  await nextTick()
  if (host.value) host.value.scrollTop = 0
  scrollTop.value = 0
  measure()
}, { flush: 'post' })

watch(() => props.maxHeight, async () => {
  await nextTick()
  measure()
})

onMounted(async () => {
  await nextTick()
  measure()
})

const maxHeightStyle = computed(() => typeof props.maxHeight === 'number'
  ? `${props.maxHeight}px` : props.maxHeight)
</script>

<template>
  <div ref="host" class="table-wrap virtual-table" :style="{ maxHeight: maxHeightStyle }" @scroll.passive="onScroll">
    <table>
      <colgroup><col v-for="(width, index) in columnWidths" :key="index" :style="width ? { width } : undefined" /></colgroup>
      <thead ref="head"><slot name="header" /></thead>
      <tbody>
        <tr v-if="visible.before > 0" class="virtual-spacer" aria-hidden="true">
          <td :colspan="columns" :style="{ height: `${visible.before}px` }"></td>
        </tr>
        <template v-for="entry in visible.entries" :key="entry.item?.key ?? entry.index">
          <slot name="row" :item="entry.item" :index="entry.index" />
        </template>
        <tr v-if="visible.after > 0" class="virtual-spacer" aria-hidden="true">
          <td :colspan="columns" :style="{ height: `${visible.after}px` }"></td>
        </tr>
        <slot name="empty" />
      </tbody>
      <tfoot><slot name="footer" /></tfoot>
    </table>
  </div>
</template>
