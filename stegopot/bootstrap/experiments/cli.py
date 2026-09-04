"""统一命令入口；只做参数解析、接口调用和退出码转换，不承载实验算法。"""

from collections.abc import Sequence
import argparse
from itertools import islice
import json
import os
from pathlib import Path
import re

from stegopot import __version__
from stegopot.bootstrap.experiments.api import prepare_file
from stegopot.bootstrap.experiments.builtin import builtin_plugin
from stegopot.bootstrap.experiments.run import run_experiment
from stegopot.bootstrap.experiments.signals import cancellation_signals
from stegopot.domain.model.diagnostic import PreflightError
from stegopot.domain.model.execution import CancellationToken
from stegopot.infrastructure.plugins.catalog import PluginCatalog, installed_plugins
from stegopot.infrastructure.recorders.audit.integrity import verify_experiment, verify_study
from stegopot.infrastructure.recorders.audit.reader import AuditReader
from stegopot.infrastructure.settings.diagnostics import diagnose_resources
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
  for command in ("run", "validate", "doctor"):
    help_text = {"run": "运行实验", "validate": "纯预检配置", "doctor": "预检并检查本地依赖和模型文件，不请求网络"}
    sub = commands.add_parser(command, help=help_text[command])
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
  events = commands.add_parser("events", help="查询审计事件，默认核验封印且只读公开视图")
  events.add_argument("directory", help="实验结果目录")
  events.add_argument("--scope", choices=("public", "research"), default="public", help="research 含私有研究数据，不能直接公开")
  events.add_argument("--trial", help="试验 ID")
  events.add_argument("--node", help="节点 ID")
  events.add_argument("--round", dest="round_index", type=int, help="轮次，从 0 开始")
  events.add_argument("--message", help="消息 ID")
  events.add_argument("--call", help="模型或工具调用 ID")
  events.add_argument("--span", help="研究调用链作用域 ID")
  events.add_argument("--kind", help="精确事件类型")
  events.add_argument("--limit", type=int, default=100, help="最多输出事件数，1 至 10000")
  events.add_argument("--unverified", action="store_true", help="显式调查未封印目录，不代表核验通过")
  events.add_argument("--expected-seal-sha256", help="独立保存的根封印 SHA-256")
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
    elif args.command == "events":
      if not 1 <= args.limit <= 10000:
        raise ValueError("limit 必须为 1 至 10000")
      reader = AuditReader(args.directory, verify=not args.unverified,
                           expected_seal_sha256=args.expected_seal_sha256)
      records = reader.events(scope=args.scope, trial_id=args.trial, node_id=args.node,
                               round_index=args.round_index, message_id=args.message,
                               call_id=args.call, span_id=args.span, kind=args.kind)
      payload = {"verified": reader.verified, "scope": args.scope,
                 "events": list(islice(records, args.limit))}
    else:
      layout = ExperimentWorkspace(Path(args.workspace))
      environment = layout.environment(env_file=args.env_file, load_env=not args.no_env)
      prepared = prepare_file(args.config, workspace=layout.root, load_env=False, environment=environment)
      if args.command in {"validate", "doctor"}:
        diagnostics = list(prepared.diagnostics)
        if args.command == "doctor":
          diagnostics.extend(diagnose_resources(prepared.config["resources"]))
        ready = not any(item.severity == "error" for item in diagnostics)
        payload = {"valid": True, "trials": len(prepared.plan.trials),
                   "plugins": [item["id"] for item in prepared.catalog.describe()],
                   "diagnostics": [item.to_dict() for item in diagnostics]}
        if args.command == "doctor":
          payload.update(ready=ready, network_checked=False)
        _print_payload(payload, environment)
        return 0 if ready else 2
      else:
        output = layout.outputs if args.output is None else layout.root / Path(args.output).expanduser()
        cancellation = CancellationToken()
        with cancellation_signals(cancellation):
          report, directory = run_experiment(prepared, output=output, cancellation=cancellation)
        payload = {"status": report["status"], "directory": str(directory),
                   "summary": report["summary"], "model_calls": report["model_calls"],
                   "execution": report["execution"]}
        _print_payload(payload, environment)
        return 0 if report["status"] == "completed" else 1
    _print_payload(payload, environment)
    return 0
  except Exception as exc:
    if isinstance(exc, PreflightError):
      _print_payload({"valid": False, "diagnostics": [item.to_dict() for item in exc.diagnostics]}, environment)
    else:
      print(_redact(f"执行失败（{type(exc).__name__}）：{exc}", environment))
    return 2


def _redact(text: str, environment: dict[str, str]) -> str:
  """从 text 中移除 environment 已知凭证；不改写实际研究文件。"""
  for name, value in environment.items():
    if value and any(word in name.upper() for word in ("KEY", "TOKEN", "PASSWORD", "SECRET")):
      text = text.replace(value, "[REDACTED]")
  return re.sub(r"sk-[A-Za-z0-9_-]{16,}", "[REDACTED]", text)


def _print_payload(payload: object, environment: dict[str, str]) -> None:
  """将 payload 输出为经过基础设施凭证脱敏的 JSON；environment 不会整体输出。"""
  print(_redact(json.dumps(payload, ensure_ascii=False, indent=2), environment))
