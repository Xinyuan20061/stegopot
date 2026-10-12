"""SAE Lens 公开权重的延迟加载适配器。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
import inspect
from typing import Any, Literal

from stegopot.domain.model.sae import SAECompatibilityError, SAEManifest
from stegopot.infrastructure.integrations.sae.runtime import SAERuntime


def _description(text: str) -> dict[str, str]:
  return {"description": text}


@dataclass(frozen=True)
class SAELensLoader:
  """从 SAE Lens release 或本地目录加载公开 SAE。"""

  source: str = field(metadata=_description("SAE Lens release 名或本地目录。"))
  sae_id: str | None = field(
      default=None, metadata=_description("release 内的 SAE ID；本地目录可省略。"))
  source_kind: Literal["pretrained", "local"] = field(
      default="pretrained", metadata=_description("公开预训练来源或本地目录。"))
  device: str = field(
      default="cpu", metadata=_description("加载和执行 SAE 的 PyTorch 设备。"))
  dtype: Literal["float32", "float16", "bfloat16"] = field(
      default="float32", metadata=_description("SAE 参数和输入使用的数据类型。"))
  force_download: bool = field(
      default=False, metadata=_description("是否忽略缓存重新下载公开权重。"))
  expected_model_id: str | None = field(
      default=None, metadata=_description("必须与权重元数据一致的基础模型 ID。"))
  expected_hook_name: str | None = field(
      default=None, metadata=_description("必须与权重元数据一致的激活位置名称。"))
  expected_input_width: int | None = field(
      default=None, metadata=_description("调用方预期的 SAE 输入宽度。"))
  expected_feature_width: int | None = field(
      default=None, metadata=_description("调用方预期的 SAE 特征宽度。"))

  def __post_init__(self) -> None:
    if not isinstance(self.source, str) or not self.source.strip():
      raise ValueError("source 必须是非空字符串")
    if self.source_kind not in {"pretrained", "local"}:
      raise ValueError("source_kind 必须是 pretrained 或 local")
    if self.source_kind == "pretrained" and not self.sae_id:
      raise ValueError("公开预训练 SAE 必须提供 sae_id")
    if self.dtype not in {"float32", "float16", "bfloat16"}:
      raise ValueError("不支持的 SAE dtype")
    for name in ("expected_input_width", "expected_feature_width"):
      value = getattr(self, name)
      if value is not None and (type(value) is not int or value <= 0):
        raise ValueError(f"{name} 必须为空或正整数")
    object.__setattr__(self, "source", self.source.strip())

  def load(self) -> SAERuntime:
    """加载权重、提取清单并执行严格兼容性检查。"""
    sae_class = _sae_class()
    if self.source_kind == "local":
      raw = _call_supported(
          sae_class.load_from_disk,
          {"path": self.source, "device": self.device, "dtype": self.dtype})
      backend, config, sparsity = _normalize_result(raw)
      resolved_id = self.sae_id or self.source
    else:
      method = getattr(sae_class, "from_pretrained_with_cfg_and_sparsity", None)
      if not callable(method):
        method = sae_class.from_pretrained
      raw = _call_supported(method, {
          "release": self.source, "sae_id": self.sae_id,
          "device": self.device, "dtype": self.dtype,
          "force_download": self.force_download,
      })
      backend, config, sparsity = _normalize_result(raw)
      resolved_id = self.sae_id or self.source
    config = _config_dict(config or getattr(backend, "cfg", None))
    manifest = _manifest(
        backend=backend, config=config, source=self.source,
        source_kind=self.source_kind, sae_id=resolved_id, dtype=self.dtype,
        sparsity=sparsity)
    self._validate(manifest)
    if callable(getattr(backend, "eval", None)):
      backend.eval()
    if callable(getattr(backend, "requires_grad_", None)):
      backend.requires_grad_(False)
    return SAERuntime(backend, manifest, device=self.device, dtype=self.dtype)

  def _validate(self, manifest: SAEManifest) -> None:
    """按调用方声明检查模型身份、hook 和两个张量宽度。"""
    checks = (
        ("基础模型 ID", self.expected_model_id, manifest.base_model_id),
        ("激活位置", self.expected_hook_name, manifest.hook_name),
        ("输入宽度", self.expected_input_width, manifest.input_width),
        ("特征宽度", self.expected_feature_width, manifest.feature_width),
    )
    for label, expected, actual in checks:
      if expected is not None and actual != expected:
        raise SAECompatibilityError(
            f"SAE {label}不兼容：期望 {expected!r}，实际 {actual!r}")


def _manifest(*, backend: Any, config: Mapping[str, Any], source: str,
              source_kind: str, sae_id: str, dtype: str,
              sparsity: Any) -> SAEManifest:
  """从不同 SAE Lens 版本的配置中提取稳定清单字段。"""
  metadata = config.get("metadata")
  metadata = dict(metadata) if isinstance(metadata, Mapping) else {}
  input_width = _positive_int(
      config.get("d_in"), getattr(backend, "d_in", None), "d_in")
  output_width = config.get("d_out")
  if output_width is not None and output_width != input_width:
    raise SAECompatibilityError(
        "当前 core.saelens 只接受输入与重构空间相同的 SAE；"
        "transcoder 应由独立实验插件适配")
  feature_width = _positive_int(
      config.get("d_sae"), getattr(backend, "d_sae", None), "d_sae")
  base_model_id = _first_text(
      metadata.get("model_name"), metadata.get("model_id"),
      config.get("model_name"), config.get("model_id"))
  hook_name = _first_text(metadata.get("hook_name"), config.get("hook_name"))
  architecture = _first_text(config.get("architecture"), type(backend).__name__)
  try:
    library_version = version("sae-lens")
  except PackageNotFoundError:
    library_version = None
  details = {"sae_lens_config": dict(config)}
  if sparsity is not None:
    details["sparsity_metadata"] = {
        "available": True, "type": type(sparsity).__name__}
  return SAEManifest(
      sae_id=sae_id, source=source, source_kind=source_kind,
      input_width=input_width, feature_width=feature_width,
      architecture=architecture or type(backend).__name__, dtype=dtype,
      base_model_id=base_model_id, hook_name=hook_name,
      library_version=library_version, metadata=details)


def _normalize_result(value: Any) -> tuple[Any, Any, Any]:
  """兼容 SAE Lens 返回单对象、二元组或三元组的版本差异。"""
  if not isinstance(value, tuple):
    return value, None, None
  if not value:
    raise RuntimeError("SAE Lens 返回了空加载结果")
  return value[0], value[1] if len(value) > 1 else None, value[2] if len(value) > 2 else None


def _call_supported(method: Any, values: Mapping[str, Any]) -> Any:
  """只向当前 SAE Lens 版本传递其显式支持的关键字参数。"""
  signature = inspect.signature(method)
  accepts_extra = any(
      item.kind == inspect.Parameter.VAR_KEYWORD
      for item in signature.parameters.values())
  kwargs = {
      key: value for key, value in values.items()
      if value is not None and (accepts_extra or key in signature.parameters)
  }
  return method(**kwargs)


def _config_dict(value: Any) -> dict[str, Any]:
  """把 SAE Lens 配置对象规范为普通字典。"""
  if value is None:
    return {}
  if isinstance(value, Mapping):
    return dict(value)
  to_dict = getattr(value, "to_dict", None)
  if callable(to_dict):
    result = to_dict()
    if isinstance(result, Mapping):
      return dict(result)
  data = getattr(value, "__dict__", None)
  if isinstance(data, Mapping):
    return {key: item for key, item in data.items() if not key.startswith("_")}
  raise TypeError("无法读取 SAE Lens 配置")


def _positive_int(primary: Any, fallback: Any, name: str) -> int:
  """读取正整数结构字段。"""
  value = primary if primary is not None else fallback
  if type(value) is not int or value <= 0:
    raise SAECompatibilityError(f"SAE 元数据缺少有效的 {name}")
  return value


def _first_text(*values: Any) -> str | None:
  """返回第一个非空字符串。"""
  return next((value.strip() for value in values
               if isinstance(value, str) and value.strip()), None)


def _sae_class() -> Any:
  """延迟导入 SAE Lens，避免基础安装承担重依赖。"""
  try:
    from sae_lens import SAE
  except ImportError as exc:
    raise RuntimeError("加载公开 SAE 需要安装 stegopot[sae]") from exc
  return SAE
