"""Agent 行为轨迹的固定结构化特征。"""

from collections import Counter
from collections.abc import Sequence


def behavior_features(actions: Sequence[str]) -> dict[str, object]:
  """按动作类型计数并保留顺序，不读取策略私有状态。"""
  values = tuple(str(item) for item in actions)
  return {"count": len(values), "action_counts": dict(sorted(Counter(values).items())),
          "sequence": list(values)}

