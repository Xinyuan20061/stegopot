"""不绑定运行器或插件实现的实验计划与组件引用。"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
import json
import re
from typing import Any

from stegopot.domain.model.communication import CommunicationIntent, carrier_sha256
from stegopot.domain.model.information import InformationAsset, principal_node_id


def json_copy(value: Any) -> Any:
  """复制 value 为标准 JSON 数据；拒绝对象实例和非有限数值。"""
  return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def validate_id(value: str) -> str:
  """验证 value 为可用于组件引用和工件名称的标识，不允许路径穿越。"""
  if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", value):
    raise ValueError(f"无效标识：{value!r}")
  return value


@dataclass(frozen=True)
class ComponentSpec:
  """组件引用。type 为注册 ID，config 为该组件自己的 JSON 参数。"""

  type: str
  config: Mapping[str, Any] = field(default_factory=dict)

  def __post_init__(self) -> None:
    validate_id(self.type)
    if not isinstance(self.config, Mapping):
      raise ValueError("组件 config 必须是对象")
    object.__setattr__(self, "config", json_copy(dict(self.config)))

  @classmethod
  def from_dict(cls, value: Mapping[str, Any]) -> "ComponentSpec":
    """从仅含 type/config 的 value 构造引用，不接受任意导入路径。"""
    if not isinstance(value, Mapping) or set(value) - {"type", "config"}:
      raise ValueError("组件只能声明 type 和 config")
    return cls(type=value["type"], config=value.get("config", {}))

  def to_dict(self) -> dict[str, Any]:
    """返回与内部映射不共享可变对象的配置副本。"""
    return {"type": self.type, "config": json_copy(self.config)}


@dataclass(frozen=True)
class NodeSpec:
  """节点声明。node_id 为身份，policy 为决策组件，tools 为授权工具。"""

  node_id: str
  role: str
  policy: ComponentSpec
  tools: Mapping[str, ComponentSpec] = field(default_factory=dict)

  def __post_init__(self) -> None:
    validate_id(self.node_id)
    if not isinstance(self.role, str) or not self.role.strip():
      raise ValueError("节点 role 不能为空")
    if not isinstance(self.tools, Mapping):
      raise TypeError("节点 tools 必须是工具别名到组件引用的映射")
    tools = dict(self.tools)
    for alias, spec in tools.items():
      validate_id(alias)
      if not isinstance(spec, ComponentSpec):
        raise TypeError("节点工具必须使用 ComponentSpec 声明")
    object.__setattr__(self, "tools", tools)

  @classmethod
  def from_dict(cls, value: Mapping[str, Any]) -> "NodeSpec":
    """从标准计划字典恢复节点声明。

    参数：
      value: 包含 node_id、role、policy 和可选 tools 的节点数据。

    返回：
      可用于证据重算的不可变节点声明。
    """
    if not isinstance(value, Mapping):
      raise TypeError("节点声明必须是映射")
    return cls(
        node_id=value["node_id"],
        role=value.get("role", value["node_id"]),
        policy=ComponentSpec.from_dict(value["policy"]),
        tools={
            alias: ComponentSpec.from_dict(spec)
            for alias, spec in value.get("tools", {}).items()
        },
    )

  def to_dict(self) -> dict[str, Any]:
    """返回标准节点声明。"""
    return {
        "node_id": self.node_id,
        "role": self.role,
        "policy": self.policy.to_dict(),
        "tools": {alias: spec.to_dict() for alias, spec in self.tools.items()},
    }


@dataclass(frozen=True)
class CounterfactualSpec:
  """固定源载体并只改变声明处理条件的配对反事实。

  属性：
    source_trial: 必须先完成的源 Trial ID。
    sender: 从源结果筛选载体的发送节点。
    recipient: 从源结果筛选载体的接收节点。
    treatment_id: 当前反事实分支的处理条件 ID。
    group_id: 多个处理条件共享的配对组 ID；为空时使用 source_trial。
    source_message_id: 可选精确消息 ID；为空时要求 sender/recipient 载体唯一。
    frozen_fields: 除载体外还要求与源 Trial 相同的计划字段。
  """

  source_trial: str
  sender: str
  recipient: str
  treatment_id: str = "default"
  group_id: str | None = None
  source_message_id: str | None = None
  frozen_fields: Sequence[str] = (
      "task",
      "shared_context",
      "node_contexts",
      "truth",
      "topology",
      "policies",
      "substrate",
  )

  def __post_init__(self) -> None:
    for value in (
        self.source_trial,
        self.sender,
        self.recipient,
        self.treatment_id,
    ):
      validate_id(value)
    if self.group_id is not None:
      validate_id(self.group_id)
    if self.source_message_id is not None:
      validate_id(self.source_message_id)
    allowed = {
        "task",
        "shared_context",
        "node_contexts",
        "truth",
        "topology",
        "policies",
        "substrate",
    }
    frozen = tuple(self.frozen_fields)
    if len(set(frozen)) != len(frozen) or set(frozen) - allowed:
      raise ValueError("counterfactual.frozen_fields 包含重复或未知字段")
    object.__setattr__(self, "frozen_fields", frozen)

  @property
  def effective_group_id(self) -> str:
    """返回显式 group_id，未设置时使用源 Trial ID。"""
    return self.group_id or self.source_trial

  @classmethod
  def from_dict(cls, value: Mapping[str, Any]) -> "CounterfactualSpec":
    """从标准计划数据恢复配对反事实声明。

    参数：
      value: 包含源载体选择、处理 ID 和冻结字段的数据。

    返回：
      经过标识和字段约束验证的反事实声明。
    """
    return cls(
        source_trial=value["source_trial"],
        sender=value["sender"],
        recipient=value["recipient"],
        treatment_id=value.get("treatment_id", "default"),
        group_id=value.get("group_id"),
        source_message_id=value.get("source_message_id"),
        frozen_fields=value.get("frozen_fields", cls.__dataclass_fields__["frozen_fields"].default),
    )

  def to_dict(self) -> dict[str, Any]:
    """返回可进入计划和报告的标准反事实声明。"""
    return {
        "source_trial": self.source_trial,
        "sender": self.sender,
        "recipient": self.recipient,
        "treatment_id": self.treatment_id,
        "group_id": self.effective_group_id,
        "source_message_id": self.source_message_id,
        "frozen_fields": list(self.frozen_fields),
    }


@dataclass(frozen=True)
class ReplaySpec(CounterfactualSpec):
  """0.x 版本 ReplaySpec 的兼容名称；新代码应使用 CounterfactualSpec。"""

  frozen_fields: Sequence[str] = (
      "task",
      "shared_context",
      "node_contexts",
      "truth",
      "topology",
      "substrate",
  )


@dataclass(frozen=True)
class PairedCarrier:
  """从已完成源结果提取并交给反事实分支的不可变载体。

  属性：
    source_trial: 源 Trial ID。
    source_message_id: 源消息 ID。
    sender: 原发送节点。
    recipient: 原接收节点。
    content: 唯一实际投递的公开正文。
    sha256: content 的 UTF-8 SHA-256。
    group_id: 配对组 ID。
    treatment_id: 当前分支处理条件 ID。
    communication: 源消息原始通信模式；用于保持插桩标签，不包含秘密载荷。
  """

  source_trial: str
  source_message_id: str
  sender: str
  recipient: str
  content: str
  sha256: str
  group_id: str
  treatment_id: str
  communication: CommunicationIntent | None = None

  def __post_init__(self) -> None:
    """校验来源身份、正文摘要和可选通信声明彼此一致。"""
    for value in (
        self.source_trial, self.source_message_id, self.sender,
        self.recipient, self.group_id, self.treatment_id,
    ):
      validate_id(value)
    if not isinstance(self.content, str):
      raise TypeError("PairedCarrier.content 必须是字符串")
    if self.sha256 != carrier_sha256(self.content):
      raise ValueError("PairedCarrier.sha256 与正文不一致")
    if (
        self.communication is not None
        and self.communication.carrier_sha256 != self.sha256
    ):
      raise ValueError("PairedCarrier.communication 与正文不一致")

  def to_dict(self) -> dict[str, Any]:
    """返回不复制秘密载荷、但包含正文和来源证据的研究数据。"""
    return {
        "source_trial": self.source_trial,
        "source_message_id": self.source_message_id,
        "sender": self.sender,
        "recipient": self.recipient,
        "content": self.content,
        "sha256": self.sha256,
        "group_id": self.group_id,
        "treatment_id": self.treatment_id,
        "communication": (
            None if self.communication is None else self.communication.to_dict()
        ),
    }


@dataclass(frozen=True)
class TrialSpec:
  """一次试验的声明，不能整体交给智能体。

  属性：
    trial_id: 中央试验编号，不自动放入节点观察。
    task: 节点共同可见的任务文本。
    nodes: 节点和策略声明。
    edges: 有向通信边；端点必须属于 nodes。
    substrate: 环境组件，默认透明通信。
    shared_context: 明确允许所有节点读取的数据，不自动添加种子或真值。
    node_contexts: 按节点身份隔离的私有环境数据。
    truth: 只供中央评估和研究记录读取的真实标签。
    max_rounds: 同步轮次上限。
    replay: 可选的前序试验正文重放，不代表模型重新生成。
    information: 带类别和读取主体的显式信息资产。
    channels: 当前 Trial 的公开信道处理链；None 表示使用运行配置默认值。
    detectors: 当前 Trial 的检测器；None 表示使用运行配置默认值。
    rewards: 当前 Trial 的逐轮奖励；None 表示使用运行配置默认值。
    counterfactual: 可选配对反事实声明；新代码优先使用该字段。
  """

  trial_id: str
  task: str
  nodes: Sequence[NodeSpec]
  edges: Sequence[tuple[str, str]]
  substrate: ComponentSpec = field(default_factory=lambda: ComponentSpec("core.communication"))
  shared_context: Mapping[str, Any] = field(default_factory=dict)
  node_contexts: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
  truth: Mapping[str, Any] = field(default_factory=dict)
  max_rounds: int = 2
  information: Sequence[InformationAsset] = ()
  channels: Sequence[ComponentSpec] | None = None
  detectors: Sequence[ComponentSpec] | None = None
  rewards: Sequence[ComponentSpec] | None = None
  counterfactual: CounterfactualSpec | None = None
  replay: ReplaySpec | None = None

  def __post_init__(self) -> None:
    validate_id(self.trial_id)
    nodes = tuple(self.nodes)
    ids = {node.node_id for node in nodes}
    edges = tuple(tuple(edge) for edge in self.edges)
    if not nodes or len(ids) != len(nodes):
      raise ValueError("试验节点不能为空或重名")
    if not isinstance(self.task, str) or not self.task.strip():
      raise ValueError("task 不能为空")
    if type(self.max_rounds) is not int or not 1 <= self.max_rounds <= 10000:
      raise ValueError("max_rounds 必须为 1 至 10000 的整数")
    if any(len(edge) != 2 or set(edge) - ids or edge[0] == edge[1] for edge in edges):
      raise ValueError("拓扑边必须引用现有节点")
    if len(set(edges)) != len(edges) or set(self.node_contexts) - ids:
      raise ValueError("拓扑重复或私有观察引用未知节点")
    if self.counterfactual is not None and self.replay is not None:
      raise ValueError("不能同时声明 counterfactual 和兼容 replay")
    paired = self.counterfactual or self.replay
    if paired and {paired.sender, paired.recipient} - ids:
      raise ValueError("重放引用未知节点")
    if any(not isinstance(value, Mapping) for value in self.node_contexts.values()):
      raise ValueError("每个节点的私有上下文必须是对象")
    object.__setattr__(self, "nodes", nodes)
    object.__setattr__(self, "edges", edges)
    information = tuple(self.information)
    if any(not isinstance(item, InformationAsset) for item in information):
      raise TypeError("TrialSpec.information 必须是 InformationAsset 序列")
    if len({item.name for item in information}) != len(information):
      raise ValueError("同一 Trial 的信息资产名称不能重复")
    for item in information:
      unknown_readers = {
          node_id
          for principal in item.visible_to
          if (node_id := principal_node_id(principal)) is not None
          and node_id not in ids
      }
      if unknown_readers:
        raise ValueError(f"信息资产引用未知节点：{sorted(unknown_readers)}")
    object.__setattr__(self, "information", information)
    for name in ("channels", "detectors", "rewards"):
      values = getattr(self, name)
      if values is not None:
        values = tuple(values)
        if any(not isinstance(item, ComponentSpec) for item in values):
          raise TypeError(f"TrialSpec.{name} 必须是 ComponentSpec 序列或 None")
        object.__setattr__(self, name, values)
    for name in ("shared_context", "node_contexts", "truth"):
      object.__setattr__(self, name, json_copy(dict(getattr(self, name))))

  def to_dict(self) -> dict[str, Any]:
    """返回研究专用计划副本，含节点私有数据和中央真值。"""
    return {
        "trial_id": self.trial_id, "task": self.task,
        "nodes": [node.to_dict() for node in self.nodes], "edges": [list(edge) for edge in self.edges],
        "substrate": self.substrate.to_dict(), "shared_context": json_copy(self.shared_context),
        "node_contexts": json_copy(self.node_contexts), "truth": json_copy(self.truth),
        "max_rounds": self.max_rounds,
        "information": {
            item.name: item.to_dict() for item in self.information
        },
        "channels": None if self.channels is None else [item.to_dict() for item in self.channels],
        "detectors": None if self.detectors is None else [item.to_dict() for item in self.detectors],
        "rewards": None if self.rewards is None else [item.to_dict() for item in self.rewards],
        "counterfactual": None if self.paired_spec is None else self.paired_spec.to_dict(),
    }

  @property
  def paired_spec(self) -> CounterfactualSpec | None:
    """返回新式 counterfactual 或兼容 replay 声明。"""
    return self.counterfactual or self.replay

  def information_for(self, principal: str) -> dict[str, Any]:
    """返回 principal 获准读取的显式信息值。

    参数：
      principal: 标准组件主体或 ``node:<id>`` 节点主体。

    返回：
      信息名称到独立 JSON 值副本的映射。
    """
    return {
        item.name: json_copy(item.value)
        for item in self.information
        if item.is_visible_to(principal)
    }

  def for_principal(self, principal: str) -> "TrialSpec":
    """返回只保留 principal 获授权信息资产的计划视图。

    参数：
      principal: 标准组件主体，例如 ``evaluator`` 或 ``research_audit``。

    返回：
      结构与当前试验相同、但 information 已按主体过滤的不可变副本。
      传统 truth 和 node_contexts 仍只允许中央评价阶段使用；新实验应优先
      采用带类别的 information 声明。
    """
    return replace(
        self,
        information=tuple(
            item for item in self.information if item.is_visible_to(principal)
        ),
    )

  @classmethod
  def from_dict(cls, value: Mapping[str, Any]) -> "TrialSpec":
    """从 manifest 中的标准计划恢复 TrialSpec。

    参数：
      value: ``TrialSpec.to_dict`` 产生的完整研究计划。

    返回：
      用于离线指标重算的 TrialSpec，不执行任何组件。
    """
    paired = value.get("counterfactual") or value.get("replay")
    return cls(
        trial_id=value["trial_id"],
        task=value["task"],
        nodes=tuple(NodeSpec.from_dict(item) for item in value["nodes"]),
        edges=tuple(tuple(edge) for edge in value["edges"]),
        substrate=ComponentSpec.from_dict(value["substrate"]),
        shared_context=value.get("shared_context", {}),
        node_contexts=value.get("node_contexts", {}),
        truth=value.get("truth", {}),
        max_rounds=value.get("max_rounds", 2),
        information=tuple(
            InformationAsset.from_dict(name, item)
            for name, item in value.get("information", {}).items()
        ),
        channels=(
            None if value.get("channels") is None
            else tuple(ComponentSpec.from_dict(item) for item in value["channels"])
        ),
        detectors=(
            None if value.get("detectors") is None
            else tuple(ComponentSpec.from_dict(item) for item in value["detectors"])
        ),
        rewards=(
            None if value.get("rewards") is None
            else tuple(ComponentSpec.from_dict(item) for item in value["rewards"])
        ),
        counterfactual=None if paired is None else CounterfactualSpec.from_dict(paired),
    )


@dataclass(frozen=True)
class EpisodeSpec(TrialSpec):
  """Session 内的一次任务交互。

  Episode 复用 TrialSpec 的任务、节点、拓扑、环境、私有材料和中央真值契约；
  ``episode_id`` 是兼容 ``trial_id`` 的只读别名，审计目录继续使用 trial_id。
  """

  @property
  def episode_id(self) -> str:
    """返回当前 Episode 的全局唯一标识。"""
    return self.trial_id


@dataclass(frozen=True)
class SessionSpec:
  """一组允许策略状态按顺序延续的 Episode。

  属性：
    session_id: 当前独立重复的唯一 ID。
    condition_id: 当前 Session 所属实验条件 ID。
    episodes: 按执行顺序排列的 Episode；节点、策略、拓扑和 Substrate 必须一致。
    persist_policy_state: 是否把前一 Episode 的节点策略状态带入下一 Episode。
  """

  session_id: str
  condition_id: str
  episodes: Sequence[EpisodeSpec]
  persist_policy_state: bool = True

  def __post_init__(self) -> None:
    validate_id(self.session_id)
    validate_id(self.condition_id)
    if type(self.persist_policy_state) is not bool:
      raise TypeError("persist_policy_state 必须是 bool")
    episodes = tuple(self.episodes)
    if not episodes or any(not isinstance(item, EpisodeSpec) for item in episodes):
      raise ValueError("SessionSpec.episodes 必须是非空 EpisodeSpec 序列")
    if len({item.episode_id for item in episodes}) != len(episodes):
      raise ValueError("同一 Session 的 episode_id 不能重复")
    if any(item.paired_spec is not None for item in episodes):
      raise ValueError("Session 内不支持配对重放；重放应声明为独立 Trial")
    baseline = episodes[0]
    baseline_nodes = [node.to_dict() for node in baseline.nodes]
    for episode in episodes[1:]:
      if ([node.to_dict() for node in episode.nodes] != baseline_nodes
          or episode.edges != baseline.edges
          or episode.substrate != baseline.substrate):
        raise ValueError(
            "同一 Session 的节点、策略、拓扑和 Substrate 必须保持一致"
        )
    object.__setattr__(self, "episodes", episodes)

  def to_dict(self) -> dict[str, Any]:
    """返回会话元数据和有序 Episode 引用，不重复嵌入完整试验计划。"""
    return {
        "session_id": self.session_id,
        "condition_id": self.condition_id,
        "episode_ids": [item.episode_id for item in self.episodes],
        "persist_policy_state": self.persist_policy_state,
    }


@dataclass(frozen=True)
class ExperimentPlan:
  """场景产生的完整计划。

  ``trials`` 保存独立旧式试验；``sessions`` 保存具备 Episode 生命周期的
  独立重复。初始化后 trials 会规范化为全部实际执行单元的扁平列表，以兼容
  既有报告、重放和完整性核验。
  """

  trials: Sequence[TrialSpec] = ()
  evaluators: Sequence[ComponentSpec] = ()
  sessions: Sequence[SessionSpec] = ()
  outcome_rewards: Sequence[ComponentSpec] = ()
  _standalone_trial_ids: tuple[str, ...] = field(
      init=False,
      repr=False,
      default=(),
  )

  def __post_init__(self) -> None:
    standalone = tuple(self.trials)
    sessions = tuple(self.sessions)
    if any(not isinstance(item, SessionSpec) for item in sessions):
      raise TypeError("ExperimentPlan.sessions 必须是 SessionSpec 序列")
    if len({item.session_id for item in sessions}) != len(sessions):
      raise ValueError("session_id 不能重复")
    trials = standalone + tuple(
        episode
        for session in sessions
        for episode in session.episodes
    )
    if not 1 <= len(trials) <= 10000:
      raise ValueError("试验数量必须为 1 至 10000")
    seen: dict[str, TrialSpec] = {}
    for trial in trials:
      if trial.trial_id in seen:
        raise ValueError("试验编号不能重复")
      paired = trial.paired_spec
      if paired:
        if paired.source_trial not in seen:
          raise ValueError("反事实只能引用先前已声明的源试验")
        _validate_frozen_fields(seen[paired.source_trial], trial, paired)
      seen[trial.trial_id] = trial
    object.__setattr__(self, "trials", trials)
    object.__setattr__(self, "evaluators", tuple(self.evaluators))
    object.__setattr__(self, "sessions", sessions)
    object.__setattr__(self, "outcome_rewards", tuple(self.outcome_rewards))
    object.__setattr__(
        self,
        "_standalone_trial_ids",
        tuple(item.trial_id for item in standalone),
    )

  @property
  def standalone_trials(self) -> tuple[TrialSpec, ...]:
    """返回不属于 Session 的旧式独立试验。"""
    identifiers = set(self._standalone_trial_ids)
    return tuple(item for item in self.trials if item.trial_id in identifiers)

  def to_dict(self) -> dict[str, Any]:
    """返回执行前应固定并保存的标准计划。"""
    return {"trials": [trial.to_dict() for trial in self.trials],
            "sessions": [session.to_dict() for session in self.sessions],
            "evaluators": [item.to_dict() for item in self.evaluators],
            "outcome_rewards": [item.to_dict() for item in self.outcome_rewards]}


def _validate_frozen_fields(
    source: TrialSpec,
    branch: TrialSpec,
    spec: CounterfactualSpec,
) -> None:
  """验证反事实分支没有改变 spec 声明固定的计划字段。"""
  values = {
      "task": lambda item: item.task,
      "shared_context": lambda item: item.shared_context,
      "node_contexts": lambda item: item.node_contexts,
      "truth": lambda item: item.truth,
      "topology": lambda item: (
          tuple(node.node_id for node in item.nodes), item.edges
      ),
      "policies": lambda item: tuple(
          (node.node_id, node.policy.to_dict(), {
              name: tool.to_dict() for name, tool in node.tools.items()
          })
          for node in item.nodes
      ),
      "substrate": lambda item: item.substrate.to_dict(),
  }
  for name in spec.frozen_fields:
    if values[name](source) != values[name](branch):
      raise ValueError(
          f"反事实分支 {branch.trial_id} 改变了冻结字段 {name}"
      )
