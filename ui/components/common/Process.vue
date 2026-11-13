<script setup lang="ts">
</script>

<template>
  <div class="progressBar visible">
    <div class="block">
      <div class="box">
        <p class="number"><span class="num">72</span><span class="sub">%</span></p>
        <p class="title">下载进度</p>
      </div><span
        class="dots"
        style="opacity: 1; transform: rotate(259.2deg);"
      ></span>
      <svg class="svg">
        <defs>
          <linearGradient id="gradientStyle">
            <stop
              offset="0%"
              stop-color="#56CB7F"
            ></stop>
            <stop
              offset="100%"
              stop-color="#A4E1B9"
            ></stop>
          </linearGradient>
        </defs>
        <circle
          id="circle"
          class="circle"
          cx="67.5"
          cy="67.5"
          r="60"
          style="stroke-dasharray: 376.991; stroke-dashoffset: 105.558;"
        ></circle>
      </svg>
    </div>
  </div>
</template>

<style scoped>
.progressBar {
  z-index: 99999;
  aspect-ratio: 1;
  background-color: #111827;
  border-radius: 50%;
  justify-content: center;
  align-items: center;
  width: 3rem;
  display: flex;
  position: fixed;
  bottom: 50%;
  right: .5rem;
  box-shadow: 5px 5px 10px -5px #00000080, -5px -5px 10px -5px #ffffff80
}

.block {
  width: 2.5rem;
  height: 2.5rem;
  box-shadow: inset 0 0 10px #00000080
}

.block,
.box {
  border-radius: 50%;
  justify-content: center;
  align-items: center;
  display: flex;
  position: relative
}

.box {
  width: calc(100% - .5rem);
  height: calc(100% - .5rem);
  color: var(--text-color);
  flex-direction: column;
  box-shadow: 0 0 10px #00000080
}

.box:before {
  content: "";
  border-radius: 50%;
  width: calc(100% + 28px);
  height: calc(100% + 28px);
  position: absolute
}

.box .number span {
  color: var(--text-color)
}

.box .number .num {
  font-size: .5rem;
  font-weight: 500
}

.box .number .sub {
  font-size: .5rem
}

.box .title {
  color: var(--text-color);
  font-size: .3rem;
  font-weight: 500
}

.dots {
  z-index: 2;
  border-radius: 50%;
  width: 100%;
  height: 100%;
  transition: transform 1s, opacity 1s;
  display: block;
  position: absolute
}

.dots:after {
  content: "";
  /* background-color: var(--fc-background-webkit); */
  border-radius: 50%;
  width: .2rem;
  height: .2rem;
  position: absolute;
  top: .02rem;
  left: 50%;
  transform: translate(-50%);
  box-shadow: 0 0 5px 2px #585858
}

.svg {
  fill: none;
  width: 100%;
  height: 100%;
  position: absolute;
  transform: rotate(-90deg)
}

.circle {
  stroke: url(#gradientStyle);
  stroke-width: .2rem;
  color: #fff;
  transition: stroke-dashoffset 1s;
  animation-duration: 1s;
  animation-timing-function: linear;
  animation-fill-mode: forwards
}

.element {
  opacity: 0;
  /* visibility:hidden; */
  transition: all .5s;
  transform: translateZ(0);
}

.visible {
  opacity: 1;
  visibility: visible;
  transition: all 1s;
  transform: translate(-1rem)
}
</style>