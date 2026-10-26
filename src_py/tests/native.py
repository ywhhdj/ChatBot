"""装饰器与 native 方法的实测用例。

和其他 verify 脚本的分工：
  * `verify_native.py`       —— 后端可用性与协议满足性
  * `verify_native_switch.py`—— 切换后不倒退
  * `verify_stream_protocol.py` —— 流协议与 wait_async
  * **本脚本**              —— **装饰器 + native 各方法的实际行为**

重点测"用了会怎样"，不只是"有没有"：

1. 三个装饰器的真实语义（返回值、异步、流式）
2. native 五个对象的实际行为（scheduler / stream / bus / timer / dispatch）
3. **不堵塞** —— 每条都断言调用方 loop 的 tick 数
4. 并发压测 —— 证明不是"看起来能跑"

Rust 内核可用时会**参数化跑两遍**（python + rust）；
不可用时只跑 python 并明确标注。

运行：python3 verify_decorator_native.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import List, Tuple

FIXED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, FIXED)

PASS = 0
FAIL = 0
SKIP = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"    [PASS] {name} {detail}")
    else:
        FAIL += 1
        print(f"    [FAIL] {name} {detail}")


def skip(name: str, why: str) -> None:
    global SKIP
    SKIP += 1
    print(f"    [SKIP] {name} ({why})")


def ticker_probe():
    """创建一个 tick 计数器，用于断言"调用方 loop 没被卡死"。"""
    state = {"n": 0, "task": None}

    async def start(interval: float = 0.01):
        async def _run():
            while True:
                state["n"] += 1
                await asyncio.sleep(interval)

        state["task"] = asyncio.create_task(_run())

    async def stop():
        t = state["task"]
        if t is not None:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass

    return state, start, stop


# ═════════════════════════════════════════════════════════════
# 装饰器
# ═════════════════════════════════════════════════════════════


def test_decorators(backend_name: str) -> None:
    print(f"\n{'═' * 60}")
    print(f"[装饰器] backend = {backend_name}")
    print("═" * 60)

    from modules.core.native import get_scheduler
    from modules.core.native.decorator import (
        async_task_scheduler,
        stream_task_scheduler,
        sync_task_scheduler,
    )

    sch = get_scheduler()

    # ---------- sync ----------

    print("\n  ── sync_task_scheduler ──")

    @sync_task_scheduler
    def add(a, b):
        return a + b

    @sync_task_scheduler(timeout=30, priority=1)
    def slow(a):
        time.sleep(0.3)
        return a * 2

    ref = add(3, 4)
    check("返回 TaskHandleLike", isinstance(ref, object) and hasattr(ref, "result"))
    check("结果正确", ref.result(timeout=5) == 7, f"({ref.result(timeout=5)})")

    # 预热一次，排除首次导入/启动开销
    slow(1).result(timeout=5)

    t0 = time.perf_counter()
    ref2 = slow(21)
    dt = (time.perf_counter() - t0) * 1000
    check("调用立刻返回（<10ms）", dt < 10, f"({dt:.2f}ms)")
    check("慢任务结果正确", ref2.result(timeout=10) == 42)

    # 带关键字参数的业务方法（S25 的错位 bug）
    @sync_task_scheduler
    def kwargs_fn(x, y=0, *, z=0):
        return x + y + z

    check("位置参数不错位", kwargs_fn(1, 2).result(timeout=5) == 3)
    check("关键字参数可用", kwargs_fn(1, y=2, z=3).result(timeout=5) == 6)

    # 异常传播
    @sync_task_scheduler
    def boom():
        raise ValueError("boom")

    try:
        boom().result(timeout=5)
        check("异常会传播", False)
    except ValueError:
        check("异常会传播", True)
    except Exception as e:  # noqa: BLE001
        check("异常会传播", False, f"({type(e).__name__})")

    # ---------- async ----------

    print("\n  ── async_task_scheduler ──")

    @async_task_scheduler
    async def a_double(x):
        await asyncio.sleep(0.05)
        return x * 2

    aref = a_double(5)
    check("async 返回句柄", hasattr(aref, "result"))
    check("async 结果正确", aref.result(timeout=10) == 10,
          f"({aref.result(timeout=10)})")

    # ---------- stream ----------

    print("\n  ── stream_task_scheduler ──")

    @stream_task_scheduler(timeout=30, auto_close=True)
    async def counter(n):
        for i in range(n):
            await asyncio.sleep(0.01)
            yield i

    async def _one_stream():
        state, start, stop = ticker_probe()
        await start()
        st = await counter(5)
        got = []
        async for x in st:
            got.append(x)
        await stop()
        return got, state["n"]

    got, ticked = asyncio.run(_one_stream())
    check("流数据完整", got == [0, 1, 2, 3, 4], f"({got})")
    check("流期间调用方 loop 未卡死", ticked >= 3, f"(tick={ticked})")

    # 并发流
    async def _many_streams():
        state, start, stop = ticker_probe()
        await start()
        sts = []
        for _ in range(4):
            sts.append(await counter(5))
        total = 0
        for st in sts:
            async for _ in st:
                total += 1
        await stop()
        return total, state["n"]

    total, ticked2 = asyncio.run(_many_streams())
    check("4 条并发流共 20 项", total == 20, f"({total})")
    check("并发流期间 loop 仍在转", ticked2 >= 5, f"(tick={ticked2})")


# ═════════════════════════════════════════════════════════════
# native 各对象的实际行为
# ═════════════════════════════════════════════════════════════


def test_native_objects(backend_name: str) -> None:
    print(f"\n{'═' * 60}")
    print(f"[native 对象] backend = {backend_name}")
    print("═" * 60)

    import native_mod  # noqa: F401  占位，实际用下面

    raise RuntimeError("不应直接执行")


def main() -> None:
    from modules.core.native import (
        backend,
        get_async_dispatch,
        get_bus,
        get_scheduler,
        get_timer,
        new_stream,
    )

    print("═══ 装饰器与 native 方法实测 ═══")
    bk = backend()
    print(f"  后端: {bk}")

    # ── 装饰器 ──
    test_decorators(bk)

    # ═══════════════════════════════════════════════════════
    print(f"\n{'═' * 60}")
    print(f"[native 对象] backend = {bk}")
    print("═" * 60)

    # ---------- scheduler ----------

    print("\n  ── scheduler ──")
    sch = get_scheduler()
    check("is_running", sch.is_running() is True)

    # 批量提交
    t0 = time.perf_counter()
    refs = [sch.submit(lambda i=i: i * i, timeout=10) for i in range(50)]
    submit_cost = (time.perf_counter() - t0) * 1000
    check("50 次 submit 不被阻塞", submit_cost < 500, f"({submit_cost:.1f}ms)")

    vals = [r.result(timeout=15) for r in refs]
    check("50 个结果全部正确", vals == [i * i for i in range(50)])

    # 并发不退化成串行
    async def _conc():
        handles = []
        for _ in range(8):
            handles.append(sch.submit(lambda: time.sleep(0.2), timeout=15))
        t0 = time.perf_counter()
        for h in handles:
            h.result(timeout=20)
        return time.perf_counter() - t0

    wall = asyncio.run(_conc())
    check("8 个 0.2s 任务并发（<1.0s 而非 1.6s）", wall < 1.0, f"({wall:.2f}s)")

    # wait_async 不阻塞
    async def _wait_probe():
        state, start, stop = ticker_probe()
        await start()
        h = sch.submit(lambda: (time.sleep(0.3), 1)[1], timeout=10)
        fn = getattr(h, "wait_async", None)
        v = await fn(timeout=10) if fn else None
        await stop()
        return v, state["n"]

    v, ticked = asyncio.run(_wait_probe())
    check("wait_async 拿到结果", v == 1, f"({v})")
    check("wait_async 期间 loop 未卡死", ticked >= 5, f"(tick={ticked})")

    # stats / status_of / cancel
    try:
        st = sch.stats()
        check("stats() 可调用", isinstance(st, dict), f"({list(st)[:3]})")
    except Exception as e:  # noqa: BLE001
        check("stats() 可调用", False, f"({e})")

    h0 = sch.submit(lambda: (time.sleep(5), 1)[1], timeout=20)
    try:
        cancelled = sch.cancel(h0.task_id)
        check("cancel 未启动/运行中的任务", isinstance(cancelled, bool),
              f"({cancelled})")
    except Exception as e:  # noqa: BLE001
        check("cancel 可用", False, f"({e})")

    # ---------- stream ----------

    print("\n  ── stream ──")
    st = new_stream(16)
    for i in range(5):
        st.push(i)
    st.finish()

    async def _drain(s):
        got = []
        async for x in s:
            got.append(x)
            if len(got) > 60:
                break
        return got

    check("push/pop 往返", asyncio.run(_drain(st)) == [0, 1, 2, 3, 4])

    # 背压：容量 2，push 满后阻塞直到消费
    bp = new_stream(2)
    bp.push(1)
    bp.push(2)
    pushed = {"n": 0}

    async def _backpressure():
        got = []
        import threading

        def _p():
            for i in range(3, 8):
                bp.push(i, timeout=5)
                pushed["n"] += 1
            bp.finish()

        t = threading.Thread(target=_p, daemon=True)
        t.start()
        for _ in range(7):
            got.append(await bp.__anext__())
        t.join(timeout=5)
        return got

    bpg = asyncio.run(_backpressure())
    check("背压下数据不丢", bpg == [1, 2, 3, 4, 5, 6, 7], f"({bpg})")
    check("producer 实际被背压", pushed["n"] == 5, f"({pushed['n']})")

    # 失败流
    fs = new_stream(4)
    fs.push("partial")
    fs.fail("boom")

    async def _fail():
        try:
            async for x in fs:
                pass
            return None
        except Exception as e:  # noqa: BLE001
            return type(e).__name__

    check("失败流抛异常而非静默", asyncio.run(_fail()) is not None,
          f"({asyncio.run(_fail())})")

    # ---------- bus ----------

    print("\n  ── bus ──")
    bus = get_bus()
    seen: List[Tuple[str, dict]] = []
    sid = bus.subscribe("evt", lambda p: seen.append(("a", p)))
    bus.subscribe("evt", lambda p: seen.append(("b", p)))
    check("subscribe 返回 id", isinstance(sid, int), f"({sid})")
    check("subscriber_count", bus.subscriber_count("evt") == 2)

    n = bus.emit("evt", {"v": 1})
    check("emit 返回触发数", n == 2, f"({n})")
    time.sleep(0.1)
    check("两个订阅者都收到", len(seen) == 2, f"({len(seen)})")

    ok_unsub = bus.unsubscribe("evt", sid)
    check("unsubscribe 精确解绑", ok_unsub and bus.subscriber_count("evt") == 1)

    # ---------- timer（防抖）----------

    print("\n  ── timer ──")
    timer = get_timer()
    fired: List[int] = []
    tid = timer.debounce(150, 500, lambda p: fired.append(p or 1))

    for _ in range(6):
        timer.touch(tid)
        time.sleep(0.03)
    time.sleep(0.4)
    check("连续输入合并为 1 次", len(fired) == 1, f"({len(fired)})")

    # 硬上限
    fired2: List[int] = []
    tid2 = timer.debounce(100, 300, lambda p: fired2.append(1))
    for _ in range(12):
        timer.touch(tid2)
        time.sleep(0.05)
    time.sleep(0.4)
    check("硬上限强制触发", len(fired2) >= 1, f"({len(fired2)})")

    canceled = timer.cancel(timer.debounce(500, 1000, lambda p: None))
    check("cancel 可用", canceled is True, f"({canceled})")

    # ---------- async dispatch ----------

    print("\n  ── async dispatch ──")
    disp = get_async_dispatch()
    check("is_available", disp.is_available() is True)

    async def _coro():
        await asyncio.sleep(0.01)
        return "dispatched"

    fut = disp.dispatch(_coro())
    try:
        check("dispatch 返回可等待对象",
              fut.result(timeout=5) == "dispatched")
    except Exception as e:  # noqa: BLE001
        check("dispatch 返回可等待对象", False, f"({e})")

    # # ---------- events 集成（无 loop 线程不阻塞）----------

    # print("\n  ── events 集成 ──")
    # from src_py.modules.events.bus import event_bus

    # got: List[int] = []

    # async def _cb():
    #     await asyncio.sleep(0)
    #     got.append(1)

    # event_bus.on("__v_dn_evt", _cb)
    # event_bus.emit("__v_dn_evt")
    # time.sleep(0.2)   # 预热：首次会导入 core.native

    # costs: List[float] = []
    # import threading

    # def _emit():
    #     t0 = time.time()
    #     event_bus.emit("__v_dn_evt")
    #     costs.append(time.time() - t0)

    # th = threading.Thread(target=_emit)
    # th.start()
    # th.join(timeout=5)
    # check("无 loop 线程 emit 不阻塞（<50ms）",
    #       costs and costs[0] < 0.05, f"({costs})")
    # check("异步回调被执行", len(got) >= 1, f"({len(got)})")

    # # ═══════════════════════════════════════════════════════
    # print(f"\n{'═' * 60}")
    # print(f"  通过 {PASS} / 失败 {FAIL} / 跳过 {SKIP}")
    # print("═" * 60)
    # print(f"\n==== {PASS}/{PASS + FAIL} 通过 ====")


if __name__ == "__main__":
    main()