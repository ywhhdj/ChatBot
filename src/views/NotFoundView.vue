<script setup lang="ts">
import { useRouter } from 'vue-router';
const router = useRouter();
</script>

<template>
  <div class="not-found-container">
    <div class="error-visual">
      <div class="error-code">404</div>
    </div>
    <div class="error-content">
      <h1 class="error-title">抱歉，您访问的页面走丢了...</h1>
      <p class="error-description">
        我们找不到您请求的资源。它可能已被移动、删除，或者您输入了一个错误的网址。
      </p>
      <div class="recommend-actions">
        <Button
          type="nav"
          icon="home"
          size="large"
          @click="router.back()"
          class="home-button"
        >
          立即返回上一页
        </Button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* -------------------- 整体容器 -------------------- */
.not-found-container {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 80vh;
  /* 确保占据屏幕大部分高度 */
  text-align: center;
  padding: 40px 20px;
  background-color: rgba(0, 0, 0, 0.15);
  /* 柔和的背景色 */
  font-family: 'Inter', 'Helvetica Neue', Helvetica, Arial, sans-serif;
}

/* -------------------- 视觉元素 -------------------- */
.error-visual {
  position: relative;
  margin-bottom: 40px;
}

.error-code {
  font-size: 180px;
  font-weight: 900;
  color: var(--accent-color);
  opacity: 0.25;
  position: absolute;
  top: -60px;
  left: 50%;
  transform: translateX(-50%);
  letter-spacing: 10px;
  user-select: none;
}

.error-illustration i {
  font-size: 80px;
  color: var(--accent-color);
  padding: 20px;
  border-radius: 50%;
  background-color: #ecf5ff;
  box-shadow: 0 5px 15px rgba(64, 158, 255, 0.1);
}

/* -------------------- 文本内容 -------------------- */
.error-content {
  max-width: 600px;
  z-index: 10;
}

.error-title {
  font-size: 36px;
  font-weight: 700;
  color: #303133;
  margin-top: 0;
  margin-bottom: 15px;
}

.error-description {
  font-size: 16px;
  color: #606266;
  margin-bottom: 30px;
}

/* -------------------- 操作区域 -------------------- */
.recommend-actions {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.home-button {
  margin-bottom: 30px;
  padding: 15px 30px;
  font-size: 18px;
  border-radius: 8px;
  font-weight: 600;
}



/* -------------------- 响应式调整 -------------------- */
@media (max-width: 768px) {
  .error-code {
    font-size: 120px;
    top: -40px;
  }

  .error-title {
    font-size: 28px;
  }

}
</style>