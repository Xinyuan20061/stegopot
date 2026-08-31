"""StegoTool 接口到 Dwinovo StegoKit 的适配器。"""

from __future__ import annotations

from collections.abc import Mapping
import copy
import dataclasses
from typing import Any

from stegopot.domain.interface import StegoEmbedRequest
from stegopot.domain.interface import StegoEmbedResult
from stegopot.domain.interface import StegoExtractRequest
from stegopot.domain.interface import StegoExtractResult
from stegopot.infrastructure.integrations.stegokit.loader import BundledStegoKitError
from stegopot.infrastructure.integrations.stegokit.loader import load_stegokit


class StegoToolError(RuntimeError):
  """StegoKit 加载、参数转换或执行失败时抛出的异常。"""


class StegoKitAdapter:
  """把稳定的 StegoTool 请求映射到 StegoKit Dispatcher。

  StegoKit 只在未显式传入 dispatcher 时按需加载，因此普通通信场景
  不需要导入 PyTorch 或 Transformers。
  """

  def __init__(
      self,
      *,
      model: Any,
      tokenizer: Any,
      dispatcher: Any | None = None,
      verbose: bool = False,
  ) -> None:
    """初始化 StegoKit 适配器。

    参数：
      model: StegoKit 使用的本地 Transformers 因果语言模型。
      tokenizer: 与 model 匹配且配置 chat_template 的 tokenizer。
      dispatcher: 可选 StegoDispatcher；为空时从 vendor 子模块创建。
      verbose: 创建官方 dispatcher 时是否输出详细日志。
    """
    if model is None:
      raise ValueError("StegoKitAdapter.model 不能为空")
    if tokenizer is None:
      raise ValueError("StegoKitAdapter.tokenizer 不能为空")
    self._model = model
    self._tokenizer = tokenizer
    self._dispatcher = (
        dispatcher if dispatcher is not None else self._create_dispatcher(verbose)
    )

  def embed(self, request: StegoEmbedRequest) -> StegoEmbedResult:
    """调用 StegoDispatcher.embed 执行隐写编码。

    参数：
      request: 与具体工具无关的编码请求。

    返回：
      不暴露 StegoKit 具体结果类的统一编码结果。
    """
    config, material = self._resolve_bindings(
        algorithm=request.algorithm,
        config=request.config,
        material=request.material,
        encode=True,
    )
    generation = request.generation
    try:
      result = self._dispatcher.embed(
          algorithm=request.algorithm,
          model=self._model,
          tokenizer=self._tokenizer,
          secret_bits=request.secret_bits,
          messages=[dict(message) for message in request.messages],
          max_new_tokens=generation.max_new_tokens,
          temperature=generation.temperature,
          top_k=generation.top_k,
          top_p=generation.top_p,
          precision=generation.precision,
          stop_on_eos=generation.stop_on_eos,
          config=config,
          material=material,
      )
    except Exception as exc:
      raise StegoToolError(f"StegoKit 编码失败：{exc}") from exc
    return StegoEmbedResult(
        text=result.text,
        generated_token_ids=result.generated_token_ids,
        consumed_bits=result.consumed_bits,
        encode_time_seconds=getattr(result, "encode_time_seconds", 0.0),
        embedding_capacity=getattr(result, "embedding_capacity", 0.0),
        metadata=getattr(result, "metadata", {}) or {},
    )

  def extract(self, request: StegoExtractRequest) -> StegoExtractResult:
    """调用 StegoDispatcher.extract 执行隐写解码。

    参数：
      request: 与具体工具无关的解码请求。

    返回：
      不暴露 StegoKit 具体结果类的统一解码结果。
    """
    config, material = self._resolve_bindings(
        algorithm=request.algorithm,
        config=request.config,
        material=request.material,
        encode=False,
    )
    generation = request.generation
    try:
      result = self._dispatcher.extract(
          algorithm=request.algorithm,
          model=self._model,
          tokenizer=self._tokenizer,
          generated_token_ids=list(request.generated_token_ids),
          messages=[dict(message) for message in request.messages],
          temperature=generation.temperature,
          top_k=generation.top_k,
          top_p=generation.top_p,
          precision=generation.precision,
          max_bits=request.max_bits,
          config=config,
          material=material,
      )
    except Exception as exc:
      raise StegoToolError(f"StegoKit 解码失败：{exc}") from exc
    return StegoExtractResult(
        bits=result.bits,
        decode_time_seconds=getattr(result, "decode_time_seconds", 0.0),
        metadata=getattr(result, "metadata", {}) or {},
    )

  def close(self) -> None:
    """释放 dispatcher、模型和 tokenizer 提供的可选资源。"""
    close = getattr(self._dispatcher, "close", None)
    if callable(close):
      close()

  @staticmethod
  def _create_dispatcher(verbose: bool) -> Any:
    """从项目 vendor 目录加载并创建官方 StegoDispatcher。"""
    try:
      stegokit = load_stegokit()
    except BundledStegoKitError as exc:
      raise StegoToolError(str(exc)) from exc
    return stegokit.StegoDispatcher(verbose=verbose)

  def _resolve_bindings(
      self,
      *,
      algorithm: str,
      config: Any | None,
      material: Any | None,
      encode: bool,
  ) -> tuple[Any | None, Any | None]:
    """把普通字典转换成算法要求的 Config 和 Material 实例。"""
    registry = getattr(self._dispatcher, "registry", None)
    if registry is None:
      return config, material
    try:
      spec = registry.get_spec(algorithm)
      config_type = (
          spec.encode_config_type if encode else spec.decode_config_type
      )
      material_type = (
          spec.encode_material_type if encode else spec.decode_material_type
      )
      return (
          self._build_config(config_type, config),
          self._build_material(material_type, material),
      )
    except StegoToolError:
      raise
    except Exception as exc:
      phase = "编码" if encode else "解码"
      raise StegoToolError(
          f"无法为算法 {algorithm} 构建{phase}配置：{exc}"
      ) from exc

  @staticmethod
  def _build_config(expected_type: type[Any], value: Any | None) -> Any | None:
    """构造 StegoKit 算法配置，并保留 None 的官方默认语义。"""
    if value is None:
      return None
    if isinstance(value, expected_type):
      return copy.deepcopy(value)
    if not isinstance(value, Mapping):
      raise TypeError(f"config 必须是 {expected_type.__name__} 或映射")
    payload = dict(value)
    if expected_type.__name__ == "NoConfig" and payload:
      raise ValueError("当前算法的 NoConfig 不接受任何字段")
    if not dataclasses.is_dataclass(expected_type) and payload:
      raise TypeError(f"不支持配置类型：{expected_type.__name__}")
    return expected_type(**payload)

  @staticmethod
  def _build_material(
      expected_type: type[Any],
      value: Any | None,
  ) -> Any | None:
    """构造 StegoKit 安全材料，并支持官方 CLI 的 prg_seed 形式。"""
    if value is None:
      return None
    if isinstance(value, expected_type):
      return copy.deepcopy(value)
    if not isinstance(value, Mapping):
      raise TypeError(f"material 必须是 {expected_type.__name__} 或映射")
    payload = dict(value)
    type_name = expected_type.__name__
    if type_name == "NoMaterial":
      if payload:
        raise ValueError("当前算法的 NoMaterial 不接受任何字段")
      return expected_type()
    if type_name in {"RandomnessMaterial", "BitMaskMaterial"}:
      seed_value = payload.get("prg_seed", payload.get("seed"))
      if seed_value is None:
        raise ValueError("密码材料必须提供 prg_seed")
      try:
        stegokit = load_stegokit()
      except BundledStegoKitError as exc:
        raise StegoToolError(str(exc)) from exc
      return expected_type(prg=stegokit.PRG.from_int_seed(int(seed_value)))
    if not dataclasses.is_dataclass(expected_type) and payload:
      raise TypeError(f"不支持密码材料类型：{type_name}")
    return expected_type(**payload)
