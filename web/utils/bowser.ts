export const supportedSetSinkId = () => {
  if (typeof HTMLMediaElement === "undefined") return false;
  return "setSinkId" in HTMLMediaElement.prototype;
};