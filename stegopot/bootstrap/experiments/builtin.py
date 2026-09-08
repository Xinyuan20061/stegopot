"""内置组件清单；算法实现保留在对应逻辑层。"""

from stegopot.application.services.experiments.explicit import BasicEvaluator, ExplicitScenario
from stegopot.application.services.experiments.sessions import SessionScenario
from stegopot.application.services.experiments.stego import StegoEvaluator
from stegopot.application.services.rewards import (
    DeliveryReward,
    DetectionPenaltyReward,
    ExactMatchOutcomeReward,
)
from stegopot.domain.interface.plugin import API_VERSION, ComponentDefinition, PluginDefinition
from stegopot.infrastructure.llm.policy import LLMPolicy
from stegopot.infrastructure.llm.prompt import PromptBuilder
from stegopot.infrastructure.llm.scheduling import RoundPolicy
from stegopot.infrastructure.llm.scripted import EchoPolicy, ScriptedPolicy
from stegopot.infrastructure.llm.strict_parser import StrictJsonActionParser
from stegopot.infrastructure.llm.validation import llm_preflight, scripted_preflight
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
  reward_number = {
      "type": "number",
      "description": "奖励组件使用的有限数值；非有限值会在构造时拒绝",
  }
  delivery_reward = _object({
      "points": {
          **reward_number,
          "default": 1.0,
          "description": "每条实际投递消息给予发送节点的分值",
      },
  })
  detection_penalty = _object({
      "penalty": {
          "type": "number",
          "minimum": 0,
          "default": 1.0,
          "description": "单位检测风险施加给消息发送节点的惩罚绝对值",
      },
      "mode": {
          "enum": ["binary", "score"],
          "default": "score",
          "description": "binary 使用二分类判定，score 使用连续风险分数",
      },
      "aggregation": {
          "enum": ["max", "sum"],
          "default": "max",
          "description": "同一消息有多个检测信号时使用最大值或求和",
      },
  })
  session_node = _object({
      "id": {"type": "string", "minLength": 1,
             "description": "Session 内稳定且唯一的节点 ID"},
      "role": {"type": "string", "minLength": 1,
               "description": "节点在全部 Episode 中保持不变的角色说明"},
      "policy": {**COMPONENT_SCHEMA,
                 "description": "节点在当前 Session 使用的策略组件"},
  }, ["id", "policy"])
  episode = _object({
      "id": {"type": "string", "minLength": 1,
             "description": "当前 Condition 内唯一的 Episode 短 ID"},
      "task": {"type": "string", "minLength": 1,
               "description": "当前 Episode 向全部节点公开的任务文本"},
      "shared_context": {"type": "object",
                         "description": "当前 Episode 向全部节点公开的结构化材料"},
      "node_contexts": {"type": "object",
                        "description": "当前 Episode 按节点 ID 隔离的私有材料"},
      "truth": {"type": "object",
                "description": "只供中央评价与 outcome_reward 使用的真实标签"},
      "max_rounds": {"type": "integer", "minimum": 1, "maximum": 10000,
                     "description": "当前 Episode 的同步轮次上限"},
  }, ["id", "task"])
  condition = _object({
      "id": {"type": "string", "minLength": 1,
             "description": "实验条件 ID，例如 baseline 或 incentive"},
      "session_count": {"type": "integer", "minimum": 1, "maximum": 10000,
                        "default": 1, "description": "该条件的独立 Session 重复次数"},
      "persist_policy_state": {"type": "boolean", "default": True,
                               "description": "是否在同一 Session 的 Episode 间延续策略状态"},
      "nodes": {"type": "array", "minItems": 1, "items": session_node,
                "description": "该条件全部 Episode 共用的节点和策略"},
      "edges": {"type": "array", "items": {
          "type": "array", "items": text, "minItems": 2, "maxItems": 2},
                "description": "该条件全部 Episode 共用的有向通信边"},
      "substrate": {**COMPONENT_SCHEMA,
                    "description": "每个 Episode 都会重置的环境组件"},
      "episodes": {"type": "array", "minItems": 1, "items": episode,
                   "description": "每个 Session 按顺序执行的任务样本"},
  }, ["id", "nodes", "edges", "episodes"])
  sessions = _object({
      "conditions": {"type": "array", "minItems": 1, "items": condition,
                     "description": "本次 Run 中按顺序执行的实验条件"},
  }, ["conditions"])
  exact_match_outcome = _object({
      "answer_node": {"type": "string", "minLength": 1,
                      "description": "从 final_answers 读取实际答案的节点 ID"},
      "truth_key": {"type": "string", "minLength": 1,
                    "description": "从 Episode.truth 读取期望字符串的字段名"},
      "reward_nodes": {"type": "array", "minItems": 1, "uniqueItems": True,
                       "items": {"type": "string", "minLength": 1},
                       "description": "接收相同结果反馈的节点 ID 列表"},
      "success_reward": {**reward_number, "default": 1.0,
                         "description": "答案匹配时给予每个目标节点的分值"},
      "failure_reward": {**reward_number, "default": 0.0,
                         "description": "答案缺失或不匹配时给予每个目标节点的分值"},
      "strip": {"type": "boolean", "default": True,
                "description": "比较前是否移除答案与期望值两端空白"},
      "case_sensitive": {"type": "boolean", "default": True,
                         "description": "英文精确匹配是否区分大小写"},
  }, ["answer_node", "truth_key", "reward_nodes"])
  return PluginDefinition("core", "0.11.0", API_VERSION, (
      ComponentDefinition("core.explicit", "scenario", lambda config, ctx: ExplicitScenario(config), explicit),
      ComponentDefinition("core.sessions", "scenario", lambda config, ctx: SessionScenario(config), sessions),
      ComponentDefinition("core.metrics", "evaluator", lambda config, ctx: BasicEvaluator(), _object()),
      ComponentDefinition("core.stego_metrics", "evaluator", lambda config, ctx: StegoEvaluator(), _object()),
      ComponentDefinition("core.communication", "substrate", lambda config, ctx: CommunicationSubstrate(), _object()),
      ComponentDefinition("core.scripted", "policy", lambda config, ctx: ScriptedPolicy(config["actions"]),
                           _object({"actions": {"type": "array", "items": action}}, ["actions"]),
                           preflight=scripted_preflight),
      ComponentDefinition("core.echo", "policy", lambda config, ctx: EchoPolicy(), _object()),
      ComponentDefinition("core.llm", "policy", _llm, llm, references={"client": "llm"},
                           preflight=llm_preflight),
      ComponentDefinition("core.block", "channel", lambda config, ctx: BlockChannel(), _object()),
      ComponentDefinition("core.replace", "channel", lambda config, ctx: ReplaceChannel(**config),
                           _object({"search": {"type": "string", "minLength": 1}, "replacement": text},
                                   ["search", "replacement"])),
      ComponentDefinition("core.delivery_reward", "reward",
                           lambda config, ctx: DeliveryReward(**config), delivery_reward),
      ComponentDefinition("core.detection_penalty", "reward",
                           lambda config, ctx: DetectionPenaltyReward(**config), detection_penalty),
      ComponentDefinition("core.exact_match_outcome", "outcome_reward",
                           lambda config, ctx: ExactMatchOutcomeReward(**config), exact_match_outcome),
  ) + definitions() + llm_definitions())
