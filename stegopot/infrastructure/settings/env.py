"""环境变量文件加载工具。"""

from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path


def load_env_file(
    path: str | os.PathLike[str] = ".env",
    *,
    override: bool = False,
) -> Mapping[str, str]:
  """从 .env 文件加载环境变量。

  参数：
    path: .env 文件路径；默认读取当前工作目录下的 .env。
    override: 是否覆盖进程中已经存在的同名环境变量。

  返回：
    本次成功加载到进程环境变量中的键值映射。
  """
  loaded: dict[str, str] = {}
  for key, value in read_env_file(path).items():
    if override or key not in os.environ:
      os.environ[key] = value
      loaded[key] = value
  return loaded


def read_env_file(path: str | os.PathLike[str]) -> dict[str, str]:
  """读取凭证文件，不修改进程环境，避免多个工作区之间相互污染。

  参数：
    path: UTF-8 编码的 KEY=value 文件；不存在时返回空映射。

  返回：
    解析后的字符串映射。调用者不得打印或持久化完整返回值。
    格式错误抛出 ValueError，只报告行号而不回显凭证。
  """
  env_path = Path(path)
  if not env_path.exists():
    return {}
  loaded: dict[str, str] = {}
  for line_number, raw_line in enumerate(
      env_path.read_text(encoding="utf-8-sig").splitlines(),
      start=1,
  ):
    line = raw_line.strip()
    if not line or line.startswith("#"):
      continue
    if "=" not in line:
      raise ValueError(f"{env_path} 第 {line_number} 行不是 KEY=value 格式。")
    key, value = line.split("=", 1)
    key = key.strip()
    if not key.isidentifier():
      raise ValueError(f"{env_path} 第 {line_number} 行变量名无效。")
    parsed_value = _parse_env_value(value.strip())
    loaded[key] = parsed_value
  return loaded


def _parse_env_value(value: str) -> str:
  """解析 .env 中的变量值。

  参数：
    value: 等号右侧的原始字符串。

  返回：
    去掉外层引号和行尾注释后的变量值。
  """
  if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
    return value[1:-1]
  if "#" in value:
    value = value.split("#", 1)[0].rstrip()
  return value
