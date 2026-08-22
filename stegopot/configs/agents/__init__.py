"""智能体配置骨架。"""

from __future__ import annotations

from collections.abc import Mapping
import dataclasses
from typing import Any


@dataclasses.dataclass(frozen=True)
class AgentConfig:
  """单个智能体节点的配置。

  属性：
    name: 智能体配置名称，通常用于注册和引用。
    type: 智能体类型，例如 "llm"、"rule" 或 "mock"。
    role: 智能体在实验中的角色，例如 "sender"、"receiver" 或
      "auditor"。
    provider: 模型供应商，例如 "deepseek"；非 LLM 智能体可以为空。
    model: 使用的模型名称；非 LLM 智能体可以为空。
    system_prompt: 传给 LLM 节点的系统提示词。
    temperature: 模型采样温度；由具体客户端决定是否使用。
    max_tokens: 单次模型响应的最大 token 数；由具体客户端决定是否使用。
    api_key_env: 保存模型 API 密钥的环境变量名称。
    settings: 额外配置，供具体智能体实现自行解释。
  """

  name: str
  type: str
  role: str
  provider: str | None = None
  model: str | None = None
  system_prompt: str = ""
  temperature: float | None = None
  max_tokens: int | None = None
  api_key_env: str | None = None
  settings: Mapping[str, Any] = dataclasses.field(default_factory=dict)


AGENT_CONFIGS: dict[str, AgentConfig] = {}
