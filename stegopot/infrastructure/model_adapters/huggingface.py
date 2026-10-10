"""Hugging Face Causal LM 的选择性观测、干预与逐 token 适配器。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from contextlib import nullcontext
import math
import time
from typing import Any

from stegopot.domain.interface.events import EventSink
from stegopot.domain.interface.storage import TraceStore
from stegopot.domain.model.capability import Capability
from stegopot.domain.model.events import EventKind, RuntimeEvent
from stegopot.domain.model.intervention_runtime import (
    Intervention,
    InterventionContext,
)
from stegopot.domain.model.reference import (
    ResolvedTensorRef,
    TensorRef,
    TracePolicy,
)
from stegopot.domain.model.runtime import (
    ForwardResult,
    GenerationConfig,
    GenerationResult,
    ModelInput,
)
from stegopot.domain.model.trace import ActivationRecord, ActivationTrace


class HuggingFaceAdapter:
  """把 AutoModelForCausalLM 映射为 StegoPot 的可控模型接口。"""

  _LAYER_ROOTS = (
      "model.layers", "transformer.h", "gpt_neox.layers",
      "model.decoder.layers", "transformer.blocks",
  )
  _COMPONENTS = {
      "attention_output": ("self_attn", "attn", "attention"),
      "attn.output": ("self_attn", "attn", "attention"),
      "mlp_output": ("mlp", "feed_forward", "ffn"),
      "mlp.output": ("mlp", "feed_forward", "ffn"),
  }

  def __init__(
      self, model_path: str | None = None, *, tokenizer_path: str | None = None,
      revision: str | None = None, device: str = "auto", dtype: str = "auto",
      trust_remote_code: bool = False, local_files_only: bool = True,
      use_safetensors: bool = True, parameter_gradients: bool = True,
      model: Any | None = None,
      tokenizer: Any | None = None, trace_store: TraceStore | None = None,
  ) -> None:
    """加载或接收模型。

    参数：
      model_path: 本地目录或 Hugging Face 模型 ID；注入 model 时可为空。
      tokenizer_path: 可选 tokenizer 目录或 ID，默认与 model_path 相同。
      revision: 固定的模型修订版本。
      device: auto、cpu、cuda、mps 或 PyTorch 接受的设备名。
      dtype: auto、float32、float16 或 bfloat16。
      trust_remote_code: 是否允许执行模型仓库代码，默认关闭。
      local_files_only: 是否禁止运行时下载，默认开启。
      use_safetensors: 是否优先使用 safetensors 权重。
      parameter_gradients: 反向传播时是否同时计算参数梯度。关闭后仍可读取
        激活梯度，但会显著降低白盒审计的显存占用。
      model: 测试或嵌入场景注入的 PyTorch 模型。
      tokenizer: 与 model 配套的 tokenizer。
      trace_store: TracePolicy.store=disk 时使用的外部张量存储。
    """
    self._torch = _import_torch()
    if (model is None) != (tokenizer is None):
      raise ValueError("model 和 tokenizer 必须同时注入")
    if model is None:
      if not model_path:
        raise ValueError("未注入模型时必须提供 model_path")
      model, tokenizer = self._load(
          model_path, tokenizer_path, revision, device, dtype,
          trust_remote_code, local_files_only, use_safetensors)
    self._model = model
    self._tokenizer = tokenizer
    self._trace_store = trace_store
    self._model.eval()
    self._input_gradient_handle = None
    if not parameter_gradients:
      self._disable_parameter_gradients()
    self._modules = dict(self._model.named_modules())
    self._layer_root = self._find_layer_root()
    self._model_id = str(
        model_path or getattr(getattr(model, "config", None), "_name_or_path", None)
        or type(model).__name__)
    self._closed = False

  @property
  def adapter_id(self) -> str:
    """返回适配器 ID。"""
    return "huggingface"

  @property
  def model_id(self) -> str:
    """返回模型标识。"""
    return self._model_id

  @property
  def capabilities(self) -> frozenset[Capability]:
    """返回当前适配器真实实现的能力。"""
    return frozenset({
        Capability.FORWARD, Capability.GENERATION,
        Capability.TOKEN_STEP_CONTROL, Capability.ACTIVATION_READ,
        Capability.ACTIVATION_WRITE, Capability.GRADIENT_READ,
    })

  def resolve(self, ref: TensorRef) -> ResolvedTensorRef:
    """把精确模块或常见 Transformer 逻辑位置解析成 Hook 地址。"""
    self._ensure_open()
    if ref.head is not None:
      raise ValueError("通用 Hugging Face 适配器不猜测 attention head 布局")
    if ref.module is not None:
      if ref.module not in self._modules:
        raise KeyError(f"模型不存在模块：{ref.module}")
      return ResolvedTensorRef(ref, ref.module, ref.io, ref.tensor_index)
    if self._layer_root is None:
      raise ValueError("模型没有可识别的 Transformer 层容器，请使用 module 精确路径")
    base = f"{self._layer_root}.{ref.layer}"
    if base not in self._modules:
      raise KeyError(f"模型不存在逻辑层：{ref.layer}")
    component = ref.component or "resid_post"
    if component == "resid_pre":
      return ResolvedTensorRef(ref, base, "input", ref.tensor_index)
    if component in {"resid_post", "output"}:
      return ResolvedTensorRef(ref, base, "output", ref.tensor_index)
    suffixes = self._COMPONENTS.get(component)
    if suffixes is None:
      raise ValueError(f"不支持的逻辑组件：{component}；请改用 module 精确路径")
    for suffix in suffixes:
      name = f"{base}.{suffix}"
      if name in self._modules:
        return ResolvedTensorRef(ref, name, "output", ref.tensor_index)
    raise KeyError(f"第 {ref.layer} 层不存在组件 {component}")

  def forward(
      self, inputs: ModelInput, *, policy: TracePolicy,
      interventions: Sequence[Intervention], run_id: str,
      step_index: int | None = None, event_sink: EventSink | None = None,
  ) -> ForwardResult:
    """执行一次带有作用域 Hook 的真实模型前向。"""
    self._ensure_open()
    encoded = self._encode(inputs)
    token_ids = _token_ids(encoded["input_ids"])
    refs = self._policy_refs(policy)
    requested = {item.key: item for item in refs}
    all_refs = {item.key: item for item in refs}
    for intervention in interventions:
      for ref in intervention.required_refs:
        all_refs.setdefault(ref.key, ref)
    resolved = {key: self.resolve(ref) for key, ref in all_refs.items()}
    grouped = defaultdict(list)
    for key, location in resolved.items():
      grouped[
          (location.module, location.io, location.tensor_index)
      ].append((key, location.requested))
    calls = defaultdict(int)
    observed: dict[str, Any] = {}
    records: list[ActivationRecord] = []
    handles = []
    byte_count = 0
    started = time.perf_counter()
    self._emit(event_sink, EventKind.FORWARD_START, run_id, {
        "step_index": step_index, "trace_profile": policy.profile})

    def process(
        module_name: str, io: str, tensor_index: int, container: Any,
    ) -> Any:
      """处理同一模块和输入输出方向的全部引用。"""
      nonlocal byte_count
      group_key = (module_name, io, tensor_index)
      call_index = calls[group_key]
      calls[group_key] += 1
      entries = [(key, ref) for key, ref in grouped[group_key]
                 if ref.call_index == call_index]
      if not entries:
        return container
      self._emit(event_sink, EventKind.LAYER_ENTER, run_id, {
          "module": module_name, "io": io, "call_index": call_index})
      tensor = _container_tensor(container, tensor_index)
      if not self._torch.is_tensor(tensor):
        raise TypeError(f"Hook 目标不是张量：{module_name}")
      for key, ref in entries:
        observed[key] = _select(tensor, ref)
      for intervention in interventions:
        target = intervention.target
        if target.key not in {key for key, _ in entries}:
          continue
        selected = _select(tensor, target)
        condition_value = (
            observed[target.key] if intervention.observe is None
            else observed.get(intervention.observe.key))
        if condition_value is None:
          raise RuntimeError(
              f"条件干预 {intervention.intervention_id} 的观察位置尚未执行")
        context = InterventionContext(
            run_id, target, step_index,
            {"module": module_name, "call_index": call_index})
        if intervention.condition is not None and not intervention.condition(
            condition_value, context):
          continue
        replacement = intervention.operator(selected, context)
        _validate_replacement(selected, replacement, self._torch)
        tensor = _replace_selection(tensor, target, replacement)
        observed[target.key] = _select(tensor, target)
        self._emit(event_sink, EventKind.INTERVENTION_APPLIED, run_id, {
            "intervention_id": intervention.intervention_id,
            "target": target.key, "step_index": step_index})
      container = _replace_container(container, tensor_index, tensor)
      for key, ref in entries:
        if key not in requested:
          continue
        if len(records) >= policy.max_records:
          raise RuntimeError("激活记录数量超过 TracePolicy.max_records")
        selected = _select(tensor, ref)
        estimated = int(selected.numel() * selected.element_size())
        if (policy.max_bytes is not None
            and byte_count + estimated > policy.max_bytes):
          raise RuntimeError("激活记录大小超过 TracePolicy.max_bytes")
        record, used = self._record(
            ref, selected, tensor, policy, run_id, step_index, len(records))
        byte_count += used
        records.append(record)
        self._emit(event_sink, EventKind.ACTIVATION_READY, run_id, {
            "ref": ref.key, "shape": list(record.shape),
            "dtype": record.dtype, "step_index": step_index})
      self._emit(event_sink, EventKind.LAYER_EXIT, run_id, {
          "module": module_name, "io": io, "call_index": call_index})
      return container

    for module_name, io, tensor_index in grouped:
      module = self._modules[module_name]
      if io == "input":
        handles.append(module.register_forward_pre_hook(
            lambda _module, args, name=module_name, index=tensor_index:
            process(name, "input", index, args)))
      else:
        handles.append(module.register_forward_hook(
            lambda _module, _args, output, name=module_name, index=tensor_index:
            process(name, "output", index, output)))
    gradient_mode = policy.retain_gradients or policy.retain_graph
    context = nullcontext() if gradient_mode else self._torch.no_grad()
    try:
      if policy.retain_gradients:
        self._model.zero_grad(set_to_none=True)
      with context:
        output = self._model(**encoded)
    finally:
      for handle in handles:
        handle.remove()
    missing = sorted(key for key in requested
                     if key not in {record.ref.key for record in records})
    if missing:
      raise RuntimeError(f"以下 TensorRef 未命中 Hook：{missing}")
    trace = ActivationTrace(
        run_id, self.model_id, token_ids, records,
        {"adapter": self.adapter_id, "step_index": step_index,
         "duration_seconds": time.perf_counter() - started})
    self._emit(event_sink, EventKind.FORWARD_END, run_id, {
        "record_count": len(records), "step_index": step_index})
    return ForwardResult(output, trace, {
        "adapter": self.adapter_id,
        "duration_seconds": time.perf_counter() - started})

  def open_generation_session(
      self, inputs: ModelInput, *, config: GenerationConfig,
      policy: TracePolicy, interventions: Sequence[Intervention], run_id: str,
      event_sink: EventSink | None = None,
  ) -> "_GenerationSession":
    """创建不使用隐藏 generate 循环的逐 token 会话。"""
    self._ensure_open()
    encoded = self._encode(inputs)
    return _GenerationSession(
        self, _token_ids(encoded["input_ids"]), config, policy,
        tuple(interventions), run_id, event_sink)

  def clear_gradients(self) -> None:
    """用 set_to_none 释放参数梯度，不修改权重。"""
    self._ensure_open()
    self._model.zero_grad(set_to_none=True)

  def close(self) -> None:
    """释放适配器持有的模型引用。"""
    if self._input_gradient_handle is not None:
      self._input_gradient_handle.remove()
      self._input_gradient_handle = None
    self._closed = True

  def _disable_parameter_gradients(self) -> None:
    """冻结参数，并从输入嵌入建立仅供激活审计使用的计算图。"""
    get_embeddings = getattr(self._model, "get_input_embeddings", None)
    if not callable(get_embeddings):
      raise TypeError("parameter_gradients=False 要求模型实现 get_input_embeddings()")
    embeddings = get_embeddings()
    if embeddings is None:
      raise TypeError("模型没有可用于激活梯度的输入嵌入模块")
    self._model.requires_grad_(False)

    def require_output_gradient(_module: Any, _inputs: Any, output: Any) -> Any:
      """把嵌入输出设为计算图叶节点，使后续激活可获得梯度。"""
      if not self._torch.is_tensor(output):
        raise TypeError("输入嵌入模块输出必须是 PyTorch Tensor")
      output.requires_grad_(True)
      return output

    self._input_gradient_handle = embeddings.register_forward_hook(
        require_output_gradient)

  def _policy_refs(self, policy: TracePolicy) -> tuple[TensorRef, ...]:
    """将显式或 full 采集策略展开为有限引用。"""
    if policy.profile != "full":
      return tuple(policy.refs)
    leaves = [
        name for name, module in self._modules.items()
        if name and not any(True for _ in module.children())
    ]
    if len(leaves) > policy.max_records:
      raise RuntimeError("full 采集模块数超过 TracePolicy.max_records")
    return tuple(TensorRef(module=name) for name in leaves)

  def _record(
      self, ref: TensorRef, selected: Any, full_tensor: Any,
      policy: TracePolicy, run_id: str, step_index: int | None, index: int,
  ) -> tuple[ActivationRecord, int]:
    """按照 TracePolicy 保存一个选择，并在需要时注册梯度 Hook。"""
    value = selected
    if policy.detach:
      value = selected.detach()
      value = _cast(value, policy.precision, self._torch)
      if policy.store in {"cpu", "disk"}:
        value = value.cpu()
    if policy.store == "disk":
      if self._trace_store is None:
        raise RuntimeError("store=disk 需要构造适配器时提供 TraceStore")
      value = self._trace_store.write_tensor(
          f"traces/{run_id}/{step_index if step_index is not None else 'forward'}-{index}.pt",
          value)
    shape = tuple(int(item) for item in selected.shape)
    record = ActivationRecord(
        ref, value, shape, str(selected.dtype), str(selected.device),
        step_index, {"adapter": self.adapter_id})
    if policy.retain_gradients:
      full_tensor.register_hook(
          lambda gradient, item=record, target=ref:
          item.set_gradient(_select(gradient, target).detach().cpu()))
    used = int(selected.numel() * selected.element_size())
    return record, used

  def _encode(self, value: ModelInput) -> dict[str, Any]:
    """把标准输入转换成模型关键字参数并移动到模型设备。"""
    if value.format == "backend":
      if not isinstance(value.payload, Mapping):
        raise TypeError("backend 输入必须是映射")
      encoded = dict(value.payload)
    elif value.format == "token_ids":
      ids = value.payload
      if self._torch.is_tensor(ids):
        tensor = ids
      else:
        tensor = self._torch.tensor(ids, dtype=self._torch.long)
      encoded = {"input_ids": tensor.unsqueeze(0) if tensor.ndim == 1 else tensor}
    elif value.format == "messages":
      method = getattr(self._tokenizer, "apply_chat_template", None)
      if not callable(method):
        raise ValueError("当前 tokenizer 不支持 messages 输入")
      rendered = method(
          value.payload, tokenize=True, add_generation_prompt=True,
          return_tensors="pt")
      encoded = (
          dict(rendered) if isinstance(rendered, Mapping)
          else {"input_ids": rendered})
    else:
      encoded = dict(self._tokenizer(value.payload, return_tensors="pt"))
    if "input_ids" not in encoded:
      raise ValueError("模型输入缺少 input_ids")
    device = _model_device(self._model, self._torch)
    return {key: item.to(device) if self._torch.is_tensor(item) else item
            for key, item in encoded.items()}

  def _find_layer_root(self) -> str | None:
    """识别常见 Transformers 层容器，不猜测未知模型结构。"""
    for root in self._LAYER_ROOTS:
      if any(name.startswith(root + ".0") for name in self._modules):
        return root
    return None

  def _load(
      self, model_path, tokenizer_path, revision, device, dtype,
      trust_remote_code, local_files_only, use_safetensors,
  ):
    """惰性导入 Transformers 并加载本地或显式允许的模型。"""
    try:
      from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:
      raise RuntimeError("使用 HuggingFaceAdapter 需要安装 stegopot[whitebox]") from exc
    dtype_value = {
        "auto": "auto", "float32": self._torch.float32,
        "float16": self._torch.float16, "bfloat16": self._torch.bfloat16,
    }.get(dtype)
    if dtype_value is None:
      raise ValueError("dtype 只支持 auto、float32、float16、bfloat16")
    common = {
        "revision": revision, "trust_remote_code": trust_remote_code,
        "local_files_only": local_files_only,
    }
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_path or model_path, **common)
    model = AutoModelForCausalLM.from_pretrained(
        model_path, torch_dtype=dtype_value, use_safetensors=use_safetensors,
        **common)
    if device != "auto":
      model.to(device)
    return model, tokenizer

  def _emit(self, sink, kind, run_id, data) -> None:
    """发送不含张量的结构化事件。"""
    if sink is not None:
      sink.emit(RuntimeEvent(kind, run_id, data=data))

  def _ensure_open(self) -> None:
    if self._closed:
      raise RuntimeError("HuggingFaceAdapter 已关闭")


class _GenerationStep:
  """一个尚未提交 token 的可重算步骤。"""

  def __init__(self, session: "_GenerationSession", result: ForwardResult) -> None:
    self._session = session
    self._result = result

  @property
  def index(self) -> int:
    return len(self._session.generated)

  @property
  def result(self) -> ForwardResult:
    return self._result

  def inspect(self, ref: TensorRef) -> ActivationRecord:
    return self._result.trace.get(ref, step_index=self.index)

  def apply(self, interventions: Sequence[Intervention]) -> "_GenerationStep":
    return self._session._recompute(tuple(interventions))

  def sample(self) -> int:
    return self._session._sample(_next_logits(self._result.output))


class _GenerationSession:
  """由完整前缀重算实现的轻量逐 token 控制会话。"""

  def __init__(
      self, adapter, prompt_ids, config, policy, interventions, run_id, event_sink,
  ) -> None:
    self.adapter = adapter
    self.prompt_ids = tuple(prompt_ids)
    self.generated: list[int] = []
    self.config = config
    self.policy = policy
    self.interventions = interventions
    self.run_id = run_id
    self.event_sink = event_sink
    self._pending: _GenerationStep | None = None
    self._reason: str | None = None
    self._committed_traces: list[ActivationTrace] = []
    self._generator = adapter._torch.Generator(device="cpu")
    self._generator.manual_seed(config.seed)

  @property
  def finished(self) -> bool:
    return self._reason is not None

  def forward_next(
      self, interventions: Sequence[Intervention] = (),
  ) -> _GenerationStep:
    if self.finished:
      raise RuntimeError("生成会话已经结束")
    if self._pending is not None:
      raise RuntimeError("必须先提交当前 token")
    return self._compute(tuple(interventions))

  def commit(self, token_id: int) -> None:
    if self._pending is None:
      raise RuntimeError("提交前必须执行 forward_next")
    token = int(token_id)
    if token < 0:
      raise ValueError("token_id 不能为负数")
    self.generated.append(token)
    self._committed_traces.append(self._pending.result.trace)
    self._pending = None
    if token in self.config.stop_token_ids:
      self._reason = "stop_token"
    elif len(self.generated) >= self.config.max_new_tokens:
      self._reason = "max_new_tokens"

  def result(self) -> GenerationResult:
    if not self.finished:
      raise RuntimeError("生成会话尚未结束")
    return GenerationResult(
        self.generated, self.adapter._tokenizer.decode(self.generated),
        tuple(self._committed_traces), {"stop_reason": self._reason})

  def close(self) -> None:
    if self._reason is None:
      self._reason = "closed"
    self._pending = None

  def _compute(self, extra: tuple[Intervention, ...]) -> _GenerationStep:
    step_index = len(self.generated)
    result = self.adapter.forward(
        ModelInput((*self.prompt_ids, *self.generated), "token_ids"),
        policy=self.policy, interventions=(*self.interventions, *extra),
        run_id=self.run_id, step_index=step_index, event_sink=self.event_sink)
    step = _GenerationStep(self, result)
    self._pending = step
    self.adapter._emit(
        self.event_sink, EventKind.GENERATION_STEP, self.run_id,
        {"step_index": step_index, "input_token_count": len(self.prompt_ids)
         + len(self.generated)})
    return step

  def _recompute(self, extra: tuple[Intervention, ...]) -> _GenerationStep:
    if self._pending is None:
      raise RuntimeError("当前没有可重算的生成步骤")
    self._pending = None
    return self._compute(extra)

  def _sample(self, logits: Any) -> int:
    torch = self.adapter._torch
    values = logits.detach().float().cpu()
    if self.config.temperature == 0:
      return int(values.argmax().item())
    values = values / self.config.temperature
    if self.config.top_k is not None:
      cutoff = torch.topk(values, min(self.config.top_k, values.numel())).values[-1]
      values = values.masked_fill(values < cutoff, -math.inf)
    if self.config.top_p is not None:
      ordered, indices = torch.sort(values, descending=True)
      cumulative = torch.softmax(ordered, dim=-1).cumsum(dim=-1)
      remove = cumulative - torch.softmax(ordered, dim=-1) > self.config.top_p
      ordered = ordered.masked_fill(remove, -math.inf)
      filtered = torch.full_like(values, -math.inf)
      filtered.scatter_(0, indices, ordered)
      values = filtered
    return int(torch.multinomial(
        torch.softmax(values, dim=-1), 1, generator=self._generator).item())


def _import_torch():
  try:
    import torch
  except ImportError as exc:
    raise RuntimeError("使用 HuggingFaceAdapter 需要安装 torch") from exc
  return torch


def _model_device(model: Any, torch: Any) -> Any:
  try:
    return next(model.parameters()).device
  except StopIteration:
    return torch.device("cpu")


def _token_ids(value: Any) -> tuple[int, ...]:
  values = value.detach().cpu().tolist()
  if values and isinstance(values[0], list):
    if len(values) != 1:
      raise ValueError("当前适配器一次 forward 只支持一个样本")
    values = values[0]
  return tuple(int(item) for item in values)


def _container_tensor(container: Any, index: int) -> Any:
  if isinstance(container, (tuple, list)):
    if index >= len(container):
      raise IndexError("tensor_index 超出模块输入输出范围")
    return container[index]
  if index != 0:
    raise IndexError("单张量输入输出只支持 tensor_index=0")
  return container


def _replace_container(container: Any, index: int, value: Any) -> Any:
  if isinstance(container, tuple):
    values = list(container)
    values[index] = value
    return tuple(values)
  if isinstance(container, list):
    values = list(container)
    values[index] = value
    return values
  return value


def _select(tensor: Any, ref: TensorRef) -> Any:
  if ref.token is None:
    return tensor
  if tensor.ndim < 2:
    raise ValueError(f"TensorRef {ref.key} 不能在低于二维的张量上选择 token")
  axis = -2
  if isinstance(ref.token, tuple):
    slices = [slice(None)] * tensor.ndim
    slices[axis] = slice(*ref.token)
    return tensor[tuple(slices)]
  slices = [slice(None)] * tensor.ndim
  slices[axis] = ref.token
  return tensor[tuple(slices)]


def _replace_selection(tensor: Any, ref: TensorRef, replacement: Any) -> Any:
  if ref.token is None:
    return replacement
  result = tensor.clone()
  axis = -2
  slices = [slice(None)] * result.ndim
  slices[axis] = slice(*ref.token) if isinstance(ref.token, tuple) else ref.token
  result[tuple(slices)] = replacement
  return result


def _validate_replacement(current: Any, replacement: Any, torch: Any) -> None:
  if not torch.is_tensor(replacement):
    raise TypeError("干预算子必须返回 PyTorch Tensor")
  if (replacement.shape != current.shape or replacement.dtype != current.dtype
      or replacement.device != current.device):
    raise ValueError("干预结果必须与目标选择具有相同 shape、dtype 和 device")


def _cast(value: Any, precision: str, torch: Any) -> Any:
  dtype = {
      "preserve": None, "float32": torch.float32,
      "float16": torch.float16, "bfloat16": torch.bfloat16,
  }[precision]
  return value if dtype is None or not value.is_floating_point() else value.to(dtype=dtype)


def _next_logits(output: Any) -> Any:
  logits = getattr(output, "logits", None)
  if logits is None and isinstance(output, Mapping):
    logits = output.get("logits")
  if logits is None:
    raise TypeError("模型输出没有 logits")
  return logits[0, -1]
