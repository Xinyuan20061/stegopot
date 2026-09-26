"""独立分析配置读取；不改变现有实验 YAML 顶层 schema。"""

from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
import yaml

from stegopot.infrastructure.recorders.audit.integrity import digest


ANALYSIS_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object", "additionalProperties": False,
    "required": ["schema_version", "secret", "labels", "matched_groups", "surface",
                 "localizer", "protocol"],
    "properties": {
        "schema_version": {"const": "stegopot.analysis/1"},
        "secret": {"type": "object", "additionalProperties": False,
                   "required": ["name", "kind", "source"],
                   "properties": {
                       "name": {"type": "string", "minLength": 1},
                       "kind": {"enum": ["categorical", "bitstring"]},
                       "source": {"type": "string", "minLength": 1},
                       "classes": {"type": "array", "uniqueItems": True,
                                   "items": {"type": "string", "minLength": 1}},
                   }},
        "labels": {"type": "object", "minProperties": 1,
                   "additionalProperties": {"type": "string", "minLength": 1}},
        "matched_groups": {"type": "object", "minProperties": 1,
                           "additionalProperties": {"type": "string", "minLength": 1}},
        "surface": {"enum": ["activation", "kv", "logits", "token", "cot", "tool",
                               "memory", "timing", "behavior"]},
        "selection": {"type": "object", "additionalProperties": False,
                      "properties": {
                          "agent_id": {"type": "string", "minLength": 1},
                          "recipient": {"type": "string", "minLength": 1},
                          "rounds": {"type": "array", "uniqueItems": True,
                                     "items": {"type": "integer", "minimum": 0}},
                          "flow_order": {"type": "number",
                                         "description": "跨表面路径中的预注册顺序。"},
                      }},
        "representation_bundles": {"type": "array", "uniqueItems": True,
                                   "items": {"type": "string", "minLength": 1}},
        "localizer": {"type": "object", "additionalProperties": False,
                      "required": ["type"],
                      "properties": {
                          "type": {"enum": ["text", "vector", "structured"]},
                          "config": {"type": "object"},
                      }},
        "split": {"type": "object", "additionalProperties": False,
                  "properties": {
                      "train_ratio": {"type": "number", "exclusiveMinimum": 0},
                      "validation_ratio": {"type": "number", "exclusiveMinimum": 0},
                      "test_ratio": {"type": "number", "exclusiveMinimum": 0},
                      "seed": {"type": "integer"},
                  }},
        "null_test": {"type": "object", "additionalProperties": False,
                      "properties": {
                          "repetitions": {"type": "integer", "minimum": 1},
                          "alpha": {"type": "number", "exclusiveMinimum": 0,
                                    "exclusiveMaximum": 1},
                      }},
        "aggregation": {"type": "object", "additionalProperties": False,
                        "properties": {"top_k": {"type": "integer", "minimum": 1}}},
        "bootstrap_repetitions": {"type": "integer", "minimum": 1},
        "minimum_samples": {"type": "integer", "minimum": 3},
        "protocol": {"type": "object", "additionalProperties": False,
                     "required": ["task_distribution", "secret_distribution", "topology",
                                  "model_family", "sampling", "capture", "intervention",
                                  "evaluator"],
                     "properties": {name: {"type": "string", "minLength": 1} for name in (
                         "task_distribution", "secret_distribution", "topology", "model_family",
                         "sampling", "capture", "intervention", "evaluator")}},
    },
}


class _UniqueSafeLoader(yaml.SafeLoader):
  """拒绝 YAML 重复键的安全加载器。"""


def _unique_mapping(loader: _UniqueSafeLoader, node: yaml.MappingNode) -> dict[str, Any]:
  """构造映射并拒绝同层重复键。"""
  result = {}
  for key_node, value_node in node.value:
    key = loader.construct_object(key_node, deep=False)
    if key in result:
      raise ValueError(f"分析配置包含重复键：{key}")
    result[key] = loader.construct_object(value_node, deep=True)
  return result


_UniqueSafeLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def load_analysis_config(path: str | Path) -> tuple[dict[str, Any], Path]:
  """读取并严格校验独立 YAML/JSON 分析配置。"""
  source = Path(path).expanduser().resolve()
  text = source.read_text(encoding="utf-8")
  if source.suffix.lower() == ".json":
    value = json.loads(text, object_pairs_hook=_unique_json_mapping)
  elif source.suffix.lower() in {".yaml", ".yml"}:
    if any(isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken))
           for token in yaml.scan(text)):
      raise ValueError("分析配置不允许 YAML 锚点或别名")
    value = yaml.load(text, Loader=_UniqueSafeLoader)
  else:
    raise ValueError("分析配置只支持 .json/.yaml/.yml")
  errors = sorted(Draft202012Validator(ANALYSIS_SCHEMA).iter_errors(value),
                  key=lambda item: list(item.path))
  if errors:
    first = errors[0]
    location = ".".join(str(item) for item in first.path) or "$"
    raise ValueError(f"分析配置 {location}：{first.message}")
  ratios = value.get("split", {})
  total = sum(float(ratios.get(name, default)) for name, default in (
      ("train_ratio", 0.6), ("validation_ratio", 0.2), ("test_ratio", 0.2)))
  if abs(total - 1.0) > 1e-9:
    raise ValueError("split 三项比例总和必须为 1")
  surface = value["surface"]
  if surface not in {"token", "activation", "kv", "logits"}:
    raise ValueError(
        f"{surface} 表面已预留领域协议，但当前内置采集链尚未实现；unsupported 不能记为零分")
  expected = {"token": "text", "cot": "text", "activation": "vector",
              "kv": "vector", "logits": "vector", "tool": "structured",
              "memory": "structured", "timing": "structured", "behavior": "structured"}
  if value["localizer"]["type"] != expected[surface]:
    raise ValueError(f"{surface} 表面必须使用 {expected[surface]} localizer")
  if surface != "token" and not value.get("representation_bundles"):
    raise ValueError("非公开文本表面必须声明 representation_bundles")
  return value, source


def _unique_json_mapping(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
  """拒绝 JSON 对象重复键。"""
  result = {}
  for key, value in pairs:
    if key in result:
      raise ValueError(f"分析配置包含重复键：{key}")
    result[key] = value
  return result


def analysis_protocol_fingerprint(config: Mapping[str, Any]) -> str:
  """计算不含实际标签、运行路径和样本身份的可比协议指纹。"""
  comparable = {
      "schema_version": config["schema_version"], "secret": config["secret"],
      "surface": config["surface"], "selection": config.get("selection", {}),
      "localizer": config["localizer"], "split": config.get("split", {}),
      "null_test": config.get("null_test", {}),
      "aggregation": config.get("aggregation", {}),
      "bootstrap_repetitions": config.get("bootstrap_repetitions", 200),
      "minimum_samples": config.get("minimum_samples", 6),
      "protocol": config["protocol"],
  }
  return digest(comparable)
