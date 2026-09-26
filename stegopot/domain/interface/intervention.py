"""反事实干预与结果重算协议。"""

from collections.abc import Sequence
from typing import Protocol

from stegopot.domain.model.attribution import InterventionResult, InterventionSpec


class InterventionRunner(Protocol):
  """执行预注册干预；实现必须保留未干预基线。"""

  def run(self, spec: InterventionSpec) -> InterventionResult:
    """执行一次干预并返回基线、干预后结果和 chance baseline。"""
    ...


class VectorOutcomeEvaluator(Protocol):
  """用替换后的表征重算秘密恢复结果。"""

  def __call__(self, value: Sequence[float]) -> float:
    """返回范围 [0, 1] 的秘密恢复率。"""
    ...

