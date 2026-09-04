"""实验工作区的文件约定；只处理路径和配置发现，不执行实验。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path

from stegopot.infrastructure.settings.env import read_env_file


CONFIG_SUFFIXES = (".yaml", ".yml", ".json")


@dataclass(frozen=True)
class ExperimentWorkspace:
  """用户工作区，与安装在 site-packages 中的框架包相互独立。

  属性：
    root: 工作区根路径；构造时转成绝对路径，不切换进程工作目录。
  """

  root: Path

  def __post_init__(self) -> None:
    """统一 root 的路径形式，不隐式创建任何文件。"""
    object.__setattr__(self, "root", Path(self.root).expanduser().resolve())

  @property
  def configs(self) -> Path:
    """用户 JSON/YAML 配置目录，不存放框架自带实验。"""
    return self.root / "configs"

  @property
  def outputs(self) -> Path:
    """默认结果父目录，由运行器按需创建并生成唯一运行子目录。"""
    return self.root / "outputs"

  def initialize(self) -> Path:
    """创建空 configs 目录并返回路径；不覆盖 .env 或生成默认实验。

    重复调用保持幂等。若 configs 是文件或链接到工作区外则抛出异常。
    此方法不创建结果目录，不安装插件，不发起模型请求。
    """
    self._check_configs_boundary()
    self.configs.mkdir(parents=True, exist_ok=True)
    return self.configs

  def discover(self) -> tuple[Path, ...]:
    """按相对路径排序发现配置文件；目录不存在时返回空元组。

    只接受 JSON/YAML/YML，不跟随工作区外的文件链接。
    本方法不解析配置内容，也不导入任何用户插件。
    """
    self._check_configs_boundary()
    if not self.configs.exists():
      return ()
    if not self.configs.is_dir():
      raise ValueError("configs 必须是目录")
    files = []
    for path in self.configs.rglob("*"):
      if path.is_file() and path.suffix.lower() in CONFIG_SUFFIXES:
        if not path.resolve().is_relative_to(self.configs.resolve()):
          raise ValueError("配置目录中的链接不能指向目录之外")
        files.append(path)
    return tuple(sorted(files, key=lambda path: path.relative_to(self.configs).as_posix()))

  def resolve_config(self, selection: str | Path | None = None) -> Path:
    """选择唯一配置，发生歧义时拒绝自动执行。

    参数：
      selection: configs 内的名称、相对工作区的文件路径或绝对路径。
        为 None 时要求 configs 中恰好只有一个配置；不按字母顺序猜选。

    返回：
      存在的配置文件绝对路径。缺失、歧义和不支持的后缀抛出 ValueError。
      显式路径可以引用工作区外的配置，不改变输出目录与凭证文件的归属。
    """
    if selection is None:
      matches = self.discover()
      if not matches:
        raise ValueError("configs 中没有配置，请先编写自己的 .yaml/.yml/.json 文件")
      if len(matches) != 1:
        raise ValueError("存在多个配置，请用 stegopot list 查看后指定名称运行")
      return matches[0].resolve()
    chosen = Path(selection).expanduser()
    if chosen.suffix.lower() in CONFIG_SUFFIXES:
      candidates = [chosen] if chosen.is_absolute() else [self.root / chosen, self.configs / chosen]
      matches = {path.resolve() for path in candidates if path.is_file()}
    elif chosen.suffix:
      raise ValueError("配置扩展名必须为 .json/.yaml/.yml")
    else:
      name = chosen.as_posix()
      matches = {path.resolve() for path in self.discover()
                 if path.relative_to(self.configs).with_suffix("").as_posix() == name}
    if len(matches) != 1:
      raise ValueError("配置不存在或名称不唯一，请提供完整文件路径")
    return next(iter(matches))

  def environment(
      self, *, env_file: str | Path | None = None, load_env: bool = True,
      overrides: Mapping[str, str] | None = None,
  ) -> dict[str, str]:
    """建立单次运行的环境快照，不写入 os.environ。

    参数：
      env_file: 显式凭证文件，相对路径以工作区为基准；未提供时使用根目录 .env。
      load_env: 是否读取凭证文件；False 时只使用进程环境和 overrides。
      overrides: 嵌入调用者显式提供的环境值，优先于进程环境与文件。

    返回：
      私有环境映射；优先级为 overrides > 进程环境 > .env。
      显式指定不存在的文件会失败；默认 .env 不存在时允许离线运行。
    """
    if not load_env and env_file is not None:
      raise ValueError("关闭 .env 加载时不能同时指定 env_file")
    values = {}
    if load_env:
      path = self.root / (Path(env_file).expanduser() if env_file is not None else ".env")
      if env_file is not None and not path.is_file():
        raise ValueError("指定的环境文件不存在")
      values.update(read_env_file(path))
    values.update(os.environ)
    values.update(overrides or {})
    return values

  def _check_configs_boundary(self) -> None:
    """拒绝将约定的 configs 目录通过链接重定向到工作区外。"""
    if not self.configs.resolve().is_relative_to(self.root):
      raise ValueError("configs 目录不能指向工作区之外")
