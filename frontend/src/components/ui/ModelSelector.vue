<script setup lang="ts">
import { cn } from '@/utils/cn'
import { ChevronDown } from 'lucide-vue-next'
import type { ModelInfo } from '@/types/api'

interface Props {
  models: ModelInfo[]
  modelValue: string
  disabled?: boolean
  id?: string
  name?: string
  autocomplete?: string
  class?: string
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

function handleChange(event: Event) {
  const target = event.target as HTMLSelectElement
  emit('update:modelValue', target.value)
}
</script>

<template>
  <div :class="cn('relative', props.class)">
    <select
      :id="id"
      :name="name"
      :autocomplete="autocomplete"
      :value="modelValue"
      :disabled="disabled || models.length === 0"
      class="w-full appearance-none rounded-xl border border-zinc-300 bg-white px-4 py-2.5 pr-10 text-sm font-medium text-zinc-900 shadow-sm transition-all hover:border-blue-400 focus:border-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-500/10 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 dark:hover:border-blue-400 dark:focus:border-blue-400"
      @change="handleChange"
    >
      <option v-if="models.length === 0" value="" disabled>正在加载模型...</option>
      <option v-for="model in models" :key="model.id" :value="model.id">
        {{ model.name }}
      </option>
    </select>
    <div class="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-3">
      <ChevronDown :size="16" class="text-zinc-500 dark:text-zinc-400" />
    </div>
  </div>
</template>
