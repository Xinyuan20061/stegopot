"""与具体隐写工具无关的请求、结果和工具协议。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import dataclasses
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable


@dataclasses.dataclass(frozen=True)
class StegoGenerationConfig:
  """隐写生成过程使用的通用参数。

  属性：
    max_new_tokens: 编码生成允许产生的最大 token 数。
    temperature: 模型采样温度，必须大于 0。
    top_k: 只保留概率最高的前 k 个 token；为空表示不限制。
    top_p: nucleus sampling 累计概率阈值；为空表示不限制。
    precision: 隐写算法使用的数值精度，必须大于 0。
    stop_on_eos: 是否在 EOS token 处停止；为空时由工具决定。
  """

  max_new_tokens: int = 128
  temperature: float = 1.0
  top_k: int | None = None
  top_p: float | None = None
  precision: int = 52
  stop_on_eos: bool | None = None

  def __post_init__(self) -> None:
    if self.max_new_tokens <= 0:
      raise ValueError("max_new_tokens 必须大于 0")
    if self.temperature <= 0:
      raise ValueError("temperature 必须大于 0")
    if self.top_k is not None and self.top_k <= 0:
      raise ValueError("top_k 必须大于 0")
    if self.top_p is not None and not 0 < self.top_p <= 1:
      raise ValueError("top_p 必须位于 (0, 1] 区间")
    if self.precision <= 0:
      raise ValueError("precision 必须大于 0")
    if self.stop_on_eos is not None and not isinstance(
        self.stop_on_eos,
        bool,
    ):
      raise TypeError("stop_on_eos 必须是 bool 或 None")

  @classmethod
  def from_mapping(
      cls,
      value: Mapping[str, Any] | None,
  ) -> "StegoGenerationConfig":
    """从动作元数据创建并验证生成配置。"""
    return cls(**dict(value or {}))


@dataclasses.dataclass(frozen=True)
class StegoEmbedRequest:
  """提交给 StegoTool 的编码请求。

  属性：
    algorithm: 隐写算法名称。
    secret_bits: 只包含 0 和 1 的秘密比特串。
    messages: 驱动本地生成模型的聊天消息。
    generation: 与具体算法无关的生成参数。
    config: 算法特有配置实例或字段映射。
    material: 算法使用的安全材料实例或字段映射。
  """

  algorithm: str
  secret_bits: str
  messages: Sequence[Mapping[str, Any]]
  generation: StegoGenerationConfig = dataclasses.field(
      default_factory=StegoGenerationConfig
  )
  config: Any | None = None
  material: Any | None = None

  def __post_init__(self) -> None:
    algorithm = self.algorithm.strip() if isinstance(self.algorithm, str) else ""
    if not algorithm:
      raise ValueError("algorithm 必须是非空字符串")
    if not isinstance(self.secret_bits, str):
      raise TypeError("secret_bits 必须是字符串")
    if set(self.secret_bits) - {"0", "1"}:
      raise ValueError("secret_bits 只能包含 0 和 1")
    object.__setattr__(self, "algorithm", algorithm.lower())
    object.__setattr__(self, "messages", _normalize_messages(self.messages))


@dataclasses.dataclass(frozen=True)
class StegoExtractRequest:
  """提交给 StegoTool 的解码请求。

  属性：
    algorithm: 编码阶段使用的隐写算法名称。
    generated_token_ids: 编码阶段生成的 token ID。
    messages: 编码阶段使用的相同聊天消息。
    generation: 与编码端保持一致的生成参数。
    max_bits: 最多提取的秘密比特数。
    config: 算法特有解码配置实例或字段映射。
    material: 与编码端匹配的安全材料实例或字段映射。
  """

  algorithm: str
  generated_token_ids: Sequence[int]
  messages: Sequence[Mapping[str, Any]]
  generation: StegoGenerationConfig = dataclasses.field(
      default_factory=StegoGenerationConfig
  )
  max_bits: int | None = None
  config: Any | None = None
  material: Any | None = None

  def __post_init__(self) -> None:
    algorithm = self.algorithm.strip() if isinstance(self.algorithm, str) else ""
    if not algorithm:
      raise ValueError("algorithm 必须是非空字符串")
    token_ids = tuple(int(token_id) for token_id in self.generated_token_ids)
    if not token_ids:
      raise ValueError("generated_token_ids 不能为空")
    if self.max_bits is not None and self.max_bits < 0:
      raise ValueError("max_bits 不能小于 0")
    object.__setattr__(self, "algorithm", algorithm.lower())
    object.__setattr__(self, "generated_token_ids", token_ids)
    object.__setattr__(self, "messages", _normalize_messages(self.messages))


@dataclasses.dataclass(frozen=True)
class StegoEmbedResult:
  """StegoTool 返回的统一编码结果。"""

  text: str
  generated_token_ids: Sequence[int]
  consumed_bits: int
  encode_time_seconds: float = 0.0
  embedding_capacity: float = 0.0
  metadata: Mapping[str, Any] = dataclasses.field(default_factory=dict)

  def __post_init__(self) -> None:
    if not isinstance(self.text, str) or not self.text.strip():
      raise ValueError("隐写编码结果 text 不能为空")
    if self.consumed_bits < 0:
      raise ValueError("consumed_bits 不能小于 0")
    object.__setattr__(
        self,
        "generated_token_ids",
        tuple(int(token_id) for token_id in self.generated_token_ids),
    )
    object.__setattr__(
        self,
        "metadata",
        MappingProxyType(dict(self.metadata)),
    )


@dataclasses.dataclass(frozen=True)
class StegoExtractResult:
  """StegoTool 返回的统一解码结果。"""

  bits: str
  decode_time_seconds: float = 0.0
  metadata: Mapping[str, Any] = dataclasses.field(default_factory=dict)

  def __post_init__(self) -> None:
    if not isinstance(self.bits, str) or set(self.bits) - {"0", "1"}:
      raise ValueError("解码结果 bits 只能包含 0 和 1")
    object.__setattr__(
        self,
        "metadata",
        MappingProxyType(dict(self.metadata)),
    )


@runtime_checkable
class StegoTool(Protocol):
  """Stego Substrate 依赖的最小隐写工具协议。"""

  def embed(self, request: StegoEmbedRequest) -> StegoEmbedResult:
    """将秘密比特嵌入生成文本。"""
    ...

  def extract(self, request: StegoExtractRequest) -> StegoExtractResult:
    """从生成 token ID 中提取秘密比特。"""
    ...

  def close(self) -> None:
    """释放隐写工具持有的资源。"""
    ...


def _normalize_messages(
    messages: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
  """验证并冻结隐写工具使用的聊天消息。"""
  normalized = []
  for index, message in enumerate(messages):
    if not isinstance(message, Mapping):
      raise TypeError(f"messages[{index}] 必须是映射")
    item = dict(message)
    if "role" not in item:
      raise ValueError(f"messages[{index}] 缺少 role")
    if "content" not in item and "tool_calls" not in item:
      raise ValueError(f"messages[{index}] 缺少 content 或 tool_calls")
    normalized.append(MappingProxyType(item))
  if not normalized:
    raise ValueError("messages 不能为空")
  return tuple(normalized)
