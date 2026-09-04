"""DeepSeek 供应商插件；凭证由宿主按声明注入。"""

from stegopot.domain.interface.plugin import ComponentDefinition, PluginDefinition
from stegopot_deepseek.infrastructure.client import DeepSeekClient


def _client(config, context):
  """用 config 模型参数和 context 授权凭证创建客户端，不执行请求。"""
  return DeepSeekClient(api_key=context.credential("api_key_env"),
                        default_model=config.get("model", "deepseek-v4-flash"),
                        timeout=config.get("timeout", 60), max_retries=0, env_file=None)


def plugin():
  """声明 deepseek.chat；关闭底层自动重试，使请求次数与宿主预算一致。"""
  return PluginDefinition("deepseek", "0.1.0", "1.0", (
      ComponentDefinition("deepseek.chat", "llm", _client, {
          "type": "object", "additionalProperties": False,
          "properties": {
              "api_key_env": {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
              "model": {"type": "string", "minLength": 1},
              "timeout": {"type": "number", "exclusiveMinimum": 0, "maximum": 300}},
          "required": ["api_key_env"]}, credentials=("api_key_env",)),
  ))
