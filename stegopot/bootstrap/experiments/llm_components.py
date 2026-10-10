"""Chat Completions 兼容的黑盒模型组件。"""

from stegopot.domain.interface.plugin import BuildContext, ComponentDefinition
from stegopot.domain.interface.registration import Plugin
from stegopot.infrastructure.llm.clients.chat_completions import ChatCompletionsClient


def definitions() -> tuple[ComponentDefinition, ...]:
  """返回 API 模型组件；只有构造实例时才注入单个授权凭证。"""
  registry = Plugin("core", "2.0.0")
  schema = {
      "type": "object", "additionalProperties": False,
      "required": ["base_url", "model"],
      "properties": {
          "base_url": {
              "type": "string", "minLength": 1,
              "description": "Chat Completions API 根地址；远程地址必须使用 HTTPS。"},
          "model": {
              "type": "string", "minLength": 1,
              "description": "服务端支持的默认模型名。"},
          "api_key_env": {
              "type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$",
              "description": "密钥环境变量名，不得填写真实密钥。"},
          "timeout": {
              "type": "number", "exclusiveMinimum": 0, "default": 60,
              "description": "单次连接和读取超时秒数。"},
          "response_format": {
              "enum": ["json_object", "text"], "default": "json_object",
              "description": "服务端响应模式。"},
          "thinking": {
              "enum": ["enabled", "disabled"],
              "description": "服务支持时发送的推理模式开关。"},
          "reasoning_effort": {
              "type": "string", "minLength": 1,
              "description": "服务支持时发送的推理强度。"},
      },
  }

  @registry.component(
      "llm", "chat_completions", schema=schema,
      credentials=("api_key_env",))
  def client(config: dict, context: BuildContext) -> ChatCompletionsClient:
    """根据连接参数和被授权的环境变量构造 API 客户端。"""
    return ChatCompletionsClient(
        api_key=context.credential("api_key_env")
        if "api_key_env" in config else None,
        **{name: value for name, value in config.items()
           if name != "api_key_env"},
    )

  return registry().components
