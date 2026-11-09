<script setup lang="ts">
import { folderService } from '@/api/services/folder';
import { emitBackgroundChange } from '@/events/event/background';
import { useTempStore } from '@/stores/ui';
import notification from '@/utils/notification';
import { getFileExtension } from '@/utils/util';

const uiStore = useTempStore();
const fileInputType = ['.jpeg', '.png', '.webp', '.bmp', '.svg', '.tif', '.gif'];
const uploadInput = ref<HTMLInputElement | null>(null);
const currentIndex = ref(0);

const getfileType = computed(() => {
  return fileInputType.join(',');
});

const isSelected = (index: number) => {
  return index === currentIndex.value;
};
const selectBackground = (url: string, index: number, duration?: number) => {
  currentIndex.value = index;
  emitBackgroundChange(url, duration);
};

const triggerUpload = () => {
  if (uploadInput.value) {
    uploadInput.value.click();
  }
};

const handleFileUpload = (event: Event) => {
  const target = event.target as HTMLInputElement;
  const files = Array.from(target.files || []);
  if (files.length === 0) return;
  files.forEach((file) => {
    if (!file.type.startsWith('image/')) {
      notification.showError({
        title: '文件类型错误',
        message: `${file.name} 不是图片文件`
      });
      return;
    }
    const ext = `.${getFileExtension(file.name)}`;
    if (!fileInputType.includes(ext)) {
      notification.showWarning({
        title: '不支持的图片格式',
        message: `${file.name} 格式不支持`
      });
      return;
    }
    const exists = uiStore.bgList.some((item) => item.name === file.name);
    if (exists) {
      notification.showWarning({
        title: '文件已存在',
        message: file.name
      });
      return;
    }
    uiStore.bgList.push({
      url: URL.createObjectURL(file),
      name: file.name.replace(/\.[^.]+$/, ''), // 去除扩展名
      index: uiStore.bgList.length, // 或 currentIndex + 1
      duration: undefined, // 默认无过渡时长
    });
  });
  if (target) target.value = '';
};

const openBackgroundFolder = async () => {
  await folderService.openFolder("images");
};

const deleteBackground = (index: number) => {
  if (index === 0) {
    notification.showWarning({
      title: '删除',
      message: '默认背景不能删除'
    })
    return;
  }
  const background = uiStore.bgList.splice(index, 1)[0];
  if (background) {
    URL.revokeObjectURL(background.url);
  }
  if (currentIndex.value >= uiStore.bgList.length) {
    currentIndex.value = Math.max(0, uiStore.bgList.length - 1);
    emitBackgroundChange(uiStore.bgList?.[currentIndex.value]?.url || '', uiStore.bgList?.[currentIndex.value]?.duration);
  }
};
</script>

<template>
  <BackgroundList>
    <BackgroundCard
      v-for="(background, index) in uiStore.bgList"
      :key="index"
      :isSelected="background.index === currentIndex"
    >
      <div class="background-image-container">
        <img
          :src="background.url"
          :alt="background.name"
          class="background-image"
        />
      </div>
      <div class="background-title">
        <div>{{ background.name }}</div>
        <div style="display: flex; gap: 8px;">
          <Button
            :class="['background-select-btn', { selected: isSelected(index) }]"
            @click="selectBackground(background.url, index, background.duration)"
          >
            {{ isSelected(index) ? '已选中' : '选择' }}
          </Button>
          <Button
            class="background-delete-btn"
            @click="deleteBackground(index)"
          >
            删除
          </Button>
        </div>
      </div>
    </BackgroundCard>
  </BackgroundList>
  <Button
    type="big"
    @click="triggerUpload"
  >上传自定义背景</Button>
  <Button
    type="big"
    @click="openBackgroundFolder"
  >打开背景文件夹</Button>
  <input
    multiple
    type="file"
    class="hidden"
    ref="uploadInput"
    @change="handleFileUpload"
    :accept="getfileType"
  />
</template>

<style scoped>
.background-image-container::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(to bottom, transparent 60%, rgba(0, 0, 0, 0.3) 100%);
  z-index: 1;
  pointer-events: none;
}

.background-image-container {
  flex: 1;
  /* 占据剩余空间 */
  position: relative;
  overflow: hidden;
}

/* 图片样式 */
.background-image {
  position: relative;
  width: 100%;
  height: 100%;
  object-fit: cover;
  aspect-ratio: 16/9;
  /* 保持图片比例 */
  transition: transform 0.3s ease;
}

/* 底部信息区域 */
/* 修改卡片底部背景为毛玻璃效果 */
.background-title {
  padding: 12px 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: rgba(255, 255, 255, 0.15);
  /* 更透明的背景 */
  backdrop-filter: blur(10px);
  /* 毛玻璃效果 */
  -webkit-backdrop-filter: blur(10px);
  /* Safari 支持 */
  border-top: 1px solid rgba(255, 255, 255, 0.2);
  /* 更柔和的边框 */
  position: relative;
  z-index: 2;
}

/* 标题文本样式 */
/* 标题文字颜色调整以适应毛玻璃背景 */
.background-title::before {
  content: attr(data-title);
  font-weight: 500;
  color: rgba(255, 255, 255, 0.9);
  /* 更亮的文字颜色 */
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 70%;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
}

.background-delete-btn,
.background-select-btn {
  padding: 6px 12px;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

/* 选择按钮 */
.background-select-btn {
  background: #4f46e5;
}

.background-select-btn:hover {
  background: #4338ca;
  transform: translateY(-1px);
}

.background-delete-btn {
  background: #ef4444;

  &:hover {
    background: #b91c1c;
    transform: translateY(-1px);
  }
}

.background-select-btn:active {
  transform: translateY(0);
}

.effect-list {
  display: flex;
  justify-content: space-around;
  gap: 20px;
  align-items: center;
}

@media (max-width: 768px) {

  /*什么？你问我为什么这里是character-grid? 灵式编程懂不懂！ */
  .character-grid {
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  }
}


/* 已选中按钮样式 */
.background-select-btn.selected {
  background-color: #10b981 !important;
}
</style>
