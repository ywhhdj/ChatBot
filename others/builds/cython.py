from setuptools import find_packages, setup
from Cython.Build import cythonize
import numpy as np

CYTHON_MODULES=[
    "api",
    "characters",
    "logger",
    "router",
    "tools",
    "manager",
    "events",
    "services",
    "devices",
    "pipeline",
    "memory"
]
m=[f"modules/{mod}/**/*.py" for mod in CYTHON_MODULES]

# 仅针对性能瓶颈模块进行编译
ext_modules = cythonize(
    m, 
    compiler_directives={
        'language_level': "3",
        'boundscheck': False,      # 关闭边界检查（性能提升 15-20%）
        'wraparound': False,       # 关闭负数索引
        'initializedcheck': False, # 关闭初始化检查
        'cdivision': True,         # C风格除法
        'profile': False,          # 关闭调试信息
        'emit_code_comments': False, # 减小体积
    }
)

setup(
    name="ProjectOptimized",
    packages=find_packages(where="modules"),
    package_dir={"": "modules"},
    ext_modules=ext_modules,
    include_dirs=[np.get_include()] # 支持numpy
)
