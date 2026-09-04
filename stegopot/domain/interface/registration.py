"""声明式注册便利接口，只构造契约，不发现插件或执行工厂。"""

from dataclasses import MISSING, fields, is_dataclass
from functools import wraps
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints
import types

from stegopot.domain.interface.plugin import API_VERSION, ComponentDefinition, PluginDefinition


def _schema(annotation):
  """把 annotation 的常用配置类型转换为 JSON Schema；不猜测未知类型。"""
  primitives = {str: "string", int: "integer", float: "number", bool: "boolean", type(None): "null"}
  if annotation in primitives:
    return {"type": primitives[annotation]}
  origin, args = get_origin(annotation), get_args(annotation)
  if origin is Literal:
    return {"enum": list(args)}
  if origin in (Union, types.UnionType):
    return {"anyOf": [_schema(item) for item in args]}
  if origin is list:
    return {"type": "array", "items": _schema(args[0])}
  if origin is dict and args == (str, Any):
    return {"type": "object"}
  raise TypeError(f"配置类型 {annotation} 不支持自动生成模式，请提供显式 schema")


def config_schema(config_type):
  """从 config_type 数据类生成严格模式，字段 metadata.description 作为参数说明。"""
  if not is_dataclass(config_type):
    raise TypeError("config 必须是 dataclass 类型")
  hints = get_type_hints(config_type)
  properties, required = {}, []
  for item in fields(config_type):
    if not item.init:
      continue
    schema = _schema(hints[item.name])
    description = item.metadata.get("description")
    if not description:
      raise ValueError(f"配置参数 {item.name} 必须提供 metadata.description 中文说明")
    schema["description"] = description
    if item.default is MISSING and item.default_factory is MISSING:
      required.append(item.name)
    properties[item.name] = schema
  return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


class Plugin:
  """装饰器注册器；每个扩展包使用独立实例，不污染宿主全局状态。"""

  def __init__(self, plugin_id: str, version: str, *, api_version: str = API_VERSION):
    """声明插件身份。

    参数：
      plugin_id: 组件命名空间，必须与安装包 entry point 名称一致。
      version: 插件版本，必须与安装包版本一致。
      api_version: 所需框架契约版本；默认使用当前 API 版本。
    """
    self._id, self._version, self._api = plugin_id, version, api_version
    self._components = []
    self._definition = None

  def component(self, kind: str, name: str, *, config=None, schema=None, references=None, credentials=()):
    """返回组件工厂装饰器。

    参数：
      kind: policy、codec、channel、scenario 等标准接口类型。
      name: 插件内短名称，宿主使用 plugin_id.name 调度。
      config: 可选的数据类配置；字段必须有参数说明，工厂收到已构造的数据类。
      schema: 可选显式 JSON Schema，与 config 互斥；此时工厂收到字典。
      references: 配置字段到 llm/codec 能力的声明，工厂通过 context.resource 读取。
      credentials: 模型供应商使用的凭证字段名，值为环境变量引用而非密钥。
    """
    if config is not None and schema is not None:
      raise ValueError("config 和 schema 不能同时提供")
    resolved = config_schema(config) if config is not None else schema or {
        "type": "object", "properties": {}, "additionalProperties": False}

    def register(factory):
      """登记 factory；其签名统一为 (config, context)，不得在导入时执行实验。"""
      if self._definition is not None:
        raise RuntimeError("插件定义已导出，不能在运行中增加组件")
      component_id = f"{self._id}.{name}"
      if any(item.component_id == component_id for item in self._components):
        raise ValueError(f"重复注册：{component_id}")
      @wraps(factory)
      def build(value, context):
        """将已校验 value 转成配置对象，再注入受限 context。"""
        return factory(config(**value) if config is not None else value, context)
      self._components.append(ComponentDefinition(component_id, kind, build, resolved,
                                                  dict(references or {}), tuple(credentials)))
      return factory
    return register

  def __call__(self) -> PluginDefinition:
    """导出并冻结组件列表；可直接把此实例作为 entry point 对象。"""
    if self._definition is None:
      self._definition = PluginDefinition(self._id, self._version, self._api, tuple(self._components))
    return self._definition
