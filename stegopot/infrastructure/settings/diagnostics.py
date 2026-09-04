"""离线环境诊断与运行环境摘要，不下载权重、不导入重型模型、不读取密钥。"""

from collections.abc import Mapping
from importlib import metadata
import json
from pathlib import Path
import platform
from typing import Any

from stegopot.domain.model.diagnostic import Diagnostic


def environment_manifest() -> dict[str, Any]:
  """返回解释器、系统和已安装依赖版本；不记录用户名、环境变量或安装绝对路径。"""
  return {"python": platform.python_version(), "implementation": platform.python_implementation(),
          "system": platform.system(), "machine": platform.machine(),
          "distributions": sorted(
              ({"name": item.metadata["Name"], "version": item.version} for item in metadata.distributions()
               if item.metadata.get("Name")), key=lambda item: item["name"].lower())}


def diagnose_resources(resources: Mapping[str, Mapping[str, Any]]) -> tuple[Diagnostic, ...]:
  """静态检查 resources 的已知本地前提；不构造模型，也不宣称推理或算法已经兼容。

  参数：
    resources: type/config 形式资源声明；不含已解析的 API 密钥。

  返回：
    缺失依赖、模型文件等诊断；第三方资源须自行实现其运行诊断。
  """
  issues = []
  for name, spec in resources.items():
    path = f"resources.{name}.config"
    if spec["type"] == "core.stegokit":
      for package in ("numpy", "torch", "transformers"):
        try:
          metadata.version(package)
        except metadata.PackageNotFoundError:
          issues.append(Diagnostic("environment.dependency_missing", path,
                                   f"缺少本地隐写依赖 {package}", "安装框架的 stego 可选依赖"))
      vendor = Path(__file__).resolve().parents[1] / "vendor" / "stego-kit"
      if not vendor.is_dir() or not any(vendor.rglob("*.py")):
        issues.append(Diagnostic("environment.vendor_missing", path,
                                 "StegoKit 源码未完整安装", "初始化子模块或重新安装完整分发包"))
      model = Path(spec["config"]["model_path"]).expanduser()
      if not model.is_absolute():
        issues.append(Diagnostic("environment.relative_model_path", path + ".model_path",
                                 "本地模型使用相对路径", "使用绝对路径，避免工作目录改变模型来源", severity="warning"))
      if not model.is_dir():
        issues.append(Diagnostic("environment.model_missing", path + ".model_path",
                                 "本地模型目录不存在", "准备本地模型后填写有效 model_path"))
        continue
      try:
        configuration = model / "config.json"
        if not configuration.is_file():
          raise ValueError("缺少模型配置")
        value = json.loads(configuration.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
          raise ValueError("配置不是对象")
        if not any((model / filename).is_file() for filename in (
            "tokenizer.json", "tokenizer.model", "vocab.json", "vocab.txt", "spiece.model")):
          issues.append(Diagnostic("environment.tokenizer_missing", path + ".model_path",
                                   "未找到常见 tokenizer 词表文件", "补齐 tokenizer；特殊布局需自行验证"))
        if not any(model.glob("*.safetensors")) and not any(model.glob("pytorch_model*.bin")):
          issues.append(Diagnostic("environment.weights_missing", path + ".model_path",
                                   "未找到常见本地模型权重", "补齐权重；此检查不会自动下载"))
        for index in model.glob("*.index.json"):
          shards = json.loads(index.read_text(encoding="utf-8")).get("weight_map", {})
          if any(not isinstance(shard, str) or not (model / shard).resolve().is_relative_to(model.resolve())
                 or not (model / shard).is_file() for shard in shards.values()):
            issues.append(Diagnostic("environment.weights_incomplete", path + ".model_path",
                                     "权重索引包含缺失或越界分片", "重新准备完整本地权重"))
      except (OSError, ValueError, AttributeError):
        issues.append(Diagnostic("environment.model_metadata_invalid", path + ".model_path",
                                 "模型配置或索引无法安全读取", "检查 JSON 格式与文件读取权限"))
  issues.append(Diagnostic("environment.offline_only", "environment",
                           "只完成离线文件与安装元数据检查，未执行网络、模型加载或编解码",
                           "真实模型兼容性须通过使用者明确选择的实验验证", severity="info"))
  return tuple(issues)
