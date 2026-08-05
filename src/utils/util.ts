export function asyncCreateScriptTag(url: string) {
  return new Promise<void>((resolve, reject) => {
    const script = document.createElement('script');
    script.src = url;
    script.type = "module";
    script.onload = () => resolve();
    script.onerror = (error) => reject(error);
    document.head.appendChild(script);
  });
}

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
