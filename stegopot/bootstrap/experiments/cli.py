"""统一命令入口；只做参数解析、接口调用和退出码转换，不承载实验算法。"""

from collections.abc import Sequence
import argparse
import json
import os
from pathlib import Path
import re

from stegopot import __version__
from stegopot.bootstrap.experiments.api import prepare_file
from stegopot.bootstrap.experiments.builtin import builtin_plugin
from stegopot.bootstrap.experiments.run import run_experiment
from stegopot.infrastructure.plugins.catalog import PluginCatalog, installed_plugins
from stegopot.infrastructure.recorders.audit.integrity import verify_experiment, verify_study
from stegopot.infrastructure.settings.experiment import CONFIG_SCHEMA
from stegopot.infrastructure.settings.workspace import ExperimentWorkspace


def _parser() -> argparse.ArgumentParser:
  """构造命令参数；所有帮助说明均为中文，解析本身不执行插件。"""
  parser = argparse.ArgumentParser(prog="stegopot", description="多 Agent 隐写实验框架")
  parser.add_argument("--version", action="version", version=f"StegoPot {__version__}")
  commands = parser.add_subparsers(dest="command", required=True)
  init = commands.add_parser("init", help="创建空实验工作区，不附带历史实验")
  init.add_argument("directory", nargs="?", default=".", help="工作区目录，默认当前目录")
  listing = commands.add_parser("list", help="列出 configs 中的实验配置，不执行")
  listing.add_argument("--workspace", default=".", help="工作区根目录")
  for command in ("run", "validate"):
    sub = commands.add_parser(command, help="运行实验" if command == "run" else "预检配置，不请求模型")
    sub.add_argument("config", nargs="?", help="配置名或文件路径；省略时要求 configs 中恰好一份配置")
    sub.add_argument("--workspace", default=".", help="工作区根目录，默认当前目录")
    env = sub.add_mutually_exclusive_group()
    env.add_argument("--env-file", help="凭证文件，默认工作区 .env；已有进程环境优先")
    env.add_argument("--no-env", action="store_true", help="不读取 .env，只使用进程环境")
    if command == "run":
      sub.add_argument("--output", help="结果父目录，默认工作区 outputs；每次生成唯一子目录")
  plugins = commands.add_parser("plugins", help="查看安装与组件接口").add_subparsers(dest="operation", required=True)
  plugins.add_parser("list", help="只列安装元数据，不加载第三方代码")
  plugins.add_parser("inspect", help="显式加载指定插件并查看接口").add_argument("name", help="插件 ID，例如 core")
  verify = commands.add_parser("verify", help="离线验证审计日志与封印")
  verify.add_argument("directory", help="已完成或待核验的运行目录")
  verify.add_argument("--expected-seal-sha256", help="事先独立保管的根封印 SHA-256")
  schema = commands.add_parser("schema", help="输出配置或内置组件的 JSON Schema")
  schema.add_argument("--component", help="内置组件 ID，例如 core.chat_completions；插件使用 plugins inspect")
  return parser


def main(argv: Sequence[str] | None = None) -> int:
  """执行一条框架命令。

  参数：
    argv: 命令行参数序列；None 使用进程参数，供控制台和嵌入测试共用。

  返回：
    0 表示成功；1 表示实验已记录但存在失败或跳过；2 表示配置、环境或执行入口错误。
    argparse 的帮助和语法错误沿用 SystemExit 行为。不得输出完整凭证环境。
  """
  args = _parser().parse_args(argv)
  environment = dict(os.environ)
  try:
    if args.command == "init":
      layout = ExperimentWorkspace(Path(args.directory))
      payload = {"workspace": str(layout.root), "configs": str(layout.initialize()),
                 "message": "请将自己的 JSON/YAML 配置放入 configs，再运行 stegopot run <名称>"}
    elif args.command == "list":
      layout = ExperimentWorkspace(Path(args.workspace))
      payload = {"workspace": str(layout.root), "configs": [
          {"name": path.relative_to(layout.configs).with_suffix("").as_posix(),
           "path": path.relative_to(layout.root).as_posix()} for path in layout.discover()]}
    elif args.command == "plugins":
      if args.operation == "list":
        payload = [{"id": "core", "version": __version__, "distribution": "stegopot"}, *installed_plugins()]
      else:
        catalog = PluginCatalog(builtin_plugin())
        if args.name != "core":
          catalog.load([args.name])
        payload = [item for item in catalog.describe() if item["id"] == args.name]
    elif args.command == "schema":
      payload = CONFIG_SCHEMA
      if args.component:
        components = {item.component_id: item for item in builtin_plugin().components}
        if args.component not in components:
          raise ValueError("未知内置组件，请先查看 stegopot plugins inspect core")
        payload = components[args.component].config_schema
    elif args.command == "verify":
      directory = Path(args.directory).expanduser().resolve()
      verifier = verify_experiment if (directory / "experiment-report.json").exists() else verify_study
      verifier(directory, expected_seal_sha256=args.expected_seal_sha256)
      payload = {"verified": True, "directory": str(directory)}
    else:
      layout = ExperimentWorkspace(Path(args.workspace))
      environment = layout.environment(env_file=args.env_file, load_env=not args.no_env)
      prepared = prepare_file(args.config, workspace=layout.root, load_env=False, environment=environment)
      if args.command == "validate":
        payload = {"valid": True, "trials": len(prepared.plan.trials),
                   "plugins": [item["id"] for item in prepared.catalog.describe()]}
      else:
        output = layout.outputs if args.output is None else layout.root / Path(args.output).expanduser()
        report, directory = run_experiment(prepared, output=output)
        payload = {"status": report["status"], "directory": str(directory),
                   "summary": report["summary"], "model_calls": report["model_calls"]}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "completed" else 1
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0
  except Exception as exc:
    message = str(exc)
    for name, value in environment.items():
      if value and any(word in name.upper() for word in ("KEY", "TOKEN", "PASSWORD", "SECRET")):
        message = message.replace(value, "[REDACTED]")
    message = re.sub(r"sk-[A-Za-z0-9_-]{16,}", "[REDACTED]", message)
    print(f"执行失败（{type(exc).__name__}）：{message}")
    return 2
