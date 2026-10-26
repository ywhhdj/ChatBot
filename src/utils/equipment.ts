export function isAndroid() {
  return /Android/i.test(navigator.userAgent);
}

export function isIOS() {
  return /iPhone|iPad|iPod/i.test(navigator.userAgent);
}

export function isMobile() {
  return isAndroid() || isIOS();
}

export function isDesktop() {
  return !!(window.qt && window.qt.webChannelTransport);
}