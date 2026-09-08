"""JSON 审计链的确定性序列化、哈希和离线完整性检查。"""

import hashlib
import json
from pathlib import Path
from typing import Any


def canonical_json(value: Any) -> str:
  """生成跨运行稳定的 JSON；value 必须可序列化且不包含 NaN。"""
  return json.dumps(value, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
  """返回 value 的规范 JSON 的 SHA-256 摘要。"""
  return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_digest(path: Path) -> str:
  """返回 path 文件字节的 SHA-256 摘要，不加载整个文件到内存。"""
  checksum = hashlib.sha256()
  with path.open("rb") as stream:
    for block in iter(lambda: stream.read(65536), b""):
      checksum.update(block)
  return checksum.hexdigest()


def verify_audit(
    directory: str | Path, *, expected_seal_sha256: str | None = None,
) -> dict[str, Any]:
  """验证双审计链、终点封印和关联报告，不发起模型调用。

  参数：
    directory: 含 research.jsonl、public.jsonl 和 seal.json 的目录。
    expected_seal_sha256: 可选的外部保存封印哈希；用于发现封印本身被替换。

  返回：
    校验通过的封印内容。失败时抛出 ValueError；无外部锚点时不能防止
    攻击者同时重写日志和封印，这不是数字签名或防篡改存储。
  """
  root = Path(directory).resolve()
  seal_path = root / "seal.json"
  if expected_seal_sha256 and file_digest(seal_path) != expected_seal_sha256:
    raise ValueError("封印与外部锚点不一致")
  seal = json.loads(seal_path.read_text(encoding="utf-8"))
  if seal.get("schema_version") != "1.0":
    raise ValueError("不支持的审计封印版本")
  for scope in ("research", "public"):
    previous = "0" * 64
    count = 0
    with (root / f"{scope}.jsonl").open(encoding="utf-8") as stream:
      for count, line in enumerate(stream, 1):
        record = json.loads(line)
        checksum = record.pop("hash", None)
        if (record.get("seq") != count or record.get("prev_hash") != previous
            or record.get("scope") != scope
            or record.get("run_id") != seal.get("run_id")
            or digest(record) != checksum):
          raise ValueError(f"{scope} 审计链第 {count} 条损坏")
        previous = checksum
    if seal["streams"][scope] != {"count": count, "head": previous}:
      raise ValueError(f"{scope} 审计链截断或封印不一致")
  for name, checksum in seal.get("artifacts", {}).items():
    path = root / name
    if Path(name).name != name or path.resolve().parent != root:
      raise ValueError("封印包含越界路径")
    if file_digest(path) != checksum:
      raise ValueError(f"关联文件被修改：{name}")
  return seal


def verify_experiment(directory: str | Path, *, expected_seal_sha256: str | None = None) -> dict[str, Any]:
  """校验 directory 标准报告与全部子试验；expected_seal_sha256 是可选外部锚点。"""
  root = Path(directory).resolve()
  seal = verify_audit(root, expected_seal_sha256=expected_seal_sha256)
  required = {'manifest.json', 'experiment-report.json', 'report.md'}
  if not required.issubset(seal.get('artifacts', {})):
    raise ValueError('根封印缺少标准实验工件')
  report = json.loads((root / 'experiment-report.json').read_text(encoding='utf-8'))
  manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
  manifest_version = manifest.get('schema_version')
  if manifest_version not in {
      'stegopot.manifest/1',
      'stegopot.manifest/2',
      'stegopot.manifest/3',
  }:
    raise ValueError('未知实验清单版本')
  if manifest_version in {'stegopot.manifest/2', 'stegopot.manifest/3'}:
    if 'threat-model.json' not in seal.get('artifacts', {}):
      raise ValueError('根封印缺少威胁模型工件')
    threat_ref = manifest.get('threat_model', {})
    threat_path = root / 'threat-model.json'
    if (threat_ref.get('artifact') != 'threat-model.json'
        or threat_ref.get('sha256') != file_digest(threat_path)):
      raise ValueError('实验清单与威胁模型工件不一致')
    threat_model = json.loads(threat_path.read_text(encoding='utf-8'))
    allowed_threat_versions = (
        {'stegopot.threat-model/2'}
        if manifest_version == 'stegopot.manifest/3'
        else {'stegopot.threat-model/1', 'stegopot.threat-model/2'}
    )
    if threat_model.get('schema_version') not in allowed_threat_versions:
      raise ValueError('未知威胁模型工件版本')
    if threat_model.get('plan_sha256') != digest(manifest.get('plan')):
      raise ValueError('威胁模型与预注册计划不一致')
    topology = [{
        'trial_id': trial['trial_id'],
        'nodes': [node['node_id'] for node in trial['nodes']],
        'edges': trial['edges'],
    } for trial in manifest['plan']['trials']]
    if threat_model.get('topology_sha256') != digest(topology):
      raise ValueError('威胁模型与预注册拓扑不一致')
    if threat_model.get('schema_version') == 'stegopot.threat-model/2':
      _verify_information_flows(manifest['plan']['trials'], threat_model)
  if report.get('schema_version') != 'stegopot.report/1':
    raise ValueError('未知实验报告版本')
  planned_trials = manifest['plan']['trials']
  if [item['trial']['trial_id'] for item in report['trials']] != [item['trial_id'] for item in planned_trials]:
    raise ValueError('试验记录与预注册计划不一致')
  for record, planned in zip(report['trials'], planned_trials):
    if record['trial'] != planned:
      raise ValueError('试验执行声明与预注册计划内容不一致')
    name = record['artifact_dir']
    child = root / name
    if Path(name).name != name or child.resolve().parent != root:
      raise ValueError('试验目录越界')
    child_seal = verify_audit(child, expected_seal_sha256=record['seal_sha256'])
    if 'result.json' not in child_seal.get('artifacts', {}):
      raise ValueError('子试验缺少结果封印')
    result = json.loads((child / 'result.json').read_text(encoding='utf-8'))
    if result != {key: value for key, value in record.items() if key not in {'artifact_dir', 'seal_sha256'}}:
      raise ValueError('根报告与子试验结果不一致')
  return seal


def _verify_information_flows(
    trials: list[dict[str, Any]],
    threat_model: dict[str, Any],
) -> None:
  """验证类型化信息目录与完整计划一致，且威胁模型没有泄露实际值。"""
  flows = threat_model.get('information_flows')
  if not isinstance(flows, dict) or set(flows) != {
      trial['trial_id'] for trial in trials
  }:
    raise ValueError('威胁模型的信息流目录与预注册试验不一致')
  for trial in trials:
    trial_id = trial['trial_id']
    information = trial.get('information', {})
    flow = flows[trial_id]
    if flow.get('trial_id') != trial_id:
      raise ValueError('信息流目录包含错误试验 ID')
    if flow.get('specification_sha256') != digest(information):
      raise ValueError('信息流声明摘要与预注册信息值不一致')
    expected_assets = {
        name: {key: value for key, value in item.items() if key != 'value'}
        for name, item in information.items()
    }
    if flow.get('assets') != expected_assets:
      raise ValueError('威胁模型信息资产目录不一致或泄露实际值')
    principals = {
        principal
        for item in information.values()
        for principal in item.get('visible_to', ())
        if principal != 'all_nodes'
    }
    principals.update(
        'node:' + node['node_id'] for node in trial.get('nodes', ())
    )
    expected_views = {
        principal: [
            name
            for name, item in information.items()
            if principal in item.get('visible_to', ())
            or (
                principal.startswith('node:')
                and 'all_nodes' in item.get('visible_to', ())
            )
        ]
        for principal in sorted(principals)
    }
    if flow.get('principal_assets') != expected_views:
      raise ValueError('威胁模型逐主体信息投影与预注册计划不一致')
