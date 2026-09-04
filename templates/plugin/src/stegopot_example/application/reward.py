"""面向实际消息投递的简单奖励，不读取中央秘密。"""

class DeliveryReward:
  """为成功投递消息的发送者累计奖励。"""

  def __init__(self, *, points: float):
    """points 为每条投递消息给予发送者的分值，可为负值。"""
    self._points = points

  def score(self, transition):
    """transition 是宿主提供的公开轮次数据，返回节点 ID 到分值的映射。"""
    rewards = {}
    for message in transition["messages"]:
      sender = message["sender"]
      rewards[sender] = rewards.get(sender, 0.0) + self._points
    return rewards
