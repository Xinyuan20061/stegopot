"""与具体算法无关的运行时干预声明。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from stegopot.domain.model.reference import TensorRef


def _description(text: str) -> dict[str, str]:
  return {"description": text}


@dataclass(frozen=True)
class InterventionContext:
  """传给条件和算子的最小可信运行信息。"""

  run_id: str = field(metadata=_description("当前受控前向的运行 ID。"))
  target: TensorRef = field(metadata=_description("当前正在处理的张量位置。"))
  step_index: int | None = field(
      default=None, metadata=_description("生成步骤；普通前向为空。"))
  metadata: Mapping[str, Any] = field(
      default_factory=dict, metadata=_description("不含张量和秘密的附加信息。"))

  def __post_init__(self) -> None:
    if not self.run_id:
      raise ValueError("run_id 不能为空")
    object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class Intervention:
  """在目标张量上调用外部算子的通用声明。"""

  intervention_id: str = field(metadata=_description("干预稳定 ID。"))
  target: TensorRef = field(metadata=_description("需要修改的内部张量位置。"))
  operator: Callable[[Any, InterventionContext], Any] = field(
      repr=False, metadata=_description("输入当前张量并返回同形状替换值的算子。"))
  observe: TensorRef | None = field(
      default=None, metadata=_description("条件干预读取的位置；为空表示无条件执行。"))
  condition: Callable[[Any, InterventionContext], bool] | None = field(
      default=None, repr=False, metadata=_description("根据 observe 张量决定是否触发。"))
  priority: int = field(
      default=0, metadata=_description("同一位置多个干预的升序执行优先级。"))
  metadata: Mapping[str, Any] = field(
      default_factory=dict, metadata=_description("不含张量原值的干预参数摘要。"))

  def __post_init__(self) -> None:
    if not isinstance(self.intervention_id, str) or not self.intervention_id.strip():
      raise ValueError("intervention_id 必须是非空字符串")
    if not callable(self.operator):
      raise TypeError("operator 必须可调用")
    if (self.observe is None) != (self.condition is None):
      raise ValueError("observe 和 condition 必须同时提供或同时为空")
    if self.condition is not None and not callable(self.condition):
      raise TypeError("condition 必须可调用")
    if type(self.priority) is not int:
      raise TypeError("priority 必须是整数")
    object.__setattr__(self, "intervention_id", self.intervention_id.strip())
    object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

  @property
  def required_refs(self) -> tuple[TensorRef, ...]:
    """返回适配器需要解析的观察和目标位置。"""
    return (self.target,) if self.observe is None else (self.observe, self.target)
