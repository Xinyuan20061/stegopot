"""消息和调用时序特征。"""

from collections.abc import Sequence
import math


def timing_features(timestamps: Sequence[float]) -> dict[str, object]:
  """把绝对时间转换为相邻间隔，避免把运行日期当作秘密特征。"""
  values = tuple(float(item) for item in timestamps)
  if any(not math.isfinite(item) for item in values):
    raise ValueError("时间戳必须为有限数")
  intervals = [max(0.0, right - left) for left, right in zip(values, values[1:])]
  return {"event_count": len(values), "intervals": intervals,
          "total_duration": sum(intervals)}

