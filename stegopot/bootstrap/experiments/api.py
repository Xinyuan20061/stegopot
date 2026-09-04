"""面向脚本和第三方应用的文件级入口，与 CLI 共用配置和运行链路。"""

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from stegopot.bootstrap.experiments.prepare import PreparedExperiment, prepare_experiment
from stegopot.bootstrap.experiments.run import run_experiment
from stegopot.infrastructure.plugins.catalog import PluginCatalog
from stegopot.infrastructure.settings.experiment import load_config
from stegopot.infrastructure.settings.workspace import ExperimentWorkspace


def prepare_file(
    config: str | Path | None = None, *, workspace: str | Path = ".",
    env_file: str | Path | None = None, load_env: bool = True,
    environment: Mapping[str, str] | None = None, catalog: PluginCatalog | None = None,
) -> PreparedExperiment:
  """从用户配置准备实验，不创建模型客户端、不写结果。

  参数：
    config: 配置名或文件路径；为空时选择工作区中唯一配置。
    workspace: 工作区根目录；凭证、相对配置与默认结果归属于该目录。
    env_file: 可选凭证文件；默认读取工作区 .env，不修改进程环境。
    load_env: False 时不读取任何凭证文件。
    environment: 显式环境覆盖值，仅用于当前预检与后续授权注入。
    catalog: 可选的调用方注册表；注入时由调用方负责登记所需插件。

  返回：
    固定的准备结果；包含私有凭证，不能公开或传给检测节点。
    格式、组件或资源错误在执行前抛出，第三方场景须遵守无副作用契约。
  """
  layout = ExperimentWorkspace(Path(workspace))
  source = layout.resolve_config(config)
  values = layout.environment(env_file=env_file, load_env=load_env, overrides=environment)
  return prepare_experiment(load_config(source), catalog=catalog, environment=values)


def run_file(
    config: str | Path | None = None, *, workspace: str | Path = ".",
    output: str | Path | None = None, env_file: str | Path | None = None,
    load_env: bool = True, environment: Mapping[str, str] | None = None,
    catalog: PluginCatalog | None = None,
    progress: Callable[[Mapping[str, Any]], None] | None = None,
) -> tuple[dict[str, Any], Path]:
  """运行用户配置并返回完整研究报告与审计目录。

  参数：
    config: configs 中的配置名或文件路径；为空时要求配置唯一。
    workspace: 工作区根目录，默认当前目录，不切换进程工作目录。
    output: 结果父目录；默认 workspace/outputs，相对路径以工作区为基准。
    env_file: 凭证文件路径；默认使用工作区 .env。
    load_env: 是否允许读取凭证文件。
    environment: 当前调用的环境覆盖值，不影响其他实验或 os.environ。
    catalog: 调用者预先注册的组件目录；为空时只加载配置明确允许的已安装插件。
    progress: 每个试验结束后的回调；不可修改或向未授权对象公开研究记录。

  返回：
    (report, directory)。普通组件失败保存在报告中，调用者必须检查 status；
    审计失败会抛出异常。框架拥有本次创建组件的关闭责任，不覆写以前的结果。
  """
  prepared = prepare_file(config, workspace=workspace, env_file=env_file, load_env=load_env,
                          environment=environment, catalog=catalog)
  layout = ExperimentWorkspace(Path(workspace))
  destination = layout.outputs if output is None else layout.root / Path(output).expanduser()
  return run_experiment(prepared, output=destination, progress=progress)
