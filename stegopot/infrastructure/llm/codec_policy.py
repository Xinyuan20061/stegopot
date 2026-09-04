"""通过统一隐写接口操作工具的节点策略，与 StegoKit 实现无关。"""

from stegopot.domain.interface.policy import Policy
from stegopot.domain.interface.codec import Carrier, EncodeRequest, DecodeRequest
from stegopot.domain.model.action import AgentAction


class CodecPolicy(Policy):
  """工具驱动的隐写节点，不将算法输出描述成 LLM 自发行为。"""

  def __init__(self, *, codec, mode, target=None, active_round=0):
    """设置 codec 注入资源、mode 编码/解码角色、target 接收者及 active_round 调用轮次。"""
    self._codec, self._mode = codec, mode
    self._target, self._round = target, active_round

  def initial_state(self):
    """每次试验没有跨运行记忆。"""
    return None

  def step(self, observation, prev_state):
    """从 observation 自身私有区取材料，接收端只解码 inbox；prev_state 不使用。"""
    if observation["round_index"] != self._round:
      return AgentAction.wait(), None
    private = observation["environment"]["framework"]["private"]
    shared = private.get("shared_material", {})
    if self._mode == "encode":
      result = self._codec.encode(EncodeRequest(private["secret_bits"], Carrier(private.get("cover", "")), shared))
      return AgentAction.message(result.carrier.content, target=self._target), None
    if not observation["inbox"]:
      return AgentAction.final_answer(""), None
    if len(observation["inbox"]) != 1:
      raise ValueError("基础解码策略要求唯一载体；多消息协议请扩展 Policy")
    result = self._codec.decode(DecodeRequest(Carrier(observation["inbox"][0]["content"]), shared))
    return AgentAction.final_answer(result.bits), None
