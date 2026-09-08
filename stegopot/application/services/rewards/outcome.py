"""使用中央结果与真值计算 Episode 结束反馈的通用实现。"""

from __future__ import annotations

import math
from collections.abc import Mapping

from stegopot.domain.model.reward import EpisodeOutcomeRequest


class ExactMatchOutcomeReward:
  """比较指定节点最终答案与 truth 字段，并向目标节点分配反馈。"""

  def __init__(
      self,
      *,
      answer_node: str,
      truth_key: str,
      reward_nodes: list[str],
      success_reward: float = 1.0,
      failure_reward: float = 0.0,
      strip: bool = True,
      case_sensitive: bool = True,
  ) -> None:
    """创建精确匹配结果奖励器。

    参数：
      answer_node: 从实际 final_answers 中读取答案的节点 ID。
      truth_key: 从当前 Episode.truth 中读取期望字符串的字段名。
      reward_nodes: 接收相同结果反馈的非空节点 ID 列表。
      success_reward: 实际答案匹配 truth 时分配给每个目标节点的分值。
      failure_reward: 答案缺失或不匹配时分配给每个目标节点的分值。
      strip: 比较前是否移除答案和期望值两端空白。
      case_sensitive: 英文比较是否区分大小写。
    """
    if not isinstance(answer_node, str) or not answer_node.strip():
      raise ValueError("answer_node 必须是非空字符串")
    if not isinstance(truth_key, str) or not truth_key.strip():
      raise ValueError("truth_key 必须是非空字符串")
    normalized_nodes = tuple(
        node.strip()
        for node in reward_nodes
        if isinstance(node, str) and node.strip()
    )
    if not normalized_nodes or len(normalized_nodes) != len(reward_nodes):
      raise ValueError("reward_nodes 必须是非空节点 ID 列表")
    if len(set(normalized_nodes)) != len(normalized_nodes):
      raise ValueError("reward_nodes 不能重复")
    success = float(success_reward)
    failure = float(failure_reward)
    if not math.isfinite(success) or not math.isfinite(failure):
      raise ValueError("success_reward/failure_reward 必须是有限数值")
    if type(strip) is not bool or type(case_sensitive) is not bool:
      raise TypeError("strip/case_sensitive 必须是 bool")
    self._answer_node = answer_node.strip()
    self._truth_key = truth_key.strip()
    self._reward_nodes = normalized_nodes
    self._success_reward = success
    self._failure_reward = failure
    self._strip = strip
    self._case_sensitive = case_sensitive

  def score(self, request: EpisodeOutcomeRequest) -> dict[str, float]:
    """根据 request.result 与 request.truth 的字符串精确匹配返回反馈。"""
    result = request.result
    truth = request.truth
    final_answers = result.get("final_answers", {})
    expected = truth.get(self._truth_key)
    actual = (
        final_answers.get(self._answer_node)
        if isinstance(final_answers, Mapping)
        else None
    )
    matched = (
        isinstance(actual, str)
        and isinstance(expected, str)
        and self._normalize(actual) == self._normalize(expected)
    )
    value = self._success_reward if matched else self._failure_reward
    return {node_id: value for node_id in self._reward_nodes}

  def _normalize(self, value: str) -> str:
    """根据构造参数规范化 value，不修改审计中的原始答案。"""
    normalized = value.strip() if self._strip else value
    return normalized if self._case_sensitive else normalized.casefold()
