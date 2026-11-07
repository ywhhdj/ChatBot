"""重计算门面：Rust 优先、纯 Python 回退、常数一致性校验。"""

from .kernel import MemoryKernel, get_kernel, reset_kernel

__all__ = ["MemoryKernel", "get_kernel", "reset_kernel"]
