"""可控本地模型适配器的内置注册。"""

from stegopot.domain.interface.plugin import BuildContext, ComponentDefinition
from stegopot.domain.interface.registration import Plugin
from stegopot.domain.model.capability import Capability
from stegopot.domain.model.diagnostic import Diagnostic
from stegopot.infrastructure.model_adapters.huggingface import HuggingFaceAdapter


def definitions() -> tuple[ComponentDefinition, ...]:
  """返回唯一内置白盒后端；其他模型生态由外部插件实现。"""
  registry = Plugin("core", "2.0.0")
  schema = {
      "type": "object", "additionalProperties": False,
      "required": ["model_path"],
      "properties": {
          "model_path": {
              "type": "string", "minLength": 1,
              "description": "本地模型目录或 Hugging Face 模型 ID。"},
          "tokenizer_path": {
              "type": "string", "minLength": 1,
              "description": "可选 tokenizer 目录或 ID。"},
          "revision": {
              "type": "string", "minLength": 1,
              "description": "用于复现的模型提交、标签或分支。"},
          "device": {
              "type": "string", "minLength": 1, "default": "auto",
              "description": "auto、cpu、cuda、mps 或 PyTorch 设备名。"},
          "dtype": {
              "enum": ["auto", "float32", "float16", "bfloat16"],
              "default": "auto", "description": "模型加载精度。"},
          "trust_remote_code": {
              "type": "boolean", "default": False,
              "description": "是否允许执行模型仓库自定义代码。"},
          "local_files_only": {
              "type": "boolean", "default": True,
              "description": "是否禁止运行时从 Hub 下载。"},
          "use_safetensors": {
              "type": "boolean", "default": True,
              "description": "是否优先加载 safetensors 权重。"},
      },
  }

  def preflight(config, context):
    """报告可复现性与代码执行风险，不加载模型。"""
    issues = []
    if config.get("trust_remote_code", False):
      issues.append(Diagnostic(
          "runtime.remote_code_enabled", context.path + ".trust_remote_code",
          "模型允许执行仓库自定义代码",
          "仅对已审查并固定 revision 的模型启用", severity="warning"))
    if not config.get("local_files_only", True):
      issues.append(Diagnostic(
          "runtime.network_loading_enabled", context.path + ".local_files_only",
          "运行时可能访问 Hugging Face Hub",
          "正式实验应使用固定本地快照", severity="warning"))
    if not config.get("revision"):
      issues.append(Diagnostic(
          "runtime.revision_unpinned", context.path + ".revision",
          "模型没有声明固定 revision",
          "填写提交哈希或记录本地模型摘要", severity="warning"))
    return tuple(issues)

  capabilities = tuple(Capability)

  @registry.component(
      "model_adapter", "huggingface", schema=schema, preflight=preflight,
      provides=capabilities)
  def huggingface(config: dict, context: BuildContext) -> HuggingFaceAdapter:
    """构造 Hugging Face 可控运行适配器。"""
    del context
    return HuggingFaceAdapter(**config)

  return registry().components
