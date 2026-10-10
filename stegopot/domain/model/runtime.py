"""通用模型输入、前向结果和生成参数。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import math
from types import MappingProxyType
from typing import Any, Literal

from stegopot.domain.model.trace import ActivationTrace


def _description(text: str) -> dict[str, str]:
  return {"description": text}


@dataclass(frozen=True)
class ModelInput:
  """由模型适配器解释、核心不推断内容语义的输入。"""

  payload: Any = field(repr=False, metadata=_description("文本、消息、token 或后端张量映射。"))
  format: Literal["text", "messages", "token_ids", "backend"] = field(
      default="text", metadata=_description("payload 的显式格式。"))
  metadata: Mapping[str, Any] = field(
      default_factory=dict, metadata=_description("不包含凭证的输入元数据。"))

  def __post_init__(self) -> None:
    if self.format not in {"text", "messages", "token_ids", "backend"}:
      raise ValueError("ModelInput.format 不受支持")
    object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

@dataclass(frozen=True)
class ForwardResult:
  """一次可控前向的模型输出和选择性轨迹。"""

  output: Any = field(repr=False, metadata=_description("适配器返回的原始模型输出。"))
  trace: ActivationTrace = field(metadata=_description("本次前向的选择性内部状态。"))
  metadata: Mapping[str, Any] = field(
      default_factory=dict, metadata=_description("耗时、设备和后端等复现信息。"))

  def __post_init__(self) -> None:
    object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class GenerationConfig:
  """逐 token 生成会话的后端无关参数。"""

  max_new_tokens: int = field(
      default=64, metadata=_description("最多提交的新 token 数。"))
  temperature: float = field(
      default=0.0, metadata=_description("0 表示 greedy；正数表示采样温度。"))
  top_k: int | None = field(
      default=None, metadata=_description("可选 top-k 截断。"))
  top_p: float | None = field(
      default=None, metadata=_description("可选 nucleus sampling 阈值。"))
  seed: int = field(default=0, metadata=_description("本地采样随机种子。"))
  stop_token_ids: Sequence[int] = field(
      default_factory=tuple, metadata=_description("提交后结束会话的 token ID。"))

  def __post_init__(self) -> None:
    if type(self.max_new_tokens) is not int or self.max_new_tokens < 1:
      raise ValueError("max_new_tokens 必须是正整数")
    temperature = float(self.temperature)
    if not math.isfinite(temperature) or temperature < 0:
      raise ValueError("temperature 必须是非负有限数")
    if self.top_k is not None and (type(self.top_k) is not int or self.top_k < 1):
      raise ValueError("top_k 必须是正整数或 None")
    if self.top_p is not None and not 0 < float(self.top_p) <= 1:
      raise ValueError("top_p 必须位于 (0, 1]")
    stops = tuple(int(item) for item in self.stop_token_ids)
    if any(item < 0 for item in stops):
      raise ValueError("stop_token_ids 不能包含负数")
    object.__setattr__(self, "temperature", temperature)
    object.__setattr__(self, "stop_token_ids", stops)


@dataclass(frozen=True)
class GenerationResult:
  """逐 token 生成会话完成后的标准输出。"""

  token_ids: Sequence[int] = field(metadata=_description("会话提交的全部新 token。"))
  text: str = field(metadata=_description("由适配器 tokenizer 解码的生成文本。"))
  traces: Sequence[ActivationTrace] = field(
      default_factory=tuple, metadata=_description("每一步选择性采集的内部状态。"))
  metadata: Mapping[str, Any] = field(
      default_factory=dict, metadata=_description("停止原因和生成后端信息。"))

  def __post_init__(self) -> None:
    object.__setattr__(self, "token_ids", tuple(int(item) for item in self.token_ids))
    object.__setattr__(self, "traces", tuple(self.traces))
    object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
