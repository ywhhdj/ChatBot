<script setup lang="ts">
const props = withDefaults(defineProps<{
  labelName: string
  inputMessage: string
  placeholder: string
}>(),
  {
    labelName: '请输入消息',
    inputMessage: '',
    placeholder: '请输入消息...',
  }
);
const emit = defineEmits(['input', 'change']);
</script>

<template>
  <div class="input-form">
    <label>{{ labelName }}</label>
    <span>: </span>
    <input
      type="text"
      :v-model="inputMessage"
      @change="emit('change')"
      @input="emit('input')"
      :placeholder="placeholder"
    >
  </div>
</template>

<style scoped>
.input-form {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  padding-bottom: 10px;
}

label {
  font-weight: bold;
  font-size: 14px;
}

span {
  padding-left: 10px;
  padding-right: 10px;
}

input {
  color: #ffffff;
  min-height: 2.5em;
  padding: 15px 20px;
  border-radius: 12px;
  backdrop-filter: blur(10px);
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.2);
  font-family: 'Courier New', Courier, monospace;
  flex: 1;
}

input:focus {
  outline: none;
}
</style>