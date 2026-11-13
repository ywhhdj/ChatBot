<script setup lang="ts">
defineProps<{
  name: string
  src: string
}>()
</script>

<template>
  <div
    data-v-5ac3e6a0=""
    class="flex flex-col items-center w-28 md:w-32 shrink-0 space-y-2 border-r border-white/10 pr-4"
  >
    <div
      data-v-5ac3e6a0=""
      class="w-24 h-24 md:w-24 md:h-24 rounded-full overflow-hidden border-2 border-indigo-400/50 shadow-lg"
    ><img
        data-v-5ac3e6a0=""
        :src="src"
        :alt="name"
        class="w-full h-full object-cover group-hover:scale-110 transition-transform duration-500"
      ></div><span
      data-v-5ac3e6a0=""
      class="w-6 h-1 bg-brand rounded-full mt-1"
    ></span>
    <h4
      data-v-5ac3e6a0=""
      class="font-bold text-white text-md tracking-wide drop-shadow-md text-center"
    >{{ name }}</h4>
  </div>
</template>