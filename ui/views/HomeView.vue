<template>
  <div class="main-page">
    <GamePanel />
    <aside class="main-aside">
      <p class="aside-quote">「今天，也来聊聊天吧。」</p>
    </aside>
  </div>
</template>

<style scoped>
.main-page {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  gap: 3vw;
  width: 80%;
  min-height: 0;
}

.main-aside {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 14px;
  flex: 0 1 auto;
}

.aside-quote {
  margin: 0;
  font-family: 'Maoken Assorted Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 18px;
  color: #fff;
  opacity: 0.8;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.6);
  letter-spacing: 1px;
}

@media screen and (max-width: 900px) {
  .main-aside {
    display: none;
  }
}

@media screen and (max-width: 768px) {
  .main-page {
    width: 95%;
  }
}
</style>
