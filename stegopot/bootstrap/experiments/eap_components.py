"""内置 EAP Analyzer 的配置注册。"""

from stegopot.domain.interface.plugin import BuildContext, ComponentDefinition
from stegopot.domain.interface.registration import Plugin
from stegopot.domain.model.attribution import EAPEdge
from stegopot.domain.model.capability import Capability
from stegopot.domain.model.reference import TensorRef
from stegopot.infrastructure.integrations.eap import EAPAnalyzer


def _tensor_ref_schema() -> dict:
  """返回拒绝未知字段的 TensorRef 配置模式。"""
  return {
      "type": "object", "additionalProperties": False,
      "properties": {
          "module": {"type": "string", "minLength": 1,
                     "description": "可选的 model.named_modules 精确路径。"},
          "layer": {"type": "integer", "minimum": 0,
                    "description": "可选零基层索引。"},
          "component": {"type": "string", "minLength": 1,
                        "description": "可选逻辑组件名。"},
          "token": {"oneOf": [
              {"type": "integer"},
              {"type": "array", "minItems": 2, "maxItems": 2,
               "items": {"type": ["integer", "null"]}},
              {"type": "null"}],
                    "description": "token 索引、半开区间或全部 token。"},
          "head": {"type": "integer", "minimum": 0,
                   "description": "后端明确支持时使用的 attention head。"},
          "call_index": {"type": "integer", "minimum": 0, "default": 0,
                         "description": "共享模块在一次前向中的调用序号。"},
          "io": {"enum": ["input", "output"], "default": "output",
                 "description": "读取模块输入或输出。"},
          "tensor_index": {"type": "integer", "minimum": 0, "default": 0,
                           "description": "tuple/list 中的张量索引。"},
      },
      "anyOf": [{"required": ["module"]}, {"required": ["layer"]}],
  }


def definitions() -> tuple[ComponentDefinition, ...]:
  """返回可由 schema_version=2 配置调用的基础 EAP Analyzer。"""
  registry = Plugin("core", "2.1.0")
  edge = {
      "type": "object", "additionalProperties": False,
      "required": ["id", "source", "target"],
      "properties": {
          "id": {"type": "string", "minLength": 1,
                 "description": "计算图内唯一的候选边 ID。"},
          "source": _tensor_ref_schema(),
          "target": _tensor_ref_schema(),
          "metadata": {"type": "object",
                       "description": "层、组件和图版本等非张量说明。"},
      },
  }
  schema = {
      "type": "object", "additionalProperties": False,
      "required": ["edges"],
      "properties": {
          "edges": {"type": "array", "minItems": 1, "items": edge,
                    "description": "由模型图适配器明确声明的 writer-reader 边。"},
          "reduction": {"enum": ["sum", "mean"], "default": "sum",
                        "description": "逐元素 attribution 的归约方式。"},
          "analyzer_id": {"type": "string", "minLength": 1,
                          "default": "core.eap",
                          "description": "输出记录中的分析器 ID。"},
      },
  }

  @registry.component(
      "analyzer", "eap", schema=schema,
      requires=(Capability.ACTIVATION_READ, Capability.GRADIENT_READ))
  def eap(config: dict, context: BuildContext) -> EAPAnalyzer:
    """根据配置构造通用 EAP Analyzer。"""
    del context
    edges = tuple(EAPEdge(
        item["id"], _tensor_ref(item["source"]), _tensor_ref(item["target"]),
        item.get("metadata", {})) for item in config["edges"])
    return EAPAnalyzer(
        edges, reduction=config.get("reduction", "sum"),
        analyzer_id=config.get("analyzer_id", "core.eap"))

  return registry().components


def _tensor_ref(value: dict) -> TensorRef:
  """把已通过 schema 的 JSON 数据转换为 TensorRef。"""
  token = value.get("token")
  if isinstance(token, list):
    token = tuple(token)
  return TensorRef(
      module=value.get("module"), layer=value.get("layer"),
      component=value.get("component"), token=token,
      head=value.get("head"), call_index=value.get("call_index", 0),
      io=value.get("io", "output"), tensor_index=value.get("tensor_index", 0))
