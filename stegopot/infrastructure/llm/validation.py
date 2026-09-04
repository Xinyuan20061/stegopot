"""内置策略的纯语义预检，与模型构造、网络请求和执行调度分离。"""

from collections.abc import Mapping
from typing import Any

from stegopot.domain.model.action import AgentAction, BROADCAST_TARGETS
from stegopot.domain.model.diagnostic import Diagnostic, PreflightContext


def _schedule(config: Mapping[str, Any], context: PreflightContext, default: int | None = None) -> list[Diagnostic]:
  """检查 config 的活动轮次；context/default 提供试验上限和策略默认值。"""
  value = config.get("active_round", default)
  if value is not None and context.max_rounds is not None and value >= context.max_rounds:
    return [Diagnostic("schedule.out_of_range", context.path + ".active_round",
                       "活动轮次不在试验范围内", "轮次从 0 开始，须小于场景 max_rounds")]
  return []


def _message(target: str | None, context: PreflightContext, *, path: str, round_index: int | None) -> list[Diagnostic]:
  """检查 target 路由；path 为定位位置，round_index 用于判断最后一轮未消费消息。"""
  issues = []
  if target is not None and target not in BROADCAST_TARGETS and target not in context.outgoing:
    issues.append(Diagnostic("routing.target_not_neighbor", path,
                             "消息目标不是当前节点的出邻居", "添加对应有向边或修改目标"))
  elif not context.outgoing:
    issues.append(Diagnostic("routing.no_outgoing", path, "发送节点没有出邻居",
                             "确认该消息是否应投递，必要时增加通信边", severity="warning"))
  if context.max_rounds is not None and round_index == context.max_rounds - 1:
    issues.append(Diagnostic("schedule.last_round_message", path,
                             "最后一轮产生的消息没有下一轮可供接收节点处理",
                             "增加一轮或提前发送；只记录载体时可保留", severity="warning"))
  return issues


def llm_preflight(config: Mapping[str, Any], context: PreflightContext) -> list[Diagnostic]:
  """校验 LLM 配置与局部 context；不能静态预测模型输出，只检查显式约束。"""
  issues = _schedule(config, context)
  kind = config.get("action_kind")
  if kind == "message":
    issues.extend(_message(config.get("target"), context, path=context.path + ".target",
                           round_index=config.get("active_round")))
  elif kind == "final_answer" and config.get("target") is not None:
    issues.append(Diagnostic("action.final_target", context.path + ".target",
                             "最终答案不应指定通信目标", "删除 target，答案只进入当前节点结果"))
  elif kind is None and "target" in config:
    issues.append(Diagnostic("action.unbound_target", context.path + ".target",
                             "未启用严格动作模式，target 不会约束模型输出",
                             "指定 action_kind: message 或在策略中处理目标", severity="warning"))
  return issues


def scripted_preflight(config: Mapping[str, Any], context: PreflightContext) -> list[Diagnostic]:
  """检查脚本动作的格式、目标与有效轮次，不构造或运行策略。"""
  issues = []
  ended = False
  for index, value in enumerate(config["actions"]):
    path = f"{context.path}.actions[{index}]"
    try:
      action = AgentAction(**value)
    except (TypeError, ValueError):
      issues.append(Diagnostic("action.invalid", path, "动作不满足 AgentAction 契约",
                               "检查 kind、content、target 和 metadata 的类型"))
      continue
    if ended or (context.max_rounds is not None and index >= context.max_rounds):
      issues.append(Diagnostic("schedule.unreachable_action", path, "该预设动作不会执行",
                               "移除终止后的动作，或调整有效轮数", severity="warning"))
      continue
    if action.kind == "message":
      if not isinstance(action.content, str) or not action.content.strip():
        issues.append(Diagnostic("action.empty_message", path + ".content",
                                 "通信消息正文不能为空", "填写非空字符串，或改用 wait 动作"))
      issues.extend(_message(action.target, context, path=path + ".target", round_index=index))
    ended = action.kind == "final_answer"
  return issues


def sender_preflight(config: Mapping[str, Any], context: PreflightContext) -> list[Diagnostic]:
  """检查隐写发送配置及当前节点私有材料，不把比特内容放入诊断结果。"""
  issues = _schedule(config, context, 0)
  issues.extend(_message(config["target"], context, path=context.path + ".target",
                         round_index=config.get("active_round", 0)))
  bits = context.private.get("secret_bits")
  if not isinstance(bits, str) or set(bits) - {"0", "1"}:
    issues.append(Diagnostic("codec.secret_bits", context.path,
                             "隐写发送节点缺少合法私有比特", "在该节点 node_contexts 中声明 secret_bits"))
  if not isinstance(context.private.get("shared_material", {}), Mapping):
    issues.append(Diagnostic("codec.shared_material", context.path,
                             "预共享材料必须是对象", "检查该节点的 shared_material"))
  return issues


def receiver_preflight(config: Mapping[str, Any], context: PreflightContext) -> list[Diagnostic]:
  """检查基础隐写接收策略；只提示可达性，不推断插件的真实发送行为。"""
  issues = _schedule(config, context, 1)
  if not context.incoming or config.get("active_round", 1) == 0:
    issues.append(Diagnostic("codec.empty_initial_inbox", context.path,
                             "接收轮次或拓扑无法提供上一轮消息",
                             "接收轮次至少为 1，并添加指向接收者的通信边", severity="warning"))
  if not isinstance(context.private.get("shared_material", {}), Mapping):
    issues.append(Diagnostic("codec.shared_material", context.path,
                             "预共享材料必须是对象", "检查该节点的 shared_material"))
  return issues
