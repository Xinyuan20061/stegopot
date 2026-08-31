"""通过可插拔 StegoTool 处理隐写消息的环境基底。"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
import dataclasses
from typing import Any, TYPE_CHECKING

from stegopot.domain.interface import StegoEmbedRequest
from stegopot.domain.interface import StegoEmbedResult
from stegopot.domain.interface import StegoExtractRequest
from stegopot.domain.interface import StegoExtractResult
from stegopot.domain.interface import StegoGenerationConfig
from stegopot.domain.interface import StegoTool
from stegopot.domain.interface import SubstrateEvent
from stegopot.domain.interface import SubstrateResetContext
from stegopot.domain.interface import SubstrateStepContext
from stegopot.domain.interface import SubstrateStepResult
from stegopot.infrastructure.substrates.communication import CommunicationSubstrate

if TYPE_CHECKING:
  from stegopot.domain.model import AgentMessage


class SubstrateProcessingError(RuntimeError):
  """环境基底无法完成消息变换或解码时抛出的异常。"""


@dataclasses.dataclass(frozen=True)
class _StegoRequestBundle:
  """一次隐写动作内部使用的编码和解码参数集合。"""

  embed_request: StegoEmbedRequest
  decode_config: Any | None
  decode_material: Any | None


class SteganographySubstrate(CommunicationSubstrate):
  """识别动作隐写元数据、生成载密文本并为授权节点解码。

  发送节点通过 ``AgentAction.metadata["stego"]`` 提交隐写请求。公开
  消息只包含生成文本和原有非隐写元数据；秘密比特、算法配置和安全
  材料保留在环境内部，不会复制到接收者消息元数据。
  """

  def __init__(
      self,
      *,
      tool: StegoTool,
      decoder_nodes: Collection[str] = (),
      metadata_key: str = "stego",
      fail_fast: bool = True,
  ) -> None:
    """初始化隐写环境。

    参数：
      tool: 实现 StegoTool 协议的隐写编码和解码工具。
      decoder_nodes: 被授权查看解码比特的接收节点 ID 集合。
      metadata_key: AgentAction.metadata 中保存隐写请求的字段名。
      fail_fast: 隐写失败时是否立即终止；为 False 时投递原始文本，
        但会删除包含秘密的请求元数据并记录 stego_error 事件。
    """
    super().__init__()
    if not isinstance(metadata_key, str) or not metadata_key.strip():
      raise ValueError("metadata_key 必须是非空字符串")
    if not callable(getattr(tool, "embed", None)):
      raise TypeError("tool 必须实现 embed(request)")
    if not callable(getattr(tool, "extract", None)):
      raise TypeError("tool 必须实现 extract(request)")
    self._tool = tool
    self._decoder_nodes = frozenset(decoder_nodes)
    self._metadata_key = metadata_key.strip()
    self._fail_fast = bool(fail_fast)
    self._decoded_by_node: dict[str, list[dict[str, Any]]] = {}
    self._encoded_message_count = 0
    self._decoded_message_count = 0
    self._failed_message_count = 0

  def reset(self, context: SubstrateResetContext) -> None:
    """重置通信状态和所有节点的私有解码记录。

    参数：
      context: 全局任务、节点、共享上下文和拓扑快照。
    """
    unknown_decoders = self._decoder_nodes - set(context.node_ids)
    if unknown_decoders:
      raise ValueError(f"decoder_nodes 包含未知节点：{sorted(unknown_decoders)}")
    super().reset(context)
    self._decoded_by_node = {node_id: [] for node_id in context.node_ids}
    self._encoded_message_count = 0
    self._decoded_message_count = 0
    self._failed_message_count = 0

  def observe(self, node_id: str) -> Mapping[str, Any]:
    """返回基础环境状态和当前节点有权查看的解码结果。

    参数：
      node_id: 请求观察的节点 ID。

    返回：
      基础通信状态以及该节点的私有 decoded_messages 列表。
    """
    observation = dict(super().observe(node_id))
    observation["steganography"] = {
        "can_decode": node_id in self._decoder_nodes,
        "decoded_messages": [
            dict(item) for item in self._decoded_by_node[node_id]
        ],
    }
    return observation

  def step(self, context: SubstrateStepContext) -> SubstrateStepResult:
    """处理本轮隐写请求，再交给默认通信环境完成投递。

    参数：
      context: 当前轮次、节点动作和拓扑路由后的候选消息。

    返回：
      携带隐写文本的实际消息、环境事件和基础零奖励。
    """
    encoded_by_sender: dict[
        str, tuple[_StegoRequestBundle, StegoEmbedResult]
    ] = {}
    decoded_by_sender: dict[str, StegoExtractResult] = {}
    processed_messages: list[AgentMessage] = []
    stego_events: list[SubstrateEvent] = []

    for message in context.messages:
      safe_message: AgentMessage | None = None
      request_payload = message.metadata.get(self._metadata_key)
      if request_payload is None:
        processed_messages.append(message)
        continue
      try:
        bundle, encode_result = encoded_by_sender.get(
            message.sender,
            (None, None),
        )
        if bundle is None or encode_result is None:
          bundle = self._build_request_bundle(message, request_payload)
          encode_result = self._tool.embed(bundle.embed_request)
          encoded_by_sender[message.sender] = (bundle, encode_result)
          self._encoded_message_count += 1
        transformed = self._build_public_message(message, encode_result)
        safe_message = transformed
        stego_events.append(SubstrateEvent(
            kind="stego_embedded",
            round_index=context.round_index,
            actor=message.sender,
            target=message.recipient,
            metadata={
                "message_id": message.message_id,
                "algorithm": bundle.embed_request.algorithm,
                "consumed_bits": encode_result.consumed_bits,
                "generated_token_ids": list(
                    encode_result.generated_token_ids
                ),
                "encode_time_seconds": encode_result.encode_time_seconds,
                "embedding_capacity": encode_result.embedding_capacity,
                "generation": dataclasses.asdict(
                    bundle.embed_request.generation
                ),
            },
        ))

        if message.recipient in self._decoder_nodes:
          decode_result = decoded_by_sender.get(message.sender)
          if decode_result is None:
            decode_result = self._tool.extract(StegoExtractRequest(
                algorithm=bundle.embed_request.algorithm,
                generated_token_ids=encode_result.generated_token_ids,
                messages=bundle.embed_request.messages,
                generation=bundle.embed_request.generation,
                max_bits=encode_result.consumed_bits,
                config=bundle.decode_config,
                material=bundle.decode_material,
            ))
            decoded_by_sender[message.sender] = decode_result
          self._decoded_by_node[message.recipient].append({
              "message_id": message.message_id,
              "sender": message.sender,
              "algorithm": bundle.embed_request.algorithm,
              "bits": decode_result.bits,
              "decode_time_seconds": decode_result.decode_time_seconds,
              "metadata": dict(decode_result.metadata),
          })
          self._decoded_message_count += 1
          stego_events.append(SubstrateEvent(
              kind="stego_decoded",
              round_index=context.round_index,
              actor=message.recipient,
              target=message.sender,
              metadata={
                  "message_id": message.message_id,
                  "algorithm": bundle.embed_request.algorithm,
                  "decoded_bit_count": len(decode_result.bits),
              },
          ))
        processed_messages.append(transformed)
      except Exception as exc:  # pylint: disable=broad-exception-caught
        if self._fail_fast:
          raise SubstrateProcessingError(
              f"消息 {message.message_id} 的隐写处理失败：{exc}"
          ) from exc
        self._failed_message_count += 1
        processed_messages.append(
            safe_message or self._build_fallback_message(message, exc)
        )
        stego_events.append(SubstrateEvent(
            kind="stego_error",
            round_index=context.round_index,
            actor=message.sender,
            target=message.recipient,
            metadata={
                "message_id": message.message_id,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        ))

    base_result = super().step(dataclasses.replace(
        context,
        messages=tuple(processed_messages),
    ))
    return SubstrateStepResult(
        messages=base_result.messages,
        rewards=base_result.rewards,
        events=tuple(stego_events) + tuple(base_result.events),
        done=base_result.done,
        termination_reason=base_result.termination_reason,
        info={
            **base_result.info,
            "encoded_message_count": self._encoded_message_count,
            "decoded_message_count": self._decoded_message_count,
            "failed_message_count": self._failed_message_count,
        },
    )

  def state(self) -> Mapping[str, Any]:
    """返回不包含秘密比特和安全材料的隐写环境状态。"""
    return {
        **super().state(),
        "decoder_nodes": sorted(self._decoder_nodes),
        "encoded_message_count": self._encoded_message_count,
        "decoded_message_count": self._decoded_message_count,
        "failed_message_count": self._failed_message_count,
    }

  def close(self) -> None:
    """释放隐写工具持有的本地模型资源。"""
    close = getattr(self._tool, "close", None)
    if callable(close):
      close()

  def _build_request_bundle(
      self,
      message: AgentMessage,
      payload: Any,
  ) -> _StegoRequestBundle:
    """从动作元数据构造工具无关的编码和解码请求参数。"""
    if not isinstance(payload, Mapping):
      raise TypeError(f"{self._metadata_key} 必须是映射")
    data = dict(payload)
    messages = data.get("messages") or (
        {"role": "user", "content": message.content},
    )
    generation_data = data.get("generation")
    if generation_data is not None and not isinstance(
        generation_data, Mapping
    ):
      raise TypeError("stego.generation 必须是映射")
    shared_config = data.get("config")
    shared_material = data.get("material")
    embed_request = StegoEmbedRequest(
        algorithm=str(data.get("algorithm") or "ac"),
        secret_bits=data.get("secret_bits"),
        messages=messages,
        generation=StegoGenerationConfig.from_mapping(generation_data),
        config=data.get("encode_config", shared_config),
        material=data.get("encode_material", shared_material),
    )
    return _StegoRequestBundle(
        embed_request=embed_request,
        decode_config=data.get("decode_config", shared_config),
        decode_material=data.get("decode_material", shared_material),
    )

  def _build_public_message(
      self,
      message: AgentMessage,
      result: StegoEmbedResult,
  ) -> AgentMessage:
    """构造只含自然文本、不向 Agent 暴露隐写标签的投递消息。"""
    metadata = {
        key: value
        for key, value in message.metadata.items()
        if key != self._metadata_key
    }
    return dataclasses.replace(
        message,
        content=result.text,
        metadata=metadata,
    )

  def _build_fallback_message(
      self,
      message: AgentMessage,
      error: Exception,
  ) -> AgentMessage:
    """构造已删除秘密字段的非严格模式回退消息。"""
    metadata = {
        key: value
        for key, value in message.metadata.items()
        if key != self._metadata_key
    }
    metadata["stego_error"] = {
        "error_type": type(error).__name__,
        "error": str(error),
    }
    return dataclasses.replace(message, metadata=metadata)
