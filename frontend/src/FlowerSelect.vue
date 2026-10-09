<script setup>
import { computed, ref } from 'vue'
import { ChevronDown } from 'lucide-vue-next'

const props = defineProps({
  modelValue: { type: String, default: '' },
  flowers: { type: Array, default: () => [] },
  placeholder: { type: String, default: '输入或选择花型' },
})
const emit = defineEmits(['update:modelValue', 'select'])
const open = ref(false)
const activeIndex = ref(0)
const filtered = computed(() => {
  const query = props.modelValue.trim().toLocaleLowerCase()
  return props.flowers.filter(item => !query || item.flower.toLocaleLowerCase().includes(query))
})

function select(item) {
  emit('update:modelValue', item.flower)
  emit('select', item)
  open.value = false
}
function closeLater() { window.setTimeout(() => { open.value = false }, 120) }
function onKeydown(event) {
  if (event.key === 'Escape') { open.value = false; return }
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    open.value = true
    activeIndex.value = Math.min(activeIndex.value + 1, filtered.value.length - 1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    activeIndex.value = Math.max(0, activeIndex.value - 1)
  } else if (event.key === 'Enter' && open.value && filtered.value.length) {
    event.preventDefault()
    select(filtered.value[activeIndex.value] || filtered.value[0])
  }
}
</script>

<template>
  <div class="flower-select" @keydown="onKeydown">
    <input :value="modelValue" :placeholder="placeholder" autocomplete="off"
      @focus="open = true; activeIndex = 0" @input="emit('update:modelValue', $event.target.value); open = true; activeIndex = 0"
      @blur="closeLater" />
    <ChevronDown class="flower-select-arrow" :size="16" @mousedown.prevent="open = !open" />
    <div v-if="open" class="flower-select-menu">
      <button v-for="(item, index) in filtered" :key="item.flower" type="button"
        :class="{ active: index === activeIndex }" @mousedown.prevent="select(item)">
        <span>{{ item.flower }}</span>
        <small>{{ Number(item.current_stock || 0).toLocaleString('zh-CN') }} 米库存</small>
      </button>
      <div v-if="!filtered.length" class="flower-select-empty">没有匹配的花型</div>
    </div>
  </div>
</template>

<style scoped>
.flower-select{position:relative;width:100%}.flower-select input{width:100%;padding-right:38px}.flower-select-arrow{position:absolute;right:12px;top:50%;transform:translateY(-50%);color:#8290a3;cursor:pointer}.flower-select-menu{position:absolute;z-index:30;left:0;right:0;top:calc(100% + 4px);max-height:260px;overflow-y:auto;padding:4px;background:#fff;border:1px solid #e3e8f0;border-radius:9px;box-shadow:0 10px 24px #25365120}.flower-select-menu button{display:flex;width:100%;height:auto;min-height:37px;align-items:center;justify-content:space-between;gap:10px;padding:8px 10px;border:0;border-radius:6px;background:#fff;color:#344055;text-align:left;cursor:pointer}.flower-select-menu button:hover,.flower-select-menu button.active{background:#f1f3ff;color:#4c5bd0}.flower-select-menu small{flex:none;color:#97a1b1;font-size:11px}.flower-select-empty{padding:12px;color:#929bab;font-size:12px;text-align:center}
</style>
