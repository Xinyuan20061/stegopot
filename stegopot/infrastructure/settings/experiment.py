"""版本化实验配置的安全读取和结构校验。"""

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
import yaml

from stegopot.domain.model.experiment import json_copy


COMPONENT_SCHEMA = {
    "type": "object", "required": ["type"], "additionalProperties": False,
    "properties": {"type": {"type": "string", "minLength": 1}, "config": {"type": "object"}},
}
CONFIG_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object",
    "required": ["schema_version", "scenario"], "additionalProperties": False,
    "properties": {
        "schema_version": {"const": "1"},
        "plugins": {"type": "array", "uniqueItems": True, "items": {"oneOf": [
            {"type": "string", "pattern": "^[a-z][a-z0-9_-]*$"},
            {"type": "object", "required": ["id"], "additionalProperties": False,
             "properties": {"id": {"type": "string"}, "version": {"type": "string"}}},
        ]}},
        "scenario": COMPONENT_SCHEMA,
        "seed": {"type": "integer"},
        "resources": {"type": "object", "additionalProperties": COMPONENT_SCHEMA},
        "policies": {"type": "object", "additionalProperties": COMPONENT_SCHEMA},
        "topology": {"type": "object", "required": ["edges"], "additionalProperties": False,
                     "properties": {"edges": {"type": "array", "items": {
                         "type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "string"}}}}},
        "channels": {"type": "array", "items": COMPONENT_SCHEMA},
        "detectors": {"type": "array", "items": COMPONENT_SCHEMA},
        "rewards": {"type": "array", "items": COMPONENT_SCHEMA},
        "evaluators": {"type": "array", "items": COMPONENT_SCHEMA},
        "audit_sinks": {"type": "array", "items": COMPONENT_SCHEMA},
        "runtime": {"type": "object", "additionalProperties": False, "properties": {
            "max_model_calls": {"type": "integer", "minimum": 1, "maximum": 100000},
            "max_output_tokens": {"type": "integer", "minimum": 1, "maximum": 65536},
            "max_rounds": {"type": "integer", "minimum": 1, "maximum": 10000},
            "max_trials": {"type": "integer", "minimum": 1, "maximum": 10000},
            "max_seconds": {"type": "number", "exclusiveMinimum": 0},
        }},
        "audit": {"type": "object", "additionalProperties": False, "properties": {
            "required": {"const": True}, "profile": {"const": "research"},
        }},
    },
}


class _UniqueSafeLoader(yaml.SafeLoader):
  """安全 YAML 解析器，同时拒绝重复键和复杂映射键。"""


def _unique_mapping(loader: _UniqueSafeLoader, node: yaml.MappingNode) -> dict:
  """从 loader/node 构建无重复键的映射，禁止覆盖已声明的实验参数。"""
  result = {}
  for key_node, value_node in node.value:
    key = loader.construct_object(key_node)
    if not isinstance(key, str) or key in result:
      raise ValueError("配置字段必须为不重复的字符串键")
    result[key] = loader.construct_object(value_node)
  return result


_UniqueSafeLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
  """将 JSON pairs 转换为映射，重复键一律拒绝。"""
  result = {}
  for key, value in pairs:
    if key in result:
      raise ValueError("JSON 配置存在重复字段")
    result[key] = value
  return result


def validate_config(value: Any) -> dict[str, Any]:
  """校验 value 并填入框架默认值，所有返回数据均为 JSON 类型。"""
  data = json_copy(value)
  errors = list(Draft202012Validator(CONFIG_SCHEMA).iter_errors(data))
  if errors:
    path = ".".join(str(part) for part in errors[0].absolute_path) or "root"
    raise ValueError(f"实验配置 {path} 未通过 {errors[0].validator} 校验")
  defaults = {"plugins": [], "seed": 0, "resources": {}, "policies": {},
              "channels": [], "detectors": [], "rewards": [], "evaluators": [], "audit_sinks": []}
  for key, default in defaults.items():
    data.setdefault(key, default)
  data["runtime"] = {"max_model_calls": 64, "max_output_tokens": 1024,
                     "max_rounds": 100, "max_trials": 1000, "max_seconds": 3600,
                     **data.get("runtime", {})}
  data["audit"] = {"required": True, "profile": "research", **data.get("audit", {})}
  return data


def load_config(path: str | Path) -> dict[str, Any]:
  """读取 path 指向的 JSON/YAML，拒绝重复键、对象构造标签和非标准数据。"""
  source = Path(path)
  if source.stat().st_size > 2_000_000:
    raise ValueError("实验配置不能超过 2 MB；大数据集应通过插件引用")
  text = source.read_text(encoding="utf-8-sig")
  if source.suffix.lower() == ".json":
    value = json.loads(text, object_pairs_hook=_unique_pairs)
  elif source.suffix.lower() in {".yaml", ".yml"}:
    if any(isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken)) for token in yaml.scan(text)):
      raise ValueError("实验配置不接受 YAML 锚点或别名，请使用显式声明")
    value = yaml.load(text, Loader=_UniqueSafeLoader)
  else:
    raise ValueError("配置扩展名必须为 .json/.yaml/.yml")
  return validate_config(value)
