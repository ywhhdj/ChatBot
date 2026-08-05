<script setup lang="ts">
import { StreamRecord } from '@/events/event/record';
import { defaultUIStore } from '@/stores/ui';
import { useUserStore } from '@/stores/user';
import { useRouter } from 'vue-router';
const user = useUserStore();
const uiStore = defaultUIStore();
const router = useRouter();
const inputMessage = ref('');
const isInputEnabled = ref(true);
const isSending = ref(false);
const audio = new StreamRecord();
const clickHistory = () => {
  uiStore.setCurrentSettingsTab('history');
  router.push('/settings');
}

const menus: UI.MenuItem[] = [
  {
    type: 'nav',
    icon: 'play',
    clickAction: () => {
      user.isAutoSend = !user.isAutoSend;
    },
  },
  {
    type: 'nav',
    icon: 'history',
    clickAction: clickHistory,
  }
];
// const sendLLM = () => {
//   sendToLLM(inputMessage.value);
// }

const startRecord = () => {
  audio.startRecording((text: string) => {
    console.log(text);
    inputMessage.value += text;
  });
}

const stopRecord = () => {
  audio.stopRecording().then((text) => {
    console.log(text);
    inputMessage.value += text;
  });
}
</script>

<template>
  <div class="chatbox-box">
    <div class="chatbox-main">
      <div class="chatbox-title-part">
        <div class="chatbox-title">
          <!-- <div id="character">{{ uiStore.showCharacterTitle }}</div> -->
        </div>
        <div class="chatbox-subtitle">
          <!-- <div id="character-sub">{{ uiStore.showCharacterSubtitle }}</div> -->
        </div>
        <div class="chatbox-emotion">
          <!-- <div id="character-emotion">{{ uiStore.showCharacterEmotion }}</div> -->
        </div>
        <div class="chatbox-buttons">
          <Button
            v-for="(menu, index) in menus"
            :key="index"
            :type="menu.type"
            :icon="menu.icon"
            @click="menu.clickAction && menu.clickAction()"
          />
          <VoiceRecord
            @start="startRecord"
            @stop="stopRecord"
          />
        </div>
      </div>
      <div class="chatbox-line"></div>
      <div class="chatbox-inputbox">
        <textarea
          id="inputMessage"
          ref="textareaRef"
          placeholder="请输入消息..."
          v-model="inputMessage"
          @keydown.enter.exact.prevent="sendOrContinue"
          :readonly="!isInputEnabled"
        ></textarea>
        <button
          id="sendButton"
          :disabled="isSending"
          @click="sendOrContinue"
        >▼</button>
      </div>
    </div>
  </div>
</template>

<style>
.chatbox-box {
  position: relative;
  display: flex;
  justify-content: center;
  width: 100%;
  z-index: 2;
  background: linear-gradient(to top, rgba(0, 14, 39, 0.7) 0%, rgba(0, 14, 39, 0.6) 100%);
  padding: 15px;
  backdrop-filter: blur(1px);
  scrollbar-width: thin;
  scrollbar-color: var(--accent-color) transparent;
}

.chatbox-box::before {
  content: '';
  position: absolute;
  top: -40px;
  left: 0;
  right: 0;
  height: 40px;
  background: linear-gradient(to bottom,
      transparent 0%,
      rgba(0, 14, 39, 0.3) 50%,
      rgba(0, 14, 39, 0.6) 100%);
  pointer-events: none;
}

.chatbox-main {
  width: 60%;
}

.chatbox-title-part {
  display: flex;
  align-items: baseline;
  margin-bottom: 10px;
}

/* 确保所有文本元素都继承相同的字体和文字阴影 */
.chatbox-title,
.chatbox-subtitle,
#inputMessage,
#sendButton {
  font-family: inherit;
  /* 继承父元素字体 */
  text-shadow: inherit;
  /* 继承文字阴影 */
}

/* 调整特定元素的字体大小和粗细 */
.chatbox-title {
  font-size: 24px;
  font-weight: bold;
  color: white;
  margin-right: 15px;
}

.chatbox-subtitle {
  font-size: 20px;
  font-weight: bold;
  color: #6eb4ff;
}

.chatbox-emotion {
  font-size: 20px;
  font-weight: bold;
  color: #ff77dd;
  margin: auto;
}

.chatbox-buttons {
  display: flex;
}

.chatbox-line {
  height: 1px;
  background: rgba(255, 255, 255, 0.3);
  margin: 6px 0 6px 0;
}

.chatbox-inputbox {
  display: flex;
  flex-direction: column;
  white-space: pre-line;
  width: 100%;
  min-height: 40px;
  background: rgba(255, 255, 255, 0);
  border: none;
  color: white;
  font-size: 20px;
  font-weight: bold;
  resize: none;
  margin: 5px 0px;
  outline: none;
  transition: all 0.3s;
}

#inputMessage {
  font-size: 20px;
  font-weight: bold;
  width: 100%;
  min-height: 40px;
  background: rgba(255, 255, 255, 0);
  border: none;
  color: white;
  font-size: 20px;
  font-weight: bold;
  resize: none;
  margin: 5px 0px;
  outline: none;
  transition: all 0.3s;
}

#inputMessage::placeholder {
  color: rgba(255, 255, 255, 0.5);
  /* 明亮的灰色 */
  text-shadow: none;
  /* 移除阴影 */
}

#sendButton {
  align-self: flex-end;
  background: rgba(0, 14, 39, 0);
  color: rgb(4, 188, 255);
  border: none;
  padding: 4px 10px;
  border-radius: 5px;
  cursor: pointer;
  transition: all 0.3s;
  font-size: 20px;
  font-weight: bold;
  transform: scaleX(1.5);
}

#sendButton:hover {
  background: rgba(0, 14, 39, 0);
  color: rgba(136, 255, 251, 0.827);
}

#sendButton:disabled {
  background: #333;
  cursor: not-allowed;
  opacity: 0.7;
}

@media (max-width: 768px) {
  .chatbox-main {
    width: 90%;
  }
}
</style>
