"""统一配置命令入口；不承载实验算法。"""

import argparse
import json
import os
import re
from pathlib import Path

from stegopot.bootstrap.experiments.builtin import builtin_plugin
from stegopot.bootstrap.experiments.prepare import prepare_experiment
from stegopot.bootstrap.experiments.run import run_experiment
from stegopot.infrastructure.plugins.catalog import PluginCatalog, installed_plugins
from stegopot.infrastructure.settings.env import load_env_file
from stegopot.infrastructure.settings.experiment import CONFIG_SCHEMA, load_config
from stegopot.infrastructure.recorders.audit.integrity import verify_experiment, verify_study


def main(argv=None):
  """处理 argv 参数列表；为空时读取进程参数，返回命令退出码。"""
  parser = argparse.ArgumentParser(prog="stegopot", description="配置驱动的多智能体实验与审计")
  commands = parser.add_subparsers(dest="command", required=True)
  for command in ("run", "validate"):
    sub = commands.add_parser(command)
    sub.add_argument("config", help="实验 JSON 或 YAML 路径")
    sub.add_argument("--env-file", default=None, help="显式加载的环境变量文件，不打印内容")
    if command == "run":
      sub.add_argument("--output", default="artifacts/experiments", help="审计结果父目录")
  plugins = commands.add_parser("plugins").add_subparsers(dest="operation", required=True)
  plugins.add_parser("list")
  plugins.add_parser("inspect").add_argument("name")
  verify = commands.add_parser("verify")
  verify.add_argument("directory")
  verify.add_argument("--expected-seal-sha256")
  commands.add_parser("schema")
  args = parser.parse_args(argv)
  try:
    if args.command == "plugins":
      if args.operation == "list":
        payload = installed_plugins()
      else:
        catalog = PluginCatalog(builtin_plugin())
        if args.name != "core":
          catalog.load([args.name])
        payload = [item for item in catalog.describe() if item["id"] == args.name]
    elif args.command == "schema":
      payload = CONFIG_SCHEMA
    elif args.command == "verify":
      verifier = verify_experiment if (Path(args.directory) / "experiment-report.json").exists() else verify_study
      verifier(args.directory, expected_seal_sha256=args.expected_seal_sha256)
      payload = {"verified": True, "directory": str(Path(args.directory).resolve())}
    else:
      if args.env_file:
        if not Path(args.env_file).is_file():
          raise ValueError("指定的环境文件不存在")
        load_env_file(args.env_file)
      prepared = prepare_experiment(load_config(args.config))
      if args.command == "validate":
        payload = {"valid": True, "trials": len(prepared.plan.trials),
                   "plugins": [item["id"] for item in prepared.catalog.describe()]}
      else:
        report, directory = run_experiment(prepared, output=args.output)
        payload = {"status": report["status"], "directory": str(directory), "summary": report["summary"],
                   "model_calls": report["model_calls"]}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "completed" else 1
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0
  except Exception as exc:
    message = str(exc)
    for name, value in os.environ.items():
      if value and any(word in name.upper() for word in ("KEY", "TOKEN", "PASSWORD", "SECRET")):
        message = message.replace(value, "[REDACTED]")
    message = re.sub(r"sk-[A-Za-z0-9_-]{16,}", "[REDACTED]", message)
    print(f"执行失败（{type(exc).__name__}）：{message}")
    return 2
