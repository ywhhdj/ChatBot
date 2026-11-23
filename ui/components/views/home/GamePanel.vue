<script setup lang="ts">
import { useRouter } from 'vue-router'
import { defaultUIStore } from '@/stores/ui';
import type { GameMenuItem } from './GameMenu.vue'

const router = useRouter();
const uiStore = defaultUIStore();

const gameNav: GameMenuItem[] = [
  {
    key: 'new',
    label: '开始游戏',
    caption: 'NEW GAME',
    icon: 'play',
    action: () => router.push('/chat'),
  },
  {
    key: 'continue',
    label: '继续游戏',
    caption: 'CONTINUE',
    icon: 'history',
    action: () => {
      uiStore.setCurrentSettingsTab('save');
      router.push('/settings');
    },
  },
  {
    key: 'config',
    label: '游戏设置',
    caption: 'CONFIG',
    icon: 'settings',
    action: () => {
      uiStore.setCurrentSettingsTab('general');
      router.push('/settings');
    },
  },
  {
    key: 'exit',
    label: '退出游戏',
    caption: 'EXIT',
    icon: 'close',
    action: () => window.close(),
  },
];
</script>

<template>
  <div class="gn-panel">
    <header class="gn-head">
      <div class="gn-kicker">
        <span>◆</span> VISUAL NOVEL <span>◆</span>
      </div>

      <div class="gn-brand">
        <AppIcon
          :size="72"
          label="ChatBot"
        />
        <div class="gn-brand-text">
          <AppLogo />
          <p>与你相遇的，是第几个故事？</p>
        </div>
      </div>

      <div class="gn-rule" />
    </header>

    <GameMenu
      :items="gameNav"
      :numbered="true"
      aria-label="游戏主菜单"
    />

    <div class="gn-dialog">
      <span class="gn-nameplate">ChatBot</span>
      <Text
        class="gn-text"
        :speed="70"
        :min-delay="20"
        :max-delay="120"
      >「今天，也来聊聊天吧。」</Text>
    </div>

    <footer class="gn-foot">
      <span>DEVELOPMENT BUILD</span>
      <span class="gn-foot-dots">◆ ◆ ◆</span>
      <span>APACHE-2.0</span>
    </footer>
  </div>
</template>

<style scoped>
.gn-panel {
  width: min(520px, 100%);
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 18px 20px 12px;
  border-radius: 18px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  background: linear-gradient(
    160deg,
    rgba(0, 14, 39, 0.5) 0%,
    rgba(0, 14, 39, 0.18) 100%
  );
  backdrop-filter: blur(3px);
  -webkit-backdrop-filter: blur(3px);
  box-shadow:
    0 18px 60px rgba(0, 0, 0, 0.35),
    inset 0 1px 0 rgba(255, 255, 255, 0.16);
  color: #fff;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.55);
}

.gn-head {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.gn-kicker {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  font-family: ui-monospace, Menlo, monospace;
  font-size: 10px;
  letter-spacing: 0.4em;
  color: var(--primary-color);
  opacity: 0.85;
}

.gn-brand {
  display: flex;
  align-items: center;
  gap: 16px;
}

.gn-brand-text {
  min-width: 0;
}

.gn-brand-text p {
  margin: 6px 0 0;
  font-size: 12px;
  letter-spacing: 1px;
  opacity: 0.72;
}

.gn-rule {
  height: 1px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255, 255, 255, 0.55) 22%,
    rgba(121, 217, 255, 0.8) 50%,
    rgba(255, 255, 255, 0.55) 78%,
    transparent 100%
  );
}

/* 对话框：复用 base Text 的打字机 + 玻璃对话框 */
.gn-dialog {
  position: relative;
  margin-top: 2px;
}

.gn-nameplate {
  position: absolute;
  top: -10px;
  left: 18px;
  z-index: 1;
  padding: 2px 14px;
  border-radius: 6px;
  border: 1px solid rgba(121, 217, 255, 0.55);
  background: rgba(0, 14, 39, 0.9);
  font-family: 'Maoken Assorted Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 13px;
  letter-spacing: 1px;
  color: #fff;
}

.gn-dialog :deep(.text) {
  min-height: 0;
  padding: 20px 18px 14px;
  font-size: 14px;
  letter-spacing: 1px;
  line-height: 1.7;
  background: rgba(0, 14, 39, 0.55);
  border-color: rgba(255, 255, 255, 0.22);
}

.gn-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-family: ui-monospace, Menlo, monospace;
  font-size: 9px;
  letter-spacing: 0.18em;
  opacity: 0.5;
}

.gn-foot-dots {
  color: var(--primary-color);
  letter-spacing: 0.4em;
}

@media screen and (max-width: 768px) {
  .game-nav {
    padding: 14px 12px 10px;
    gap: 10px;
  }

  .gn-brand {
    gap: 10px;
  }

  .gn-brand-text p,
  .gn-foot {
    display: none;
  }
}
</style>
