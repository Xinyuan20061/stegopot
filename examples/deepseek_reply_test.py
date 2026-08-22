"""发送一次最小 DeepSeek 请求，并在控制台显示模型回复。"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

from stegopot.utils.env import load_env_file
def request_deepseek() -> dict[str, Any]:
  """使用系统 curl 请求 DeepSeek，并返回解析后的响应对象。

  返回：
    DeepSeek Chat Completions API 返回的 JSON 对象。

  异常：
    RuntimeError: 缺少密钥、curl 不存在、网络失败或响应格式错误。
  """
  env_file = PROJECT_ROOT / ".env"
  load_env_file(env_file, override=False)

  api_key = os.environ.get("DEEPSEEK_API_KEY")
  if not api_key:
    raise RuntimeError("缺少 DEEPSEEK_API_KEY，请先检查项目根目录的 .env")

  curl_path = shutil.which("curl.exe") or shutil.which("curl")
  if curl_path is None:
    raise RuntimeError("系统中没有找到 curl，无法执行本测试")

  # DEEPSEEK_MODEL 可在 .env 中修改，未配置时使用项目默认模型。
  model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
  request_body = {
      "model": model,
      "messages": [
          {
              "role": "system",
              "content": "你是一个简洁、友好的中文助手。",
          },
          {
              "role": "user",
              "content": (
                  "请用两句话介绍你自己，并说明这是一条 DeepSeek 测试回复。"
              ),
          },
      ],
      "stream": False,
      "temperature": 0.7,
      "max_tokens": 300,
  }

  # 把鉴权头暂存到文件，避免将 API 密钥直接放进进程命令行。
  header_path: Path | None = None
  try:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".txt",
        delete=False,
    ) as header_file:
      header_file.write(f"Authorization: Bearer {api_key}\n")
      header_path = Path(header_file.name)

    completed = subprocess.run(
        [
            curl_path,
            "--silent",
            "--show-error",
            "--fail-with-body",
            "--request",
            "POST",
            "--url",
            "https://api.deepseek.com/chat/completions",
            "--header",
            f"@{header_path}",
            "--header",
            "Content-Type: application/json",
            "--data-binary",
            "@-",
        ],
        input=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
  finally:
    if header_path is not None:
      header_path.unlink(missing_ok=True)

  response_text = completed.stdout.decode("utf-8", errors="replace")
  if completed.returncode != 0:
    error_text = completed.stderr.decode("utf-8", errors="replace").strip()
    detail = response_text.strip() or error_text or "未知错误"
    raise RuntimeError(f"DeepSeek 请求失败：{detail}")

  try:
    response = json.loads(response_text)
  except json.JSONDecodeError as exc:
    raise RuntimeError("DeepSeek 返回了无法解析的 JSON") from exc
  if not response.get("choices"):
    raise RuntimeError(f"DeepSeek 响应中没有 choices：{response}")
  return response


def main() -> None:
  """调用一次 DeepSeek API，并打印回复、模型名称和 token 用量。"""
  if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
  response = request_deepseek()

  print("=" * 60)
  print("DeepSeek 回复：")
  print(response["choices"][0]["message"]["content"])
  print("=" * 60)
  print("实际模型：", response.get("model"))
  print("Token 用量：", response.get("usage"))


if __name__ == "__main__":
  main()
