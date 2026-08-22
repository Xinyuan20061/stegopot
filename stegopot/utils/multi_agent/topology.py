"""多智能体通信拓扑。"""

from __future__ import annotations

from collections.abc import Iterable, Sequence


class TopologyError(ValueError):
  """拓扑定义非法时抛出的异常。"""


class AgentTopology:
  """保存节点和有向通信边的轻量拓扑对象。

  拓扑只描述“谁可以向谁发送消息”，不负责调用智能体，
  也不保存消息内容。节点和边按添加顺序保存，使实验可复现。
  """

  def __init__(
      self,
      node_ids: Iterable[str] = (),
      edges: Iterable[tuple[str, str]] = (),
  ) -> None:
    """初始化拓扑。

    参数：
      node_ids: 初始节点 ID 集合。
      edges: 初始有向边集合，每条边格式为 ``(发送者, 接收者)``。
    """
    self._outgoing: dict[str, list[str]] = {}
    self._incoming: dict[str, list[str]] = {}
    for node_id in node_ids:
      self.add_node(node_id)
    for source, target in edges:
      self.connect(source, target)

  @property
  def nodes(self) -> tuple[str, ...]:
    """返回按添加顺序排列的全部节点 ID。"""
    return tuple(self._outgoing)

  @property
  def edges(self) -> tuple[tuple[str, str], ...]:
    """返回按添加顺序排列的全部有向边。"""
    return tuple(
        (source, target)
        for source, targets in self._outgoing.items()
        for target in targets
    )

  def add_node(self, node_id: str) -> "AgentTopology":
    """添加一个节点。

    参数：
      node_id: 全局唯一的节点 ID，不能为空或只包含空白字符。

    返回：
      当前拓扑对象，便于链式调用。
    """
    normalized = self._normalize_node_id(node_id)
    if normalized in self._outgoing:
      raise TopologyError(f"节点已存在：{normalized}")
    self._outgoing[normalized] = []
    self._incoming[normalized] = []
    return self

  def connect(
      self,
      source: str,
      target: str,
      *,
      bidirectional: bool = False,
  ) -> "AgentTopology":
    """连接两个已存在的节点。

    参数：
      source: 有向边的发送者节点 ID。
      target: 有向边的接收者节点 ID。
      bidirectional: 是否同时添加 ``target -> source`` 反向边。

    返回：
      当前拓扑对象，便于链式调用。
    """
    self._connect_one_way(source, target)
    if bidirectional:
      self._connect_one_way(target, source)
    return self

  def outgoing_neighbors(self, node_id: str) -> tuple[str, ...]:
    """返回节点可以直接发送消息的邻居。

    参数：
      node_id: 要查询的节点 ID。

    返回：
      按边添加顺序排列的出邻居。
    """
    self._require_node(node_id)
    return tuple(self._outgoing[node_id])

  def incoming_neighbors(self, node_id: str) -> tuple[str, ...]:
    """返回可以直接向该节点发送消息的邻居。

    参数：
      node_id: 要查询的节点 ID。

    返回：
      按边添加顺序排列的入邻居。
    """
    self._require_node(node_id)
    return tuple(self._incoming[node_id])

  def can_send(self, source: str, target: str) -> bool:
    """判断是否存在 ``source -> target`` 有向边。

    参数：
      source: 发送者节点 ID。
      target: 接收者节点 ID。

    返回：
      存在直接通信边时为 ``True``，否则为 ``False``。
    """
    self._require_node(source)
    self._require_node(target)
    return target in self._outgoing[source]

  def copy(self) -> "AgentTopology":
    """返回当前拓扑的独立副本。"""
    return AgentTopology(self.nodes, self.edges)

  def to_dict(self) -> dict[str, object]:
    """返回适合日志记录和 JSON 序列化的拓扑结构。"""
    return {
        "nodes": list(self.nodes),
        "edges": [list(edge) for edge in self.edges],
    }

  @classmethod
  def from_edges(
      cls,
      edges: Iterable[tuple[str, str]],
      *,
      isolated_nodes: Iterable[str] = (),
  ) -> "AgentTopology":
    """从边列表创建拓扑，并自动推断边中的节点。

    参数：
      edges: 有向边集合，每条边格式为 ``(发送者, 接收者)``。
      isolated_nodes: 不出现在边中、但仍需加入拓扑的孤立节点。

    返回：
      新创建的拓扑对象。
    """
    edge_list = tuple(edges)
    ordered_nodes: list[str] = []
    for source, target in edge_list:
      for node_id in (source, target):
        if node_id not in ordered_nodes:
          ordered_nodes.append(node_id)
    for node_id in isolated_nodes:
      if node_id not in ordered_nodes:
        ordered_nodes.append(node_id)
    return cls(ordered_nodes, edge_list)

  @classmethod
  def complete(cls, node_ids: Sequence[str]) -> "AgentTopology":
    """创建不含自环的全连接有向拓扑。

    参数：
      node_ids: 要加入全连接拓扑的节点 ID 序列。

    返回：
      任意两个不同节点之间都有双向边的拓扑。
    """
    topology = cls(node_ids)
    for source in topology.nodes:
      for target in topology.nodes:
        if source != target:
          topology.connect(source, target)
    return topology

  @classmethod
  def ring(
      cls,
      node_ids: Sequence[str],
      *,
      bidirectional: bool = False,
  ) -> "AgentTopology":
    """创建环形拓扑。

    参数：
      node_ids: 按环上顺序排列的节点 ID 序列。
      bidirectional: 是否同时添加逆时针方向的边。

    返回：
      新创建的环形拓扑。
    """
    topology = cls(node_ids)
    if len(topology.nodes) < 2:
      return topology
    for index, source in enumerate(topology.nodes):
      target = topology.nodes[(index + 1) % len(topology.nodes)]
      topology.connect(source, target, bidirectional=bidirectional)
    return topology

  @classmethod
  def star(
      cls,
      center: str,
      leaves: Sequence[str],
      *,
      bidirectional: bool = True,
  ) -> "AgentTopology":
    """创建星形拓扑。

    参数：
      center: 中心节点 ID。
      leaves: 叶子节点 ID 序列。
      bidirectional: 是否允许叶子节点向中心节点发送消息。

    返回：
      中心指向每个叶子、并可选反向边的星形拓扑。
    """
    topology = cls((center, *leaves))
    for leaf in leaves:
      topology.connect(center, leaf, bidirectional=bidirectional)
    return topology

  def _connect_one_way(self, source: str, target: str) -> None:
    """添加一条有向边，并自动忽略重复边。"""
    self._require_node(source)
    self._require_node(target)
    if target not in self._outgoing[source]:
      self._outgoing[source].append(target)
      self._incoming[target].append(source)

  def _require_node(self, node_id: str) -> None:
    """确认节点存在。"""
    if node_id not in self._outgoing:
      raise TopologyError(f"拓扑中不存在节点：{node_id}")

  @staticmethod
  def _normalize_node_id(node_id: str) -> str:
    """校验并规范化节点 ID。"""
    if not isinstance(node_id, str) or not node_id.strip():
      raise TopologyError("节点 ID 必须是非空字符串")
    return node_id.strip()
