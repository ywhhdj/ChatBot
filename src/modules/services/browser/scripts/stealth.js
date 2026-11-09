Object.defineProperty(navigator, 'webdriver', {
  get: () => undefined
});
window.chrome = {
  runtime: {},
  loadTimes: () => { },
  csi: () => { },
  app: {}
};

Object.defineProperty(navigator, 'plugins', {
  get: () => [1, 2, 3, 4, 5]
});

Object.defineProperty(navigator, 'languages', {
  get: () => ['zh-CN', 'zh', 'en']
});

Object.defineProperty(navigator, 'permissions', {
  get: () => ({
    query: (p) => p.name === 'notifications'
      ? Promise.resolve({ state: 'denied' })
      : Promise.resolve({ state: 'granted' })
  })
});
//WebGL 指纹伪装
const getParam = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function (p) {
  if (p === 37445) return 'Google Inc. (Intel)';
  if (p === 37446) return 'ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 vs_5_0 ps_5_0)';
  return getParam.call(this, p);
};