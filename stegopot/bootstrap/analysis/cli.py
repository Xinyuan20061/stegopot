"""离线分析子命令参数和调度。"""

import argparse
from pathlib import Path

from stegopot.bootstrap.analysis.api import (
    attribute_path,
    combine_localizations,
    compare_paths,
    localize_runs,
)


def add_analysis_parser(commands: argparse._SubParsersAction) -> None:
  """向统一 CLI 注册 analyze 子命令。"""
  parser = commands.add_parser("analyze", help="对封印实验执行离线秘密定位和因果归因")
  operations = parser.add_subparsers(dest="analysis_command", required=True)
  localize = operations.add_parser("localize", help="生成 LocalizationMap 和 null tests")
  localize.add_argument("target", help="封印运行目录、运行组目录或 runs JSON 清单")
  localize.add_argument("--config", required=True, help="独立分析 YAML/JSON")
  localize.add_argument("--output", help="分析结果父目录")
  attribute = operations.add_parser("attribute", help="根据真实干预结果生成 CausalPathGraph")
  attribute.add_argument("analysis", help="含 localization.json 的分析目录")
  attribute.add_argument("--interventions", help="干预结果 JSON；默认分析目录/interventions.json")
  combine = operations.add_parser("combine", help="组合同一运行的多表面 LocalizationMap")
  combine.add_argument("analyses", nargs="+", help="两个或更多定位分析目录")
  combine.add_argument("--output", help="组合分析结果父目录")
  compare = operations.add_parser("compare-paths", help="比较相同协议下的路径迁移")
  compare.add_argument("before", help="迁移前分析目录或 path.json")
  compare.add_argument("after", help="迁移后分析目录或 path.json")
  compare.add_argument("--output", help="迁移分析结果父目录")


def run_analysis_command(args: argparse.Namespace) -> dict[str, object]:
  """执行已解析分析命令并返回统一 JSON 摘要。"""
  if args.analysis_command == "localize":
    result, directory = localize_runs(args.target, config=args.config, output=args.output)
    return {"analysis_id": result.analysis_id, "directory": str(directory),
            "units": len(result.units), "significant_units": sum(item.significant for item in result.units),
            "surface_scores": [item.to_dict() for item in result.surface_scores]}
  if args.analysis_command == "attribute":
    result, directory = attribute_path(args.analysis, interventions=args.interventions)
    return {"analysis_id": result.analysis_id, "directory": str(directory),
            "nodes": len(result.nodes), "causal_nodes": sum(item.causal_score is not None for item in result.nodes)}
  if args.analysis_command == "combine":
    result, directory = combine_localizations(args.analyses, output=args.output)
    return {"analysis_id": result.analysis_id, "directory": str(directory),
            "units": len(result.units),
            "surfaces": [item.surface.value for item in result.surface_scores]}
  result, directory = compare_paths(args.before, args.after, output=args.output)
  return {"directory": str(directory), **result}
