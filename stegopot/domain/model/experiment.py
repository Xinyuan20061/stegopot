"""不绑定运行器或插件实现的实验计划与组件引用。"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import json
import re
from typing import Any


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
  """节点声明。node_id 为身份，role 为角色，policy 为决策组件引用。"""

  node_id: str
  role: str
  policy: ComponentSpec

  def __post_init__(self) -> None:
    validate_id(self.node_id)
    if not isinstance(self.role, str) or not self.role.strip():
      raise ValueError("节点 role 不能为空")

  def to_dict(self) -> dict[str, Any]:
    """返回标准节点声明。"""
    return {"node_id": self.node_id, "role": self.role, "policy": self.policy.to_dict()}


@dataclass(frozen=True)
class ReplaySpec:
  """配对重放。source_trial 为已完成源试验，sender/recipient 指定唯一正文。"""

  source_trial: str
  sender: str
  recipient: str

  def __post_init__(self) -> None:
    for value in (self.source_trial, self.sender, self.recipient):
      validate_id(value)


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
    if self.replay and {self.replay.sender, self.replay.recipient} - ids:
      raise ValueError("重放引用未知节点")
    if any(not isinstance(value, Mapping) for value in self.node_contexts.values()):
      raise ValueError("每个节点的私有上下文必须是对象")
    object.__setattr__(self, "nodes", nodes)
    object.__setattr__(self, "edges", edges)
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
        "replay": None if self.replay is None else {
            "source_trial": self.replay.source_trial,
            "sender": self.replay.sender, "recipient": self.replay.recipient,
        },
    }


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
    if any(item.replay is not None for item in episodes):
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
    seen = set()
    for trial in trials:
      if trial.trial_id in seen:
        raise ValueError("试验编号不能重复")
      if trial.replay and trial.replay.source_trial not in seen:
        raise ValueError("重放只能引用先前已声明的试验")
      seen.add(trial.trial_id)
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
