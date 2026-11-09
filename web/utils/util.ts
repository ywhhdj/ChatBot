export async function saveJsonFile(filename: string, data: any) {
  return new Promise<void>((resolve, reject) => {
    if (!filename) {
      filename = new Date().toISOString() + '.json';
    }
    const blob = new Blob([JSON.stringify(data)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
    resolve();
  });
}

export async function loadJsonFile<T = any>(filename: string): Promise<T> {
  const response = await fetch(filename, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
  });
  const data = await response.json();
  if (typeof data === 'string') {
    return JSON.parse(data);
  }
  return data;
}

export const JSONparse = (text: string) => {
  try {
    return JSON.parse(text);
  } catch (e) {
    return null;
  }
};

export const loadStorage = (key: string) => {
  return JSONparse(localStorage.getItem(key) || '{}');
};

export const saveStorage = (key: string, value: any) => {
  localStorage.setItem(key, JSON.stringify(value));
};

export const getFileExtension = (filename: string) => {
  return filename.split('.').pop()?.toLowerCase() || '';
};

export function throttle<T extends (...args: any[]) => any>(
  fn: T,
  delay: number
): T {
  let lastTime = 0;
  return function (this: any, ...args: Parameters<T>) {
    const now = Date.now();
    if (now - lastTime >= delay) {
      fn.apply(this, args);
      lastTime = now;
    }
  } as T;
}