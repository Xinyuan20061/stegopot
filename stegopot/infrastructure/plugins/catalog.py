"""显式允许列表、版本校验和组件注册表。"""

from collections.abc import Mapping, Sequence
from importlib import metadata
import hashlib
import inspect
from pathlib import Path
import sys
from typing import Any

from jsonschema import Draft202012Validator
from packaging.specifiers import SpecifierSet
from packaging.version import Version

from stegopot.domain.interface.plugin import API_VERSION, ComponentDefinition, PluginDefinition
from stegopot.domain.model.experiment import ComponentSpec, json_copy


ENTRY_POINT_GROUP = "stegopot.plugins"


def installed_plugins() -> list[dict[str, str]]:
  """只读取已安装包的 entry points 元数据，不导入第三方插件代码。"""
  return sorted([
      {"id": point.name, "distribution": point.dist.name,
       "version": point.dist.version, "entry_point": point.value}
      for point in metadata.entry_points(group=ENTRY_POINT_GROUP)
  ], key=lambda item: (item["id"], item["distribution"]))


class PluginCatalog:
  """一次配置解析使用一个注册表，不共享全局可变注册状态。"""

  def __init__(self, builtin: PluginDefinition) -> None:
    """注册 builtin 内置能力，第三方能力必须通过 load 显式允许。"""
    self._plugins: dict[str, PluginDefinition] = {}
    self._components: dict[str, ComponentDefinition] = {}
    self._distributions: dict[str, dict[str, str]] = {}
    self._frozen = False
    self.add(builtin)

  def add(self, plugin: PluginDefinition) -> None:
    """校验并原子注册 plugin；用于可信内置能力和契约测试。"""
    if self._frozen:
      raise RuntimeError("实验注册表已经固定，请为下一次实验创建新注册表")
    if not isinstance(plugin, PluginDefinition):
      raise TypeError("插件入口必须返回 PluginDefinition")
    if plugin.plugin_id in self._plugins:
      raise ValueError(f"插件 ID 重复：{plugin.plugin_id}")
    api = Version(plugin.api_version)
    host = Version(API_VERSION)
    if api.major != host.major or api > host:
      raise ValueError(f"插件 {plugin.plugin_id} 的接口版本 {api} 与宿主 {host} 不兼容")
    Version(plugin.version)
    for component in plugin.components:
      if component.component_id in self._components:
        raise ValueError(f"组件 ID 重复：{component.component_id}")
      schema = component.config_schema
      Draft202012Validator.check_schema(schema)
      if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        raise ValueError("插件配置必须为拒绝未知字段的对象 schema")
      self._reject_remote_refs(schema)
    self._plugins[plugin.plugin_id] = plugin
    self._components.update({item.component_id: item for item in plugin.components})

  def load(self, requests: Sequence[str | Mapping[str, str]]) -> None:
    """加载 requests 明确允许的已安装插件；不安装软件，不导入其他已安装插件。"""
    if self._frozen:
      raise RuntimeError("实验注册表已经固定，不能在运行中加载插件")
    available: dict[str, list] = {}
    for point in metadata.entry_points(group=ENTRY_POINT_GROUP):
      available.setdefault(point.name, []).append(point)
    for request in requests:
      name = request if isinstance(request, str) else request["id"]
      version_spec = "" if isinstance(request, str) else request.get("version", "")
      matches = available.get(name, [])
      if len(matches) != 1:
        reason = "尚未安装" if not matches else "存在重名 entry point"
        raise ValueError(f"插件 {name} {reason}；请在当前解释器环境中检查安装")
      point = matches[0]
      if Version(point.dist.version) not in SpecifierSet(version_spec):
        raise ValueError(f"插件 {name} 版本 {point.dist.version} 不满足 {version_spec}")
      definition = point.load()()
      if definition.plugin_id != name or definition.version != point.dist.version:
        raise ValueError(f"插件 {name} 的声明与安装包元数据不一致")
      self.add(definition)
      self._distributions[name] = {"distribution": point.dist.name, "version": point.dist.version,
                                    "entry_point": point.value}

  def validate(self, spec: ComponentSpec, kind: str) -> ComponentDefinition:
    """验证 spec 引用存在、属于 kind，且参数满足声明；返回组件定义。"""
    definition = self._components.get(spec.type)
    if definition is None:
      raise ValueError(f"未注册组件：{spec.type}；插件必须在配置 plugins 中启用")
    if definition.kind != kind:
      raise ValueError(f"组件 {spec.type} 是 {definition.kind}，不能用作 {kind}")
    errors = sorted(Draft202012Validator(definition.config_schema).iter_errors(spec.config),
                    key=lambda item: str(list(item.absolute_path)))
    if errors:
      error = errors[0]
      path = ".".join(str(item) for item in error.absolute_path) or "config"
      # 不输出配置原值，避免错误消息意外打印调用者误填的凭证。
      raise ValueError(f"组件 {spec.type} 的 {path} 未通过 {error.validator} 校验")
    return definition

  def kind_of(self, component_id: str) -> str:
    """返回已注册 component_id 的能力类型，用于未使用资源的结构预检。"""
    if component_id not in self._components:
      raise ValueError(f"未注册组件：{component_id}")
    return self._components[component_id].kind

  def freeze(self) -> None:
    """固定本次实验的注册清单；后续调用 add/load 将被拒绝。"""
    self._frozen = True

  def describe(self) -> list[dict[str, Any]]:
    """返回不包含工厂对象的完整组件清单，可用于配置编辑器和锁定清单。"""
    return [{
        "id": plugin.plugin_id, "version": plugin.version, "api_version": plugin.api_version,
        **self._distributions.get(plugin.plugin_id, {}),
        "components": [{"id": item.component_id, "kind": item.kind,
                        "config_schema": json_copy(item.config_schema),
                        "references": dict(item.references), "credentials": list(item.credentials)}
                       for item in plugin.components],
    } for plugin in self._plugins.values()]

  def source_fingerprints(self) -> list[dict[str, Any]]:
    """计算已注册工厂所属包的 Python 源码摘要；不导入未启用扩展。"""
    roots = {}
    for definition in self._components.values():
      module_name = definition.factory.__module__.split('.')[0]
      module = sys.modules.get(module_name)
      locations = getattr(module, '__path__', ())
      if locations:
        roots[module_name] = Path(next(iter(locations))).resolve()
      else:
        source = inspect.getsourcefile(definition.factory)
        if source:
          roots[module_name] = Path(source).resolve()
    results = []
    for name, root in sorted(roots.items()):
      checksum = hashlib.sha256()
      paths = [root] if root.is_file() else sorted(root.rglob('*.py'))
      count = 0
      for path in paths:
        if '__pycache__' in path.parts:
          continue
        checksum.update((path.name if root.is_file() else path.relative_to(root).as_posix()).encode())
        checksum.update(b'\x00')
        checksum.update(path.read_bytes())
        count += 1
      results.append({'package': name, 'python_files': count, 'sha256': checksum.hexdigest()})
    return results

  @staticmethod
  def _reject_remote_refs(value: Any) -> None:
    """拒绝 value 中需要网络或文件读取的 schema 引用，验证过程保持离线。"""
    if isinstance(value, Mapping):
      for key, item in value.items():
        if key in {"$ref", "$dynamicRef"} and (not isinstance(item, str) or not item.startswith("#")):
          raise ValueError("插件 schema 只允许文档内部引用")
        PluginCatalog._reject_remote_refs(item)
    elif isinstance(value, list):
      for item in value:
        PluginCatalog._reject_remote_refs(item)
