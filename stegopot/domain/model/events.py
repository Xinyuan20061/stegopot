"""运行时与实验生命周期事件。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any


def _description(text: str) -> dict[str, str]:
  return {"description": text}


class EventKind(str, Enum):
  """框架保证的通用生命周期事件名称。"""

  RUN_START = "run.start"
  CONFIG_LOAD = "config.load"
  PLUGIN_LOAD = "plugin.load"
  RUNTIME_INIT = "runtime.init"
  DATA_PREPARE = "data.prepare"
  FORWARD_START = "forward.start"
  LAYER_ENTER = "layer.enter"
  ACTIVATION_READY = "activation.ready"
  LAYER_EXIT = "layer.exit"
  FORWARD_END = "forward.end"
  GENERATION_STEP = "generation.step"
  INTERVENTION_APPLIED = "intervention.applied"
  MESSAGE_SEND = "message.send"
  MESSAGE_RECEIVE = "message.receive"
  ANALYZE = "analyze"
  EVALUATE = "evaluate"
  SAVE = "save"
  RUN_END = "run.end"


@dataclass(frozen=True)
class RuntimeEvent:
  """不携带原始张量的可订阅生命周期事件。"""

  kind: str = field(metadata=_description("标准 EventKind 或插件命名事件。"))
  run_id: str = field(metadata=_description("事件所属运行 ID。"))
  timestamp: str = field(
      default_factory=lambda: datetime.now(timezone.utc).isoformat(),
      metadata=_description("UTC ISO-8601 事件时间。"))
  data: Mapping[str, Any] = field(
      default_factory=dict, metadata=_description("不得包含原始张量或凭证的事件数据。"))

  def __post_init__(self) -> None:
    kind = self.kind.value if isinstance(self.kind, EventKind) else str(self.kind).strip()
    if not kind or not self.run_id:
      raise ValueError("RuntimeEvent.kind 和 run_id 不能为空")
    object.__setattr__(self, "kind", kind)
    object.__setattr__(self, "data", MappingProxyType(dict(self.data)))
