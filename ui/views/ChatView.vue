<template>
  <header style="margin: 10px;">
    <ChatNav />
  </header>
  <main>
    <div class="image"></div>
    <div class="dialog">
      <ChatDialog />
    </div>
  </main>
  <!-- <AgentSidePanel visible /> -->
</template>

<style scoped>
.image {
  position: absolute;
}

.dialog {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 2;
}
</style>
