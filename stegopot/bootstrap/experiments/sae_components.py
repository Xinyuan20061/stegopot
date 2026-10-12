"""内置公开 SAE 资源的配置注册。"""

from stegopot.domain.interface.plugin import BuildContext, ComponentDefinition
from stegopot.domain.interface.registration import Plugin
from stegopot.domain.model.diagnostic import Diagnostic, PreflightContext
from stegopot.infrastructure.integrations.sae import SAELensLoader, SAERuntime


def definitions() -> tuple[ComponentDefinition, ...]:
  """返回可从实验配置加载 SAE Lens 公开权重的资源组件。"""
  registry = Plugin("core", "2.1.0")
  positive_integer = {"type": "integer", "minimum": 1}
  optional_text = {"type": ["string", "null"], "minLength": 1}
  schema = {
      "type": "object", "additionalProperties": False,
      "required": ["source"],
      "properties": {
          "source": {
              "type": "string", "minLength": 1,
              "description": "SAE Lens release 名或本地权重目录。",
          },
          "sae_id": {
              **optional_text,
              "description": "release 内的 SAE ID；本地目录可省略。",
          },
          "source_kind": {
              "enum": ["pretrained", "local"], "default": "pretrained",
              "description": "从公开预训练 release 或本地目录加载。",
          },
          "device": {
              "type": "string", "minLength": 1, "default": "cpu",
              "description": "加载和执行 SAE 的 PyTorch 设备。",
          },
          "dtype": {
              "enum": ["float32", "float16", "bfloat16"],
              "default": "float32",
              "description": "SAE 参数和输入使用的数据类型。",
          },
          "force_download": {
              "type": "boolean", "default": False,
              "description": "是否忽略本地缓存重新下载公开权重。",
          },
          "expected_model_id": {
              **optional_text,
              "description": "必须与 SAE 元数据完全一致的基础模型 ID。",
          },
          "expected_hook_name": {
              **optional_text,
              "description": "必须与 SAE 元数据完全一致的激活位置名称。",
          },
          "expected_input_width": {
              **positive_integer,
              "description": "调用方预期的 SAE 输入宽度。",
          },
          "expected_feature_width": {
              **positive_integer,
              "description": "调用方预期的 SAE 特征宽度。",
          },
      },
      "allOf": [{
          "if": {"properties": {"source_kind": {"const": "pretrained"}}},
          "then": {"required": ["sae_id"]},
      }],
  }

  @registry.component("sae", "saelens", schema=schema, preflight=_preflight)
  def saelens(config: dict, context: BuildContext) -> SAERuntime:
    """按配置加载公开 SAE；实验特征语义由外部插件定义。"""
    del context
    return SAELensLoader(**config).load()

  return registry().components


def _preflight(config: dict, context: PreflightContext) -> tuple[Diagnostic, ...]:
  """在下载权重前指出可复现性和兼容性声明缺口。"""
  diagnostics = []
  if config.get("source_kind", "pretrained") == "pretrained":
    diagnostics.append(Diagnostic(
        code="sae.remote_resource", path=context.path,
        message="首次运行可能从公开仓库下载 SAE 权重",
        hint="固定 release 与 sae_id，并保留生成的 SAE manifest",
        severity="info", component="core.saelens"))
  missing = [name for name in (
      "expected_model_id", "expected_hook_name", "expected_input_width")
      if config.get(name) is None]
  if missing:
    diagnostics.append(Diagnostic(
        code="sae.compatibility_partially_unpinned", path=context.path,
        message="SAE 兼容性约束未全部固定",
        hint="正式实验请填写 expected_model_id、expected_hook_name 和 expected_input_width",
        severity="warning", component="core.saelens"))
  return tuple(diagnostics)
