"""每次试验的组件组装和受限资源注入。"""

from collections.abc import Mapping
from contextlib import ExitStack
from typing import Any

from stegopot.domain.interface.audit import AuditSink
from stegopot.domain.interface.plugin import BuildContext
from stegopot.domain.interface.execution import ExecutionGuard
from stegopot.domain.interface.trace import audit_span
from stegopot.domain.model.execution import ContractViolation
from stegopot.domain.model.experiment import ComponentSpec, json_copy
from stegopot.infrastructure.llm.audit import AuditedLLMClient, CallBudget
from stegopot.infrastructure.llm.codec_audit import AuditedCodec
from stegopot.infrastructure.plugins.catalog import PluginCatalog


class _ScopedAudit:
  """插件只能追加命名空间研究事件，不能伪造宿主的公开投递事件。"""

  def __init__(self, sink, component):
    """将 sink 限定为 component 的事件发出接口。"""
    self._sink = sink
    self._component = component

  def emit(self, event):
    """把 event 原样放入插件命名空间；顶层 kind 由宿主决定。"""
    self._sink.emit({"kind": "plugin.event", "data": {
        "component": self._component, "event": json_copy(dict(event)),
    }})


class _Context:
  """BuildContext 的实现，不持有全局注册表、实验计划或全部环境变量。"""

  def __init__(self, *, node_id, audit, resources, credentials):
    """接收已授权的 node_id、audit、resources 和 credentials 副本。"""
    self.node_id = node_id
    self.audit = audit
    self._resources = dict(resources)
    self._credentials = dict(credentials)

  def resource(self, slot: str) -> Any:
    """返回已声明 slot，不允许通过任意名称访问宿主资源。"""
    if slot not in self._resources:
      raise PermissionError(f"未授权资源槽位：{slot}")
    return self._resources[slot]

  def credential(self, name: str) -> str:
    """返回已授权 name 凭证，不读取进程其他环境变量。"""
    if name not in self._credentials:
      raise PermissionError("组件没有获得该凭证授权")
    return self._credentials[name]


class ComponentSession:
  """每个试验使用新会话；缓存仅属于该会话，资源在结束时逆序关闭。"""

  def __init__(
      self, catalog: PluginCatalog, *, resources: Mapping[str, ComponentSpec],
      credentials: Mapping[str, str], audit: AuditSink, budget: CallBudget,
      max_output_tokens: int,
      control: ExecutionGuard | None = None,
  ) -> None:
    """初始化受控组装会话。

    参数：
      catalog: 已固定的插件组件注册表。
      resources: 配置明确声明的模型或隐写工具引用。
      credentials: 预检解析的凭证，只按工厂声明分发。
      audit: 宿主管理的审计接口。
      budget: 整组试验共享的模型调用计数器。
      max_output_tokens: 所有模型调用的输出上限。
      control: 当前试验预算与取消接口；资源构造前后检查，不限制关闭操作。
    """
    self._catalog = catalog
    self._resources = resources
    self._credentials = credentials
    self._audit = audit
    self._budget = budget
    self._max_tokens = max_output_tokens
    self._control = control
    self._stack = ExitStack()
    self._cache = {}
    self._building = set()

  def create(self, spec: ComponentSpec, kind: str, *, node_id: str | None = None) -> Any:
    """构造 spec 对应 kind 的组件；node_id 只用于策略和模型调用归属。"""
    if self._control is not None:
      self._control.checkpoint()
    definition = self._catalog.validate(spec, kind)
    bound = {}
    for slot, resource_kind in definition.references.items():
      if slot not in spec.config:
        continue
      name = spec.config[slot]
      key = (name, node_id)
      if key in self._building:
        raise ValueError("组件资源依赖存在循环")
      if key not in self._cache:
        self._building.add(key)
        try:
          self._cache[key] = self.create(self._resources[name], resource_kind, node_id=node_id)
        finally:
          self._building.remove(key)
      bound[slot] = self._cache[key]
    authorized = {field: self._credentials[spec.config[field]]
                  for field in definition.credentials if field in spec.config}
    context: BuildContext = _Context(node_id=node_id,
                                    audit=_ScopedAudit(self._audit, spec.type),
                                    resources=bound, credentials=authorized)
    self._audit.emit({"kind": "component.creating", "data": {
        "component": spec.type, "kind": kind, "node_id": node_id,
    }})
    with audit_span(self._audit, "component.create", actor=node_id):
      instance = definition.factory(json_copy(spec.config), context)
      close = getattr(instance, "close", None)
      if callable(close):
        self._stack.callback(close)
    if self._control is not None:
      self._control.checkpoint()
    required = {
        "scenario": ("plan",), "policy": ("initial_state", "step", "close"),
        "llm": ("generate", "close"), "substrate": ("reset", "observe", "step", "state", "close"),
        "channel": ("transform",), "codec": ("encode", "decode", "close"),
        "detector": ("reset", "detect", "close"), "reward": ("score",),
        "evaluator": ("evaluate", "summarize"), "audit": ("emit",),
    }[kind]
    if any(not callable(getattr(instance, method, None)) for method in required):
      raise ContractViolation(f"组件 {spec.type} 没有满足 {kind} 的方法契约")
    if kind == "llm":
      instance = AuditedLLMClient(instance, audit_sink=self._audit,
                                  node_id=node_id or spec.type, budget=self._budget,
                                  max_output_tokens=self._max_tokens, control=self._control)
    elif kind == "codec":
      instance = AuditedCodec(instance, audit=self._audit, component_id=spec.type,
                              node_id=node_id, control=self._control)
    self._audit.emit({"kind": "component.ready", "data": {"component": spec.type, "kind": kind}})
    return instance

  def close(self) -> None:
    """逆序释放组件；关闭失败向上传播，不能把未释放资源标记为正常完成。"""
    self._stack.close()

  def adopt(self, session) -> None:
    """接管 session 的关闭责任，用于生命周期受控的可选审计接收器。"""
    self._stack.callback(session.close)


class PlanningContext:
  """场景展开阶段不提供网络、凭证、资源或可伪造审计的能力。"""

  node_id = None

  @property
  def audit(self):
    """计划阶段不允许向尚未创建的运行日志发送事件。"""
    raise PermissionError("场景工厂必须是无副作用的计划构造器")

  def resource(self, slot):
    """禁止计划阶段请求 slot 资源。"""
    raise PermissionError("计划阶段不能构造模型或工具")

  def credential(self, name):
    """禁止计划阶段读取 name 凭证。"""
    raise PermissionError("计划阶段不能读取凭证")
