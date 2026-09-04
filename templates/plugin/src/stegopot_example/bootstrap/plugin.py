"""通过数据类与装饰器声明参数、接口类型和统一工厂。"""

from dataclasses import dataclass, field

from stegopot.domain.interface.registration import Plugin
from stegopot_example.application.reward import DeliveryReward


@dataclass(frozen=True)
class RewardConfig:
  """奖励参数；每个字段的说明参与生成配置模式。"""

  points: float = field(default=1.0, metadata={"description": "每条已投递消息给予发送者的奖励分值"})


plugin = Plugin("example", "0.1.0")


@plugin.component("reward", "delivery", config=RewardConfig)
def build_reward(config: RewardConfig, context) -> DeliveryReward:
  """使用 config.points 创建奖励；context 保留统一工厂签名，此组件不申请额外资源。"""
  return DeliveryReward(points=config.points)
