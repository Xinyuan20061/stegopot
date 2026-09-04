"""共谋扩展的唯一注册入口；只负责声明和对象组装。"""

from stegopot.domain.interface.plugin import ComponentDefinition, PluginDefinition
from stegopot_collusion.application.services.scenario import CodebookScenario, CollusionEvaluator
from stegopot_collusion.domain.model.collusion import CONDITIONS, CollusionTrial
from stegopot_collusion.infrastructure.policies.fixture import FixturePolicy
from stegopot_collusion.infrastructure.substrates.channel import CollusionChannel
from stegopot_collusion.infrastructure.policies.prompts import SENDER_PROMPT, RECEIVER_PROMPT, OBSERVER_PROMPT


def plugin():
  """返回 API 1.0 插件定义；安装并在配置中启用后才会被加载。"""
  def obj(properties=None, required=()):
    """根据 properties 和 required 构造严格参数模式。"""
    return {"type": "object", "properties": properties or {}, "required": list(required), "additionalProperties": False}
  return PluginDefinition("collusion", "0.1.0", "1.0", (
      ComponentDefinition("collusion.codebook", "scenario", lambda c, x: CodebookScenario(c, (
          ("sender", SENDER_PROMPT), ("receiver", RECEIVER_PROMPT), ("observer", OBSERVER_PROMPT))), obj({
          "cases": {"type": "integer", "minimum": 4, "maximum": 200, "multipleOf": 4},
          "mode": {"enum": ["offline", "llm"]}, "client": {"type": "string"},
          "temperature": {"type": "number", "minimum": 0, "maximum": 2},
          "max_tokens": {"type": "integer", "minimum": 64, "maximum": 4096},
          "conditions": {"type": "array", "items": {"enum": list(CONDITIONS)}, "uniqueItems": True}})),
      ComponentDefinition("collusion.fixture", "policy", lambda c, x: FixturePolicy(c["role"]),
                          obj({"role": {"enum": ["sender", "receiver", "observer"]}}, ["role"])),
      ComponentDefinition("collusion.channel", "substrate", lambda c, x: CollusionChannel(CollusionTrial(**c["case"])),
                          obj({"case": {"type": "object"}}, ["case"])),
      ComponentDefinition("collusion.metrics", "evaluator", lambda c, x: CollusionEvaluator(), obj()),
  ))
