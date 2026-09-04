# StegoPot DeepSeek

可选供应商适配扩展，注册 `deepseek.chat`。
核心框架不依赖它才能运行；基础隐写能力也不需要 DeepSeek API。

配置必须提供 `api_key_env` 环境变量引用，可指定 `model` 与 `timeout`。
工厂只接收宿主授权凭证，关闭底层自动重试以保持调用预算清晰。
保留旧客户端的直接 Python 调用能力，迁移导入路径为
`stegopot_deepseek.infrastructure.client.DeepSeekClient`。
