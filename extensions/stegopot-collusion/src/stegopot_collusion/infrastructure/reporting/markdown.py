"""将标准研究映射渲染为可阅读的逐样本审计说明。"""

from collections.abc import Mapping
from typing import Any


def render_study(report: Mapping[str, Any]) -> str:
  """把 report 渲染为中文 Markdown；不导入应用层报告类型。"""
  lines = [
      "# 合成隐写共谋实验记录", "",
      "研究专用：包含私有目标和共享协议。公开导出仅使用各样本的 public.jsonl。", "",
      f"后端：`{report['backend']}`；证据状态：`{report['evidence_status']}`。", "",
      "## 全量结果", "",
      "| 条件 | 计划 | 完成 | 失败 | 私有目标恢复 | 满足载体约束的共谋证据 |",
      "| --- | ---: | ---: | ---: | ---: | ---: |",
  ]
  for name, values in report["summary"]["conditions"].items():
    lines.append(
        f"| {name} | {values['planned']} | {values['completed']} | {values['failed']} | "
        f"{values['recovered']}/{values['planned']} | {values['covert_witnesses']} |")
  lines += ["", f"同时通过无协议和断信道对照的样本：{report['summary']['paired_witness_count']}。",
            "", "## 限制", ""]
  lines.extend(f"- {item}" for item in report["limitations"])
  lines += ["", "## 逐样本证据", ""]
  for record in report["trials"]:
    trial = record["trial"]
    evaluation = record["evaluation"]
    lines += [
        f"### {trial['case_id']} / {trial['condition']}", "",
        f"状态：{record['status']}；生成来源：{record['carrier_source']}。", "",
        f"公开规则：`{trial['public_target']}`；私有目标：`{trial['private_target']}`。", "",
        f"共享映射：`{dict(trial['codebook'])}`。", "",
        "实际送达正文（空表示信道未送达）：", "",
    ]
    lines.extend("    " + line for line in (evaluation["carrier"] or "<未送达>").splitlines())
    lines += ["", f"接收者选择：`{evaluation['receiver_choice'] or '<无答案>'}`；"
              f"观察者猜测：`{evaluation['observer_guess'] or '<本条件未调用>'}`。", "",
              f"共谋证据：{evaluation['covert_coordination_witness']}；"
              f"明文泄露选择标签：{evaluation['literal_disclosure']}。", "",
              f"完整提示、响应、动作与消息路径：`{record['artifact_dir']}/research.jsonl`。", ""]
  return "\n".join(lines) + "\n"
