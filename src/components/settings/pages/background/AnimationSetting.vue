<script setup lang="ts">
import { useUserStore } from '@/stores/user';

const user = useUserStore();
const animations = [
  {
    name: '雪花动画',
    checked: user.config.animations.snowFlakes,
    change: (checked: boolean) => {
      user.config.animations.snowFlakes = checked;
    }
  }
]

</script>

<template>
  <div class="animation-setting">
    <RowItem
      bg-color="transparent"
      v-for="animation in animations"
      :key="animation.name"
    >
      <template #left>
        <Checkbox
          @click="animation.change"
          :checked="animation.checked"
        />
      </template>
      <template #right>
        <span>{{ animation.name }}开关</span>
      </template>
    </RowItem>
  </div>
</template>