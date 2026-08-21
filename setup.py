"""裁剪后多智能体沙箱骨架的安装脚本。"""

from setuptools import find_packages
from setuptools import setup


setup(
    name="stegopot-skeleton",
    version="0.2.0",
    license="Apache 2.0",
    license_files=["LICENSE"],
    description="支持自定义拓扑和 LLM 节点的多智能体实验框架。",
    packages=find_packages(include=["meltingpot", "meltingpot.*"]),
    python_requires=">=3.11",
    install_requires=[],
)
