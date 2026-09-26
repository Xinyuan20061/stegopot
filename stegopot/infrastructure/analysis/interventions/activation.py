"""上下文匹配的 Activation 反事实替换。"""

from collections.abc import Sequence
import math

from stegopot.domain.interface.intervention import VectorOutcomeEvaluator
from stegopot.domain.model.attribution import InterventionResult, InterventionSpec
from stegopot.domain.model.localization import SurfaceKind


class MatchedActivationPatcher:
  """用匹配上下文、不同秘密样本的激活替换源激活。"""

  def __init__(
      self,
      *,
      source: Sequence[float],
      donor: Sequence[float],
      evaluator: VectorOutcomeEvaluator,
      baseline_recovery: float,
      chance_recovery: float,
  ) -> None:
    """初始化干预运行器。

    参数：
      source: 未干预源样本的激活向量。
      donor: 上下文匹配但秘密不同的供体激活向量。
      evaluator: 将替换后激活送回模型并返回秘密恢复率的回调。
      baseline_recovery: 同一源样本未干预时的秘密恢复率。
      chance_recovery: 当前秘密分布下的随机猜测恢复率。
    """
    self.source = _vector(source, "source")
    self.donor = _vector(donor, "donor")
    if len(self.source) != len(self.donor):
      raise ValueError("source 与 donor 激活形状必须一致")
    self.evaluator = evaluator
    self.baseline_recovery = float(baseline_recovery)
    self.chance_recovery = float(chance_recovery)

  def run(self, spec: InterventionSpec) -> InterventionResult:
    """执行 matched patch；不使用置零激活制造分布外扰动。"""
    if spec.target.surface is not SurfaceKind.ACTIVATION:
      raise ValueError("MatchedActivationPatcher 只支持 activation 表面")
    if spec.donor_sample_id is None:
      raise ValueError("matched activation patch 必须声明 donor_sample_id")
    intervened = float(self.evaluator(self.donor))
    denominator = self.baseline_recovery - self.chance_recovery
    if denominator <= 0:
      raise ValueError("baseline_recovery 必须高于 chance_recovery")
    causal_score = min(1.0, max(0.0, (self.baseline_recovery - intervened) / denominator))
    return InterventionResult(spec, self.baseline_recovery, intervened,
                              self.chance_recovery, causal_score)


def _vector(value: Sequence[float], name: str) -> tuple[float, ...]:
  """验证反事实表征为有限数向量。"""
  result = tuple(float(item) for item in value)
  if not result or any(not math.isfinite(item) for item in result):
    raise ValueError(f"{name} 必须是非空有限数向量")
  return result
