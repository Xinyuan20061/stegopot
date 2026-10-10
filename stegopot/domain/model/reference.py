"""模型内部张量位置和采集策略的稳定领域对象。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal


def _description(text: str) -> dict[str, str]:
  """返回统一的字段说明。"""
  return {"description": text}


@dataclass(frozen=True)
class TensorRef:
  """与具体模型后端无关的内部张量位置引用。"""

  module: str | None = field(
      default=None, metadata=_description("可选的后端精确模块路径。"))
  layer: int | None = field(
      default=None, metadata=_description("可选的零基层索引。"))
  component: str | None = field(
      default=None, metadata=_description("resid_pre、resid_post、attention_output、mlp_output 等逻辑组件。"))
  token: int | tuple[int | None, int | None] | None = field(
      default=None, metadata=_description("token 索引或半开区间；None 表示保留全部 token。"))
  head: int | None = field(
      default=None, metadata=_description("可选 attention head 索引；仅后端明确支持时可用。"))
  call_index: int = field(
      default=0, metadata=_description("共享模块在一次前向中的零基调用序号。"))
  io: Literal["input", "output"] = field(
      default="output", metadata=_description("读取或修改模块输入或输出张量。"))
  tensor_index: int = field(
      default=0, metadata=_description("tuple/list 输入输出中的张量索引。"))

  def __post_init__(self) -> None:
    module = self.module.strip() if isinstance(self.module, str) else self.module
    component = self.component.strip() if isinstance(self.component, str) else self.component
    if not module and self.layer is None:
      raise ValueError("TensorRef 必须声明 module 或 layer")
    if self.layer is not None and (type(self.layer) is not int or self.layer < 0):
      raise ValueError("layer 必须是非负整数或 None")
    if component == "":
      raise ValueError("component 不能是空字符串")
    if self.head is not None and (type(self.head) is not int or self.head < 0):
      raise ValueError("head 必须是非负整数或 None")
    if type(self.call_index) is not int or self.call_index < 0:
      raise ValueError("call_index 必须是非负整数")
    if type(self.tensor_index) is not int or self.tensor_index < 0:
      raise ValueError("tensor_index 必须是非负整数")
    if self.io not in {"input", "output"}:
      raise ValueError("io 只支持 input 或 output")
    token = self.token
    if isinstance(token, tuple):
      if len(token) != 2 or any(item is not None and type(item) is not int for item in token):
        raise ValueError("token 区间必须是 (start, stop)")
    elif token is not None and type(token) is not int:
      raise TypeError("token 必须是整数、区间或 None")
    object.__setattr__(self, "module", module)
    object.__setattr__(self, "component", component)

  @property
  def key(self) -> str:
    """返回可作为轨迹索引和工件地址的稳定文本键。"""
    token = self.token
    if isinstance(token, tuple):
      token_text = f"{token[0]}:{token[1]}"
    else:
      token_text = "all" if token is None else str(token)
    location = self.module or f"layer:{self.layer}:{self.component or 'output'}"
    head = "all" if self.head is None else str(self.head)
    return (f"{location}|{self.io}:{self.tensor_index}|token:{token_text}|"
            f"head:{head}|call:{self.call_index}")

  def to_dict(self) -> dict:
    """返回可写入配置或工件清单的标准结构。"""
    return {
        "module": self.module,
        "layer": self.layer,
        "component": self.component,
        "token": list(self.token) if isinstance(self.token, tuple) else self.token,
        "head": self.head,
        "call_index": self.call_index,
        "io": self.io,
        "tensor_index": self.tensor_index,
    }


@dataclass(frozen=True)
class ResolvedTensorRef:
  """模型适配器把逻辑位置解析成精确 Hook 地址后的结果。"""

  requested: TensorRef = field(metadata=_description("调用方提交的逻辑位置。"))
  module: str = field(metadata=_description("model.named_modules() 中的精确模块路径。"))
  io: Literal["input", "output"] = field(metadata=_description("Hook 读取模块输入或输出。"))
  tensor_index: int = field(metadata=_description("tuple/list 中的目标张量索引。"))

  def __post_init__(self) -> None:
    if not isinstance(self.module, str) or not self.module.strip():
      raise ValueError("ResolvedTensorRef.module 必须是非空字符串")
    if self.io not in {"input", "output"}:
      raise ValueError("ResolvedTensorRef.io 只支持 input 或 output")
    if type(self.tensor_index) is not int or self.tensor_index < 0:
      raise ValueError("tensor_index 必须是非负整数")
    object.__setattr__(self, "module", self.module.strip())


@dataclass(frozen=True)
class TracePolicy:
  """限制一次前向允许采集的位置、存储和计算图生命周期。"""

  refs: Sequence[TensorRef] = field(
      default_factory=tuple, metadata=_description("需要采集的显式张量位置。"))
  profile: Literal["none", "selected", "full"] = field(
      default="selected", metadata=_description("禁用、选择性采集或显式全量采集。"))
  store: Literal["memory", "cpu", "disk"] = field(
      default="cpu", metadata=_description("激活保存在原设备、CPU 或外部 TraceStore。"))
  detach: bool = field(
      default=True, metadata=_description("是否从计算图分离采集值。"))
  retain_graph: bool = field(
      default=False, metadata=_description("是否保留计算图供调用方反向传播。"))
  retain_gradients: bool = field(
      default=False, metadata=_description("是否为所选激活注册梯度采集。"))
  precision: Literal["preserve", "float32", "float16", "bfloat16"] = field(
      default="preserve", metadata=_description("分离后工件使用的数值精度。"))
  max_records: int = field(
      default=4096, metadata=_description("单次前向最多保存的激活记录数。"))
  max_bytes: int | None = field(
      default=None, metadata=_description("可选的单次轨迹近似字节上限。"))

  def __post_init__(self) -> None:
    refs = tuple(self.refs)
    if len({item.key for item in refs}) != len(refs):
      raise ValueError("TracePolicy.refs 不能重复")
    if self.profile == "none" and refs:
      raise ValueError("profile=none 时不能声明 refs")
    if self.profile == "selected" and not refs:
      object.__setattr__(self, "profile", "none")
    if self.retain_gradients and (self.detach or self.store != "memory"):
      raise ValueError("梯度采集必须使用 store=memory 且 detach=False")
    if self.retain_graph and self.detach:
      raise ValueError("retain_graph=True 时不能 detach")
    if not self.detach and self.store != "memory":
      raise ValueError("保留计算图时只支持 store=memory")
    if type(self.max_records) is not int or self.max_records < 1:
      raise ValueError("max_records 必须是正整数")
    if self.max_bytes is not None and (type(self.max_bytes) is not int or self.max_bytes < 1):
      raise ValueError("max_bytes 必须是正整数或 None")
    object.__setattr__(self, "refs", refs)

  @property
  def enabled(self) -> bool:
    """返回本策略是否实际请求内部状态。"""
    return self.profile != "none"
