"""模型运行时与研究插件之间的能力声明。"""

from enum import Enum


class Capability(str, Enum):
  """适配器可显式提供、插件可显式要求的原子能力。"""

  FORWARD = "forward"
  GENERATION = "generation"
  TOKEN_STEP_CONTROL = "token_step_control"
  ACTIVATION_READ = "activation_read"
  ACTIVATION_WRITE = "activation_write"
  GRADIENT_READ = "gradient_read"
  AGENT_MESSAGE_HOOK = "agent_message_hook"


class MissingCapabilityError(RuntimeError):
  """运行前发现后端缺少插件所需能力。"""

  def __init__(self, required, available) -> None:
    """保存缺失能力并生成不依赖具体后端的错误消息。"""
    required_values = frozenset(Capability(item) for item in required)
    available_values = frozenset(Capability(item) for item in available)
    self.required = required_values
    self.available = available_values
    self.missing = required_values - available_values
    rendered = ", ".join(sorted(item.value for item in self.missing))
    super().__init__(f"模型后端缺少能力：{rendered}")
