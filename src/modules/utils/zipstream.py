import asyncio
from typing import Optional
import queue,zipfile,io
from .util import create_daemon_thread

class QueueWriter(io.RawIOBase):
    def __init__(self,queue:asyncio.Queue[bytes],loop: asyncio.AbstractEventLoop):
        self.queue = queue
        self.loop=loop

    def write(self,b:bytes):
        if b:
            fut = asyncio.run_coroutine_threadsafe(
                self.queue.put(bytes(b)), self.loop
            )
            try:
                fut.result(timeout=30)   # 阻塞直到消费者取走
            except Exception as e:
                raise IOError(f"queue put failed: {e}")
        return len(b)
    
    def close(self):
        super().close()
    
    @property
    def writeable(self):
        return True

async def stream_zip(
    files:list[dict[str,str]],
    compression:int=zipfile.ZIP_DEFLATED,
):
    loop = asyncio.get_running_loop()
    aq: asyncio.Queue = asyncio.Queue(maxsize=64)
    sentinel = object()
    err_holder: dict = {}

    async def producer():
        try:
            writer = QueueWriter(aq, loop)
            with zipfile.ZipFile(writer, 'w',
                                 compression=compression,
                                 allowZip64=True) as zf:
                for f in files:
                    with zf.open(f['name'], 'w') as dest:
                        async for chunk in remote_stream(f['url']):
                            dest.write(chunk)
        except Exception as e:
            err_holder['err'] = e
        finally:
            # 用阻塞 put 保证 sentinel 一定放进去
            try:
                fut = asyncio.run_coroutine_threadsafe(
                    aq.put(sentinel), loop
                )
                fut.result(timeout=10)
            except Exception:
                pass

    t = create_daemon_thread(target=producer, name=f'zip-stream')
    t.start()

    try:
        while True:
            item = await aq.get()
            if item is sentinel:
                break
            yield item
    finally:
        # 客户端断开时也保证 producer 能退出
        await asyncio.to_thread(t.join, 5)

    if 'err' in err_holder:
        raise err_holder['err']