"""按需加载项目内置的 Dwinovo StegoKit。"""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
import sys
import threading
from types import ModuleType


class BundledStegoKitError(ImportError):
  """内置 StegoKit 缺失、未初始化或依赖不完整时抛出的异常。"""


_LOAD_LOCK = threading.Lock()


def bundled_stegokit_path() -> Path:
  """返回项目内 StegoKit 上游仓库的绝对路径。

  返回：
    stegopot/infrastructure/vendor/stego-kit 对应的绝对路径。
  """
  return Path(__file__).resolve().parents[2] / "vendor" / "stego-kit"


def load_stegokit() -> ModuleType:
  """加载项目内置的 ``stegokit`` Python 包。

  该函数只在首次使用隐写功能时修改模块搜索路径并导入 StegoKit，
  因此普通多智能体运行不需要提前导入 PyTorch 或 Transformers。

  返回：
    已加载的 ``stegokit`` 模块。

  异常：
    BundledStegoKitError: 子模块未初始化，或缺少 StegoKit 运行依赖。
  """
  with _LOAD_LOCK:
    loaded = sys.modules.get("stegokit")
    if loaded is not None:
      return loaded

    repository = bundled_stegokit_path()
    package_entry = repository / "stegokit" / "__init__.py"
    installed_spec = importlib.util.find_spec("stegokit")
    if not package_entry.is_file() and installed_spec is None:
      raise BundledStegoKitError(
          "项目内 StegoKit 子模块尚未初始化。请在项目根目录运行 "
          "`git submodule update --init --recursive`。"
      )

    if package_entry.is_file():
      repository_text = str(repository)
      if repository_text not in sys.path:
        sys.path.insert(0, repository_text)

    try:
      return importlib.import_module("stegokit")
    except ModuleNotFoundError as exc:
      missing = exc.name or "未知模块"
      raise BundledStegoKitError(
          "无法加载项目内 StegoKit，缺少运行依赖 "
          f"`{missing}`。请运行 `python -m pip install -e \".[stego]\"`。"
      ) from exc
    except ImportError as exc:
      raise BundledStegoKitError(
          f"项目内 StegoKit 导入失败：{exc}"
      ) from exc
