"""内置组件清单；算法实现保留在对应逻辑层。"""

from stegopot.application.services.experiments.explicit import BasicEvaluator, ExplicitScenario
from stegopot.application.services.experiments.stego import StegoEvaluator
from stegopot.domain.interface.plugin import API_VERSION, ComponentDefinition, PluginDefinition
from stegopot.infrastructure.llm.policy import LLMPolicy
from stegopot.infrastructure.llm.prompt import PromptBuilder
from stegopot.infrastructure.llm.scheduling import RoundPolicy
from stegopot.infrastructure.llm.scripted import EchoPolicy, ScriptedPolicy
from stegopot.infrastructure.llm.strict_parser import StrictJsonActionParser
from stegopot.infrastructure.settings.experiment import COMPONENT_SCHEMA
from stegopot.infrastructure.substrates.communication import CommunicationSubstrate
from stegopot.infrastructure.substrates.transforms import BlockChannel, ReplaceChannel
from stegopot.bootstrap.experiments.stego_components import definitions
from stegopot.bootstrap.experiments.llm_components import definitions as llm_definitions


def _object(properties=None, required=()):
  """以 properties/required 组成禁止未知字段的组件配置 schema。"""
  return {"type": "object", "properties": properties or {},
          "required": list(required), "additionalProperties": False}


def _llm(config, context):
  """将 config 提示与 context 提供的审计客户端注入通用 LLM 策略。"""
  parser = None
  if "action_kind" in config:
    parser = StrictJsonActionParser(kind=config["action_kind"], target=config.get("target"))
  policy = LLMPolicy(
      node_id=context.node_id, role=config.get("role", context.node_id), client=context.resource("client"),
      prompt_builder=PromptBuilder(system_prompt=config.get("prompt", "")), action_parser=parser,
      model=config.get("model"), temperature=config.get("temperature", 0),
      max_tokens=config.get("max_tokens", 384), keep_history=config.get("keep_history", False),
  )
  return RoundPolicy(policy, active_round=config["active_round"]) if "active_round" in config else policy


def builtin_plugin() -> PluginDefinition:
  """返回独立可用的基础组件，没有安装任何扩展包时也能运行规则实验。"""
  text = {"type": "string"}
  action = _object({"kind": {"enum": ["message", "wait", "final_answer"]},
                    "content": {"type": ["string", "null"]}, "target": {"type": ["string", "null"]},
                    "metadata": {"type": "object"}}, ["kind"])
  explicit = _object({
      "task": {"type": "string", "minLength": 1},
      "nodes": {"type": "array", "minItems": 1, "items": _object({
          "id": text, "role": text, "policy": COMPONENT_SCHEMA}, ["id", "policy"])},
      "edges": {"type": "array", "items": {"type": "array", "items": text, "minItems": 2, "maxItems": 2}},
      "substrate": COMPONENT_SCHEMA, "repeat": {"type": "integer", "minimum": 1, "maximum": 10000},
      "max_rounds": {"type": "integer", "minimum": 1, "maximum": 10000},
      "shared_context": {"type": "object"}, "node_contexts": {"type": "object"}, "truth": {"type": "object"},
  }, ["task", "nodes", "edges"])
  llm = _object({"client": text, "role": text, "prompt": text, "model": text,
                 "temperature": {"type": "number", "minimum": 0, "maximum": 2},
                 "max_tokens": {"type": "integer", "minimum": 1, "maximum": 65536},
                 "keep_history": {"type": "boolean"},
                 "active_round": {"type": "integer", "minimum": 0},
                 "action_kind": {"enum": ["message", "final_answer"]},
                 "target": {"type": ["string", "null"]}}, ["client"])
  return PluginDefinition("core", "0.7.0", API_VERSION, (
      ComponentDefinition("core.explicit", "scenario", lambda config, ctx: ExplicitScenario(config), explicit),
      ComponentDefinition("core.metrics", "evaluator", lambda config, ctx: BasicEvaluator(), _object()),
      ComponentDefinition("core.stego_metrics", "evaluator", lambda config, ctx: StegoEvaluator(), _object()),
      ComponentDefinition("core.communication", "substrate", lambda config, ctx: CommunicationSubstrate(), _object()),
      ComponentDefinition("core.scripted", "policy", lambda config, ctx: ScriptedPolicy(config["actions"]),
                           _object({"actions": {"type": "array", "items": action}}, ["actions"])),
      ComponentDefinition("core.echo", "policy", lambda config, ctx: EchoPolicy(), _object()),
      ComponentDefinition("core.llm", "policy", _llm, llm, references={"client": "llm"}),
      ComponentDefinition("core.block", "channel", lambda config, ctx: BlockChannel(), _object()),
      ComponentDefinition("core.replace", "channel", lambda config, ctx: ReplaceChannel(**config),
                           _object({"search": {"type": "string", "minLength": 1}, "replacement": text},
                                   ["search", "replacement"])),
  ) + definitions() + llm_definitions())
