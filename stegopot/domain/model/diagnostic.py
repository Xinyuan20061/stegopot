"""配置与环境诊断数据；不保存配置原值、密钥或模型响应。"""

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class Diagnostic:
  """诊断结果。

  属性：
    code: 稳定机器码。
    path: 配置路径或展开计划路径，不是原始参数值。
    message: 中文问题说明，不得回显秘密。
    hint: 中文修复建议。
    severity: error 阻止运行，warning 仅提示风险，info 记录检查范围。
    component: 可选的注册组件 ID。
  """

  code: str
  path: str
  message: str
  hint: str
  severity: Literal["error", "warning", "info"] = "error"
  component: str | None = None

  def __post_init__(self) -> None:
    """验证诊断字段类型，不检查或回显研究载荷。"""
    if self.severity not in {"error", "warning", "info"}:
      raise ValueError("无效诊断级别")
    if any(not isinstance(value, str) for value in (self.code, self.path, self.message, self.hint)):
      raise TypeError("诊断说明必须是字符串")

  def to_dict(self) -> dict[str, Any]:
    """返回标准报告字段，不附加内部执行对象。"""
    return asdict(self)


@dataclass(frozen=True)
class PreflightContext:
  """纯预检上下文，只有当前节点的已授权材料。

  属性：
    path: 当前组件的配置或展开计划位置。
    node_id: 当前节点，无节点作用域时为 None。
    max_rounds: 本次试验轮数，无试验作用域时为 None。
    outgoing: 可发送的邻居 ID。
    incoming: 可接收的邻居 ID。
    private: 当前节点私有材料的独立副本；不得写入诊断文本。
  """

  path: str
  node_id: str | None = None
  max_rounds: int | None = None
  outgoing: tuple[str, ...] = ()
  incoming: tuple[str, ...] = ()
  private: Mapping[str, Any] = field(default_factory=dict)


class PreflightError(ValueError):
  """聚合阻止运行的诊断；保留 ValueError 兼容性。"""

  def __init__(self, diagnostics: Sequence[Diagnostic]) -> None:
    """保存 diagnostics；调用者可读取结构化字段，不能输出未经脱敏的插件原值。"""
    self.diagnostics = tuple(diagnostics)
    super().__init__("；".join(
        f"{item.path} [{item.code}] {item.message} 建议：{item.hint}"
        for item in self.diagnostics if item.severity == "error"))
