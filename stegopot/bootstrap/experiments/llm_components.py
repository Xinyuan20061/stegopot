"""内置通用模型组件注册；供应商地址和型号由用户配置，不绑定实验场景。"""

from stegopot.domain.interface.plugin import BuildContext, ComponentDefinition
from stegopot.domain.interface.registration import Plugin
from stegopot.infrastructure.llm.clients.chat_completions import ChatCompletionsClient


def definitions() -> tuple[ComponentDefinition, ...]:
  """返回通用模型组件声明；只有实际构造资源时才注入授权凭证。"""
  registry = Plugin("core", "0.7.0")
  schema = {
      "type": "object", "additionalProperties": False, "required": ["base_url", "model"],
      "properties": {
          "base_url": {"type": "string", "minLength": 1, "description": "API 根地址，可含 /v1；远程必须 HTTPS，本地可使用 HTTP"},
          "model": {"type": "string", "minLength": 1, "description": "服务提供方支持的默认模型名"},
          "api_key_env": {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$", "description": "密钥环境变量名，不得填写真实密钥；无鉴权本地服务可省略"},
          "timeout": {"type": "number", "exclusiveMinimum": 0, "default": 60, "description": "单次连接与读操作超时秒数，不是实验硬截止"},
          "response_format": {"enum": ["json_object", "text"], "default": "json_object", "description": "JSON 模式或不指定响应格式；服务端必须支持所选模式"},
          "thinking": {"enum": ["enabled", "disabled"], "description": "可选的推理模式开关；仅在服务支持时发送"},
          "reasoning_effort": {"type": "string", "minLength": 1, "description": "可选推理强度，具体取值由所用服务定义"},
      },
  }

  @registry.component("llm", "chat_completions", schema=schema, credentials=("api_key_env",))
  def client(config: dict, context: BuildContext) -> ChatCompletionsClient:
    """根据 config 的连接参数和 context 授权密钥构造客户端；不读取全局环境。"""
    return ChatCompletionsClient(
        api_key=context.credential("api_key_env") if "api_key_env" in config else None,
        **{name: value for name, value in config.items() if name != "api_key_env"},
    )
  return registry().components
