"""DeepSeek 请求相关测试。

本测试文件包含两类测试：
1. 默认运行的离线测试：不访问网络、不需要 API 密钥。
2. 显式开启的真实请求测试：需要设置 DEEPSEEK_API_KEY 和
   RUN_DEEPSEEK_LIVE_TEST=1。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import urllib.error

from stegopot.utils.env import load_env_file
from stegopot.utils.llm import DeepSeekClient
from stegopot.utils.llm import JsonActionParser
from stegopot.utils.llm import LLMMessage
from stegopot.utils.policies import LLMPolicy


class DeepSeekRequestTest(unittest.TestCase):
  """DeepSeek 客户端请求构造和响应解析测试。"""

  def test_build_request_body_uses_default_values(self) -> None:
    """验证请求体会使用默认模型和 JSON 响应格式。"""
    client = DeepSeekClient(
        api_key="test-key",
        default_model="deepseek-test-model",
        default_temperature=0.2,
        default_max_tokens=128,
    )

    body = client._build_request_body(
        messages=[LLMMessage(role="user", content="你好")],
        model=None,
        temperature=None,
        max_tokens=None,
    )

    self.assertEqual(body["model"], "deepseek-test-model")
    self.assertEqual(body["temperature"], 0.2)
    self.assertEqual(body["max_tokens"], 128)
    self.assertEqual(body["response_format"], {"type": "json_object"})
    self.assertEqual(body["messages"], [{"role": "user", "content": "你好"}])
    self.assertFalse(body["stream"])

  def test_build_request_body_allows_per_call_overrides(self) -> None:
    """验证单次调用参数可以覆盖客户端默认参数。"""
    client = DeepSeekClient(
        api_key="test-key",
        default_model="deepseek-default",
        default_temperature=0.1,
        default_max_tokens=64,
    )

    body = client._build_request_body(
        messages=[LLMMessage(role="user", content="测试")],
        model="deepseek-override",
        temperature=0.7,
        max_tokens=256,
    )

    self.assertEqual(body["model"], "deepseek-override")
    self.assertEqual(body["temperature"], 0.7)
    self.assertEqual(body["max_tokens"], 256)

  def test_missing_api_key_raises_clear_error(self) -> None:
    """验证缺少密钥时不会发请求，并给出清晰错误。"""
    client = DeepSeekClient(api_key=None, api_key_env="MISSING_DEEPSEEK_KEY")

    with self.assertRaisesRegex(ValueError, "缺少 DeepSeek API 密钥"):
      client.generate([LLMMessage(role="user", content="你好")])

  def test_client_can_read_api_key_from_env_file(self) -> None:
    """验证客户端可以从 .env 文件读取 DeepSeek 密钥。"""
    with tempfile.TemporaryDirectory() as temp_dir:
      env_path = Path(temp_dir) / ".env"
      env_path.write_text(
          "DEEPSEEK_API_KEY=sk-from-env-file\n",
          encoding="utf-8",
      )
      old_value = os.environ.pop("DEEPSEEK_API_KEY", None)
      try:
        client = DeepSeekClient(env_file=env_path)
        body = client._build_request_body(
            messages=[LLMMessage(role="user", content="你好")],
            model=None,
            temperature=None,
            max_tokens=None,
        )
        self.assertEqual(client._api_key, "sk-from-env-file")
        self.assertEqual(body["model"], "deepseek-v4-flash")
      finally:
        os.environ.pop("DEEPSEEK_API_KEY", None)
        if old_value is not None:
          os.environ["DEEPSEEK_API_KEY"] = old_value

  def test_parse_response_returns_standard_llm_response(self) -> None:
    """验证 DeepSeek 响应会被解析成统一 LLMResponse。"""
    client = DeepSeekClient(api_key="test-key")
    raw_response = {
        "id": "chatcmpl-test",
        "model": "deepseek-test-model",
        "choices": [{
            "message": {
                "role": "assistant",
                "content": '{"kind":"message","content":"你好","target":"b"}',
            },
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        },
    }

    response = client._parse_response(json.dumps(raw_response))

    self.assertEqual(
        response.content,
        '{"kind":"message","content":"你好","target":"b"}',
    )
    self.assertEqual(response.metadata["provider"], "deepseek")
    self.assertEqual(response.metadata["model"], "deepseek-test-model")
    self.assertEqual(response.metadata["usage"]["total_tokens"], 15)

  @mock.patch("stegopot.utils.llm.deepseek_client.urllib.request.urlopen")
  def test_generate_retries_temporary_network_error(self, urlopen) -> None:
    """验证临时连接错误会重试，并在后续成功时返回响应。"""
    response = mock.MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps({
        "id": "chatcmpl-retry",
        "model": "deepseek-test-model",
        "choices": [{
            "message": {"role": "assistant", "content": '{"kind":"wait"}'},
            "finish_reason": "stop",
        }],
    }).encode("utf-8")
    urlopen.side_effect = [
        urllib.error.URLError("temporary error"),
        response,
    ]
    client = DeepSeekClient(
        api_key="test-key",
        max_retries=1,
        retry_backoff=0,
    )

    result = client.generate([LLMMessage(role="user", content="你好")])

    self.assertEqual(result.content, '{"kind":"wait"}')
    self.assertEqual(urlopen.call_count, 2)

  @unittest.skipUnless(
      os.environ.get("RUN_DEEPSEEK_LIVE_TEST") == "1"
      and bool(os.environ.get("DEEPSEEK_API_KEY")),
      "需要设置 DEEPSEEK_API_KEY 和 RUN_DEEPSEEK_LIVE_TEST=1 才运行真实请求",
  )
  def test_live_deepseek_request_can_drive_llm_policy(self) -> None:
    """真实请求测试：验证 DeepSeek 可以驱动 LLMPolicy 输出动作。

    环境变量：
      DEEPSEEK_API_KEY: DeepSeek API 密钥。
      RUN_DEEPSEEK_LIVE_TEST: 设置为 "1" 时才允许真实联网请求。
    """
    client = DeepSeekClient(default_model="deepseek-v4-flash", timeout=60.0)
    node = LLMPolicy(
        node_id="deepseek_test_sender",
        role="sender",
        client=client,
        model="deepseek-v4-flash",
        temperature=0.0,
        max_tokens=128,
    )

    state = node.initial_state()
    action, state = node.step(
        {
            "task": (
                "只输出 JSON："
                '{"kind":"message","content":"ping","target":"receiver"}'
            )
        },
        state,
    )

    self.assertIn(action.kind, {"message", "wait", "final_answer", "audit"})
    self.assertEqual(state.step_count, 1)
    self.assertIsNotNone(state.last_action)
    self.assertIn("llm_metadata", action.metadata)


class JsonActionParserTest(unittest.TestCase):
  """模型输出 JSON 到结构化动作的解析测试。"""

  def test_parse_model_json_action(self) -> None:
    """验证合法 JSON 输出可以解析为动作对象。"""
    parser = JsonActionParser()

    action = parser.parse(
        '{"kind":"message","content":"hello","target":"receiver"}'
    )

    self.assertEqual(action.kind, "message")
    self.assertEqual(action.content, "hello")
    self.assertEqual(action.target, "receiver")

  def test_empty_model_message_is_normalized_to_wait(self) -> None:
    """验证模型产生的空消息会被安全地规范化为等待动作。"""
    parser = JsonActionParser()

    action = parser.parse(
        '{"kind":"message","content":"  ","target":null}'
    )

    self.assertEqual(action.kind, "wait")
    self.assertIsNone(action.content)
    self.assertEqual(action.metadata["normalized_from"], "empty_message")

  def test_empty_model_response_is_normalized_to_wait(self) -> None:
    """验证完全为空的模型响应也会被安全地规范化为等待动作。"""
    parser = JsonActionParser()

    action = parser.parse("   ")

    self.assertEqual(action.kind, "wait")
    self.assertIsNone(action.content)
    self.assertEqual(action.metadata["normalized_from"], "empty_response")


class EnvFileTest(unittest.TestCase):
  """本地 .env 文件加载测试。"""

  def test_load_env_file_parses_values_and_comments(self) -> None:
    """验证 .env 加载器支持空行、注释、引号和行尾注释。"""
    with tempfile.TemporaryDirectory() as temp_dir:
      env_path = Path(temp_dir) / ".env"
      env_path.write_text(
          "\n"
          "# 注释行\n"
          "PLAIN_VALUE=abc # 行尾注释\n"
          "QUOTED_VALUE=\"hello # not comment\"\n",
          encoding="utf-8",
      )
      old_plain = os.environ.pop("PLAIN_VALUE", None)
      old_quoted = os.environ.pop("QUOTED_VALUE", None)
      try:
        loaded = load_env_file(env_path)
        self.assertEqual(loaded["PLAIN_VALUE"], "abc")
        self.assertEqual(loaded["QUOTED_VALUE"], "hello # not comment")
        self.assertEqual(os.environ["PLAIN_VALUE"], "abc")
      finally:
        os.environ.pop("PLAIN_VALUE", None)
        os.environ.pop("QUOTED_VALUE", None)
        if old_plain is not None:
          os.environ["PLAIN_VALUE"] = old_plain
        if old_quoted is not None:
          os.environ["QUOTED_VALUE"] = old_quoted

  def test_load_env_file_does_not_override_by_default(self) -> None:
    """验证默认不会覆盖已有环境变量。"""
    with tempfile.TemporaryDirectory() as temp_dir:
      env_path = Path(temp_dir) / ".env"
      env_path.write_text("EXISTING_VALUE=from-file\n", encoding="utf-8")
      old_value = os.environ.get("EXISTING_VALUE")
      os.environ["EXISTING_VALUE"] = "from-env"
      try:
        loaded = load_env_file(env_path)
        self.assertNotIn("EXISTING_VALUE", loaded)
        self.assertEqual(os.environ["EXISTING_VALUE"], "from-env")
      finally:
        if old_value is None:
          os.environ.pop("EXISTING_VALUE", None)
        else:
          os.environ["EXISTING_VALUE"] = old_value


if __name__ == "__main__":
  unittest.main()
