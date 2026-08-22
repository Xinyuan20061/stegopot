"""隐写工具协议及 Dwinovo StegoKit 的可选适配器。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import copy
import dataclasses
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from stegopot.tools import BundledStegoKitError
from stegopot.tools import load_stegokit


class StegoToolError(RuntimeError):
  """隐写工具加载、参数转换或执行失败时抛出的异常。"""


@dataclasses.dataclass(frozen=True)
class StegoGenerationConfig:
  """与 StegoKit ``GenerationConfig`` 对齐的生成参数。

  属性：
    max_new_tokens: 编码生成时允许产生的最大 token 数。
    temperature: 模型采样温度，必须大于 0。
    top_k: 只从概率最高的前 k 个 token 中采样；为空表示不限制。
    top_p: nucleus sampling 的累计概率阈值；为空表示不限制。
    precision: 隐写算法内部数值精度，必须大于 0。
    stop_on_eos: 是否在生成到 EOS token 时停止；为空时由算法决定。
  """

  max_new_tokens: int = 128
  temperature: float = 1.0
  top_k: int | None = None
  top_p: float | None = None
  precision: int = 52
  stop_on_eos: bool | None = None

  def __post_init__(self) -> None:
    if self.max_new_tokens <= 0:
      raise ValueError("max_new_tokens 必须大于 0")
    if self.temperature <= 0:
      raise ValueError("temperature 必须大于 0")
    if self.top_k is not None and self.top_k <= 0:
      raise ValueError("top_k 必须大于 0")
    if self.top_p is not None and not 0 < self.top_p <= 1:
      raise ValueError("top_p 必须位于 (0, 1] 区间")
    if self.precision <= 0:
      raise ValueError("precision 必须大于 0")
    if self.stop_on_eos is not None and not isinstance(
        self.stop_on_eos, bool
    ):
      raise TypeError("stop_on_eos 必须是 bool 或 None")

  @classmethod
  def from_mapping(
      cls,
      value: Mapping[str, Any] | None,
  ) -> "StegoGenerationConfig":
    """从动作元数据中的字典创建生成配置。

    参数：
      value: 生成参数映射；为空时使用全部默认值。

    返回：
      经过类型和范围验证的生成配置。
    """
    return cls(**dict(value or {}))


@dataclasses.dataclass(frozen=True)
class StegoEmbedRequest:
  """与具体隐写工具无关的一次编码请求。

  属性：
    algorithm: 隐写算法名称，例如 ``ac`` 或 ``adg``。
    secret_bits: 只包含 0 和 1 的待嵌入秘密比特串。
    messages: 用于驱动本地生成模型的聊天消息列表。
    generation: 通用生成参数。
    config: 算法特有配置实例或字段映射。
    material: 密码材料实例或字段映射。
  """

  algorithm: str
  secret_bits: str
  messages: Sequence[Mapping[str, Any]]
  generation: StegoGenerationConfig = dataclasses.field(
      default_factory=StegoGenerationConfig
  )
  config: Any | None = None
  material: Any | None = None

  def __post_init__(self) -> None:
    algorithm = self.algorithm.strip() if isinstance(self.algorithm, str) else ""
    if not algorithm:
      raise ValueError("algorithm 必须是非空字符串")
    if not isinstance(self.secret_bits, str):
      raise TypeError("secret_bits 必须是字符串")
    if set(self.secret_bits) - {"0", "1"}:
      raise ValueError("secret_bits 只能包含 0 和 1")
    messages = _normalize_messages(self.messages)
    object.__setattr__(self, "algorithm", algorithm.lower())
    object.__setattr__(self, "messages", messages)


@dataclasses.dataclass(frozen=True)
class StegoExtractRequest:
  """与具体隐写工具无关的一次解码请求。

  属性：
    algorithm: 编码时使用的隐写算法名称。
    generated_token_ids: StegoKit 编码产生的 token ID 序列。
    messages: 编码时使用的相同聊天消息列表。
    generation: 必须与编码端保持一致的通用生成参数。
    max_bits: 最多提取的比特数；通常使用编码结果 consumed_bits。
    config: 算法特有解码配置实例或字段映射。
    material: 与编码端匹配的密码材料实例或字段映射。
  """

  algorithm: str
  generated_token_ids: Sequence[int]
  messages: Sequence[Mapping[str, Any]]
  generation: StegoGenerationConfig = dataclasses.field(
      default_factory=StegoGenerationConfig
  )
  max_bits: int | None = None
  config: Any | None = None
  material: Any | None = None

  def __post_init__(self) -> None:
    algorithm = self.algorithm.strip() if isinstance(self.algorithm, str) else ""
    if not algorithm:
      raise ValueError("algorithm 必须是非空字符串")
    token_ids = tuple(int(token_id) for token_id in self.generated_token_ids)
    if not token_ids:
      raise ValueError("generated_token_ids 不能为空")
    if self.max_bits is not None and self.max_bits < 0:
      raise ValueError("max_bits 不能小于 0")
    object.__setattr__(self, "algorithm", algorithm.lower())
    object.__setattr__(self, "generated_token_ids", token_ids)
    object.__setattr__(self, "messages", _normalize_messages(self.messages))


@dataclasses.dataclass(frozen=True)
class StegoEmbedResult:
  """统一的隐写编码结果。

  属性：
    text: 携带秘密比特的生成文本。
    generated_token_ids: 生成文本对应的 token ID 序列。
    consumed_bits: 实际嵌入的秘密比特数量。
    encode_time_seconds: 编码耗时，单位为秒。
    embedding_capacity: 工具报告的嵌入容量。
    metadata: 工具提供的其他编码元数据。
  """

  text: str
  generated_token_ids: Sequence[int]
  consumed_bits: int
  encode_time_seconds: float = 0.0
  embedding_capacity: float = 0.0
  metadata: Mapping[str, Any] = dataclasses.field(default_factory=dict)

  def __post_init__(self) -> None:
    if not isinstance(self.text, str) or not self.text.strip():
      raise ValueError("隐写编码结果 text 不能为空")
    if self.consumed_bits < 0:
      raise ValueError("consumed_bits 不能小于 0")
    object.__setattr__(
        self,
        "generated_token_ids",
        tuple(int(token_id) for token_id in self.generated_token_ids),
    )
    object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclasses.dataclass(frozen=True)
class StegoExtractResult:
  """统一的隐写解码结果。

  属性：
    bits: 从生成 token 中提取出的秘密比特串。
    decode_time_seconds: 解码耗时，单位为秒。
    metadata: 工具提供的其他解码元数据。
  """

  bits: str
  decode_time_seconds: float = 0.0
  metadata: Mapping[str, Any] = dataclasses.field(default_factory=dict)

  def __post_init__(self) -> None:
    if not isinstance(self.bits, str) or set(self.bits) - {"0", "1"}:
      raise ValueError("解码结果 bits 只能包含 0 和 1")
    object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@runtime_checkable
class StegoTool(Protocol):
  """Substrate 依赖的最小隐写工具协议。"""

  def embed(self, request: StegoEmbedRequest) -> StegoEmbedResult:
    """将秘密比特嵌入生成文本。"""
    ...

  def extract(self, request: StegoExtractRequest) -> StegoExtractResult:
    """从生成 token ID 中提取秘密比特。"""
    ...

  def close(self) -> None:
    """释放隐写工具持有的本地模型资源。"""
    ...


class StegoKitAdapter:
  """把本项目隐写协议映射到 ``Dwinovo/stego-kit`` API。

  ``stegokit`` 只在未显式传入 dispatcher 时从项目内的工具子模块
  动态加载，因此普通通信场景和离线测试不需要导入 PyTorch 或
  Transformers。
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
      tokenizer: 与 model 完全匹配、且配置 chat_template 的 tokenizer。
      dispatcher: 可选 StegoDispatcher；为空时动态创建官方 dispatcher。
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
    """调用 ``StegoDispatcher.embed`` 执行隐写编码。

    参数：
      request: 本项目统一的编码请求。

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
    """调用 ``StegoDispatcher.extract`` 执行隐写解码。

    参数：
      request: 本项目统一的解码请求。

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
    """从项目工具目录加载并创建官方 StegoDispatcher。

    参数：
      verbose: 是否启用 StegoKit dispatcher 的详细日志。

    返回：
      官方 ``StegoDispatcher`` 实例。
    """
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


def _normalize_messages(
    messages: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
  """验证并冻结 StegoKit 要求的聊天消息列表。"""
  normalized = []
  for index, message in enumerate(messages):
    if not isinstance(message, Mapping):
      raise TypeError(f"messages[{index}] 必须是映射")
    item = dict(message)
    if "role" not in item:
      raise ValueError(f"messages[{index}] 缺少 role")
    if "content" not in item and "tool_calls" not in item:
      raise ValueError(f"messages[{index}] 缺少 content 或 tool_calls")
    normalized.append(MappingProxyType(item))
  if not normalized:
    raise ValueError("messages 不能为空")
  return tuple(normalized)
