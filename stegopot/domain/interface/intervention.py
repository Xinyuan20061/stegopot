"""运行时张量干预算子的最小协议。"""

from typing import Any, Protocol

from stegopot.domain.model.intervention_runtime import InterventionContext


class TensorOperator(Protocol):
  """把选中的张量转换为同形状、同设备和同 dtype 的新张量。"""

  def __call__(self, value: Any, context: InterventionContext) -> Any:
    """返回替换当前选择的值。"""
    ...


__all__ = ["TensorOperator"]
