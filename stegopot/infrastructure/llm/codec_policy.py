"""通过统一隐写接口操作工具的节点策略，与 StegoKit 实现无关。"""

from collections.abc import Mapping
from typing import Any, Literal

from stegopot.domain.interface.policy import Policy
from stegopot.domain.interface.codec import Carrier, DecodeRequest, EncodeRequest, StegoCodec
from stegopot.domain.model.action import AgentAction
from stegopot.domain.model.communication import CommunicationIntent


class CodecPolicy(Policy):
  """工具驱动的隐写节点，不将算法输出描述成 LLM 自发行为。"""

  def __init__(
      self,
      *,
      codec: StegoCodec,
      mode: Literal["encode", "decode"],
      codec_id: str,
      target: str | None = None,
      active_round: int = 0,
  ) -> None:
    """设置 codec、资源 ID、编码/解码角色、接收者及调用轮次。

    参数：
      codec: 由组合根注入且已经审计包装的隐写编解码器。
      mode: ``encode`` 或 ``decode``。
      codec_id: 配置引用的 codec 资源 ID，用于载体来源审计。
      target: 编码消息的接收节点；解码模式可为空。
      active_round: 当前策略唯一执行编解码操作的零基轮次。
    """
    self._codec, self._mode = codec, mode
    if mode not in {"encode", "decode"}:
      raise ValueError("mode 必须是 encode 或 decode")
    if not isinstance(codec_id, str) or not codec_id:
      raise ValueError("codec_id 必须是非空资源 ID")
    if type(active_round) is not int or active_round < 0:
      raise ValueError("active_round 必须是非负整数")
    self._codec_id = codec_id
    self._target, self._round = target, active_round

  def initial_state(self) -> None:
    """每次试验没有跨运行记忆。"""
    return None

  def step(
      self,
      observation: Mapping[str, Any],
      prev_state: None,
  ) -> tuple[AgentAction, None]:
    """从 observation 私有区取材料，接收端只解码 inbox。

    参数：
      observation: 宿主为当前节点构造的局部观察。
      prev_state: 该策略无跨轮次状态，固定为 None。

    返回：
      编码消息、解码最终答案或等待动作，以及 None 状态。
    """
    if observation["round_index"] != self._round:
      return AgentAction.wait(), None
    private = observation["environment"]["framework"]["private"]
    shared = private.get("shared_material", {})
    if self._mode == "encode":
      result = self._codec.encode(EncodeRequest(private["secret_bits"], Carrier(private.get("cover", "")), shared))
      intent = CommunicationIntent.instrumented(
          result.carrier.content,
          codec_id=self._codec_id,
          payload_bits=len(private["secret_bits"]),
          consumed_bits=result.consumed_bits,
          carrier_token_count=result.research.get("carrier_token_count"),
      )
      return AgentAction.message(result.carrier.content, target=self._target,
                                 communication=intent), None
    if not observation["inbox"]:
      return AgentAction.final_answer(""), None
    if len(observation["inbox"]) != 1:
      raise ValueError("基础解码策略要求唯一载体；多消息协议请扩展 Policy")
    result = self._codec.decode(DecodeRequest(Carrier(observation["inbox"][0]["content"]), shared))
    return AgentAction.final_answer(result.bits), None

  def close(self) -> None:
    """codec 生命周期由组合根管理，本策略没有自有资源。"""
