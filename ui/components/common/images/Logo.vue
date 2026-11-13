<template>
  <h1 class="logo">
    <div class="logo-prefix">Neuro</div>
    <div class="logo-suffix">Chat</div>
  </h1>
</template>

<style scoped>
.logo {
  -webkit-text-stroke: 8px white;
  paint-order: stroke;
  font-family: "Quicksand", "Noto Sans SC", sans-serif;
  color: rgb(149, 47, 47);
  paint-order: stroke;
  letter-spacing: -0.05em;
  color: rgba(255, 255, 255, 0.8);
  line-height: 0.8;
  font-style: italic;
  font-weight: 900;
  z-index: 10;
  position: relative;
  font-size: 100%;
}

.logo-prefix {
  --tw-gradient-from: #ff7eb3 0%;
  --tw-gradient-to: #e11d48 100%;
  --tw-gradient-stops: var(--tw-gradient-from), var(--tw-gradient-to);
  --tw-drop-shadow: drop-shadow(4px 4px 0px rgba(255, 182, 193, 1));
}

.logo-suffix {
  --tw-gradient-from: #60a5fa 0%;
  --tw-gradient-to: #2563eb 100%;
  --tw-gradient-stops: var(--tw-gradient-from), var(--tw-gradient-to);
  --tw-drop-shadow: drop-shadow(4px 4px 0px rgba(147, 197, 253, 1));
  margin-left: 6rem;
}

div {
  color: transparent;
  background-clip: text;
  filter: var(--tw-drop-shadow);
  background-image: linear-gradient(to bottom, var(--tw-gradient-stops));
}
</style>