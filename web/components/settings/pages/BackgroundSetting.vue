<template>
  <MenuItem title="选择背景">
  <BackGroundSelect />
  </MenuItem>
  <MenuItem
    title="动画设置"
    size="small"
  >
  <AnimationSetting />
  </MenuItem>
</template>

<style scoped>
/*什么？你问我为什么这里是character-grid? 灵式编程懂不懂！ */
.character-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 20px;
  padding-bottom: 20px;
  width: 100%;
}

/* 图片容器 */
/* 图片容器添加伪元素增强效果 */
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