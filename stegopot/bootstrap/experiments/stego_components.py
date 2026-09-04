"""核心隐写与基础检测组件的配置注册；重型依赖在构造时才加载。"""

from stegopot.domain.interface.registration import Plugin
from stegopot.infrastructure.integrations.stegokit.codec import StegoKitCodec
from stegopot.infrastructure.integrations.stegokit.adapter import StegoKitAdapter
from stegopot.infrastructure.llm.codec_policy import CodecPolicy
from stegopot.infrastructure.detectors.keyword import KeywordStegoDetector
from stegopot.infrastructure.detectors.llm import LLMStegoDetector


def _object(properties, required=()):
  """根据 properties/required 组成严格配置模式。"""
  return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


def definitions():
  """返回核心隐写组件列表，使用与外部开发者相同的装饰器接口。"""
  registry = Plugin("core", "0.6.0")
  text = {"type": "string", "minLength": 1}

  @registry.component("codec", "stegokit", schema=_object({
      "model_path": text, "algorithm": text,
      "generation": _object({
          "max_new_tokens": {"type": "integer", "minimum": 1},
          "temperature": {"type": "number", "exclusiveMinimum": 0},
          "top_k": {"type": ["integer", "null"], "minimum": 1},
          "top_p": {"type": ["number", "null"], "exclusiveMinimum": 0, "maximum": 1},
          "precision": {"type": "integer", "minimum": 1},
          "stop_on_eos": {"type": ["boolean", "null"]}}),
      "encode_config": {"type": "object"}, "decode_config": {"type": "object"}}, ["model_path"]))
  def codec(config, context):
    """从 config.model_path 加载本地模型；context 不提供网络下载或远程代码权限。"""
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(config["model_path"], local_files_only=True, trust_remote_code=False)
    model = AutoModelForCausalLM.from_pretrained(config["model_path"], local_files_only=True, trust_remote_code=False)
    model.eval()
    return StegoKitCodec(adapter=StegoKitAdapter(model=model, tokenizer=tokenizer), tokenizer=tokenizer,
                         **{key: value for key, value in config.items() if key != "model_path"})

  @registry.component("policy", "codec_sender", references={"codec": "codec"},
                      schema=_object({"codec": text, "target": text,
                                      "active_round": {"type": "integer", "minimum": 0}}, ["codec", "target"]))
  def sender(config, context):
    """将 config 接收者与 context 的已审计 codec 组装成发送策略。"""
    return CodecPolicy(codec=context.resource("codec"), mode="encode", target=config["target"],
                       active_round=config.get("active_round", 0))

  @registry.component("policy", "codec_receiver", references={"codec": "codec"},
                      schema=_object({"codec": text, "active_round": {"type": "integer", "minimum": 0}}, ["codec"]))
  def receiver(config, context):
    """将 config 轮次与 context 的已审计 codec 组装成接收策略。"""
    return CodecPolicy(codec=context.resource("codec"), mode="decode", active_round=config.get("active_round", 1))

  @registry.component("detector", "keyword", schema=_object({
      "keywords": {"type": "array", "minItems": 1, "items": text},
      "case_sensitive": {"type": "boolean"}}, ["keywords"]))
  def keyword(config, context):
    """用 config 构建公开文本基线；context 不参与真实标签读取。"""
    return KeywordStegoDetector(**config)

  @registry.component("detector", "llm_detector", references={"client": "llm"}, schema=_object({
      "client": text, "model": text, "threshold": {"type": "number", "minimum": 0, "maximum": 1},
      "max_tokens": {"type": "integer", "minimum": 1}}, ["client"]))
  def detector(config, context):
    """将 config 与 context 的模型资源注入检测器。"""
    return LLMStegoDetector(client=context.resource("client"),
                           **{key: value for key, value in config.items() if key != "client"})
  return registry().components
