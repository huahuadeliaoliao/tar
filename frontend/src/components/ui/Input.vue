<script setup lang="ts">
import { computed } from 'vue'
import { cn } from '@/utils/cn'

interface Props {
  modelValue?: string
  type?: string
  placeholder?: string
  disabled?: boolean
  error?: string
  id?: string
  name?: string
  autocomplete?: string
  class?: string
}

const props = withDefaults(defineProps<Props>(), {
  type: 'text',
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const inputClasses = computed(() => {
  const base =
    'w-full rounded-xl border bg-white px-4 py-3 text-sm shadow-sm outline-none transition-all placeholder:text-zinc-400 focus:shadow-md focus:ring-4 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-zinc-900'

  const variants = props.error
    ? 'border-red-300 focus:border-red-500 focus:ring-red-500/10 dark:border-red-700 dark:focus:border-red-400'
    : 'border-zinc-300 focus:border-blue-500 focus:ring-blue-500/10 dark:border-zinc-700 dark:focus:border-blue-400'

  return cn(base, variants, props.class)
})

function handleInput(event: Event) {
  const target = event.target as HTMLInputElement
  emit('update:modelValue', target.value)
}
</script>

<template>
  <div class="w-full">
    <input
      :id="id"
      :name="name"
      :type="type"
      :value="modelValue"
      :placeholder="placeholder"
      :disabled="disabled"
      :autocomplete="autocomplete"
      :class="inputClasses"
      @input="handleInput"
    />
    <p v-if="error" class="mt-1.5 text-xs text-red-600 dark:text-red-400">
      {{ error }}
    </p>
  </div>
</template>
