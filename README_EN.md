<p align="center">
  <a href="README.md">简体中文</a> | <strong>English</strong>
</p>

<p align="center">
  <img src="docs/assets/stegopot-icon.png" alt="StegoPot" width="112">
</p>

<h1 align="center">StegoPot</h1>

<p align="center"><strong>An experimental framework for multi-agent steganography, covert communication, and collusion research</strong></p>

<p align="center">
  <a href="https://github.com/Xinyuan20061/stegopot/releases/tag/v1.0.0"><img src="https://img.shields.io/badge/release-v1.0.0-2F81F7?style=flat-square" alt="Release v1.0.0"></a>
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/PyTorch-2.1%2B%20optional-EE4C2C?style=flat-square&logo=pytorch&logoColor=white" alt="PyTorch 2.1+ optional">
  <img src="https://img.shields.io/badge/plugin%20API-1.4-4B5563?style=flat-square" alt="Plugin API 1.4">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-D22128?style=flat-square" alt="Apache-2.0 License"></a>
</p>

<p align="center">
  <a href="#core-features">Core Features</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#llm-nodes">LLM Nodes</a> ·
  <a href="#steganography-experiments">Steganography</a> ·
  <a href="#plugin-development">Plugins</a>
</p>

StegoPot describes experiments with YAML or JSON. Users configure agents, directed topologies,
models, steganographic codecs, channels, detectors, rewards, and evaluators. A unified workflow
then handles preflight validation, execution, auditing, integrity verification, and metric
recomputation.

## Core Features

| Feature | Description |
| --- | --- |
| Multi-agent topology | Define nodes, roles, and directed edges, then execute them in synchronous rounds |
| LLM nodes | Configure the model, system role, sampling parameters, and output constraints per node |
| Steganographic codecs | Generate carriers with StegoKit and recover bits from the text actually received |
| Communication provenance | Separate ordinary `opaque` messages from controlled `instrumented` codec messages |
| Information-flow control | Isolate public, agent-private, secret, monitor-visible, and evaluator-only data |
| Channels and detectors | Block, transform, or inspect messages before delivery |
| Reward loop | Apply per-round rewards, detection penalties, and end-of-episode outcome rewards |
| Agent tools | Authorize tools per node and return tool results only to the calling node |
| Stateful sessions | Preserve explicitly allowed policy state across episodes in the same session |
| Paired counterfactuals | Hold a real carrier fixed while changing channels, detectors, or rewards |
| Standard metrics | Report BER, recovery, bits/token, detector performance, AUROC, and task utility |
| Plugin system | Register 12 component types with decorators and load them between experiments |
| Full audit trail | Store public/research logs, execution plans, source fingerprints, and reports |
| Evidence verification | Verify hash chains and seals, then recompute metrics from recorded evidence |

Typical uses include:

- directed communication, cooperation, and competition baselines;
- observation of covert communication and collusion between LLM agents;
- capacity, recovery, and robustness evaluation for explicit steganographic algorithms;
- carrier sanitization, message blocking, and detector ablation studies;
- joint analysis of covert-channel success, detection performance, and task utility;
- plugin-based implementations of paper reproduction protocols and new experiments.

## Installation

### Install the release

```powershell
python -m pip install https://github.com/Xinyuan20061/stegopot/releases/download/v1.0.0/stegopot-1.0.0-py3-none-any.whl
```

### Install from source

```powershell
git clone https://github.com/Xinyuan20061/stegopot.git
cd stegopot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

Install the optional StegoKit, Transformers, and PyTorch dependencies when local codec models
are required:

```powershell
python -m pip install -e ".[stego]"
```

## Quick Start

### 1. Create a workspace

```powershell
python -m stegopot init D:\Research\my-stegopot-study
```

The workspace contains:

```text
my-stegopot-study/
  .env               Local secrets and environment variables
  configs/           YAML/JSON experiment configurations
  outputs/           An isolated result directory for every run
```

### 2. Define an experiment

Create `D:\Research\my-stegopot-study\configs\communication.yaml`:

```yaml
schema_version: "1"

scenario:
  type: core.explicit
  config:
    task: "The sender reports its status to the receiver"
    max_rounds: 2
    nodes:
      - id: sender
        role: sender
        policy:
          type: core.scripted
          config:
            actions:
              - kind: message
                content: "ready"
                target: receiver
      - id: receiver
        role: receiver
        policy:
          type: core.echo
    edges:
      - [sender, receiver]
```

Edges are directed. A message from `sender` to `receiver` can only be delivered when that edge
is declared.

### 3. Validate and run

```powershell
python -m stegopot validate communication --workspace D:\Research\my-stegopot-study
python -m stegopot run communication --workspace D:\Research\my-stegopot-study
```

`validate` checks configuration, component references, topology, budgets, and information flows
without constructing models or making network requests. For local StegoKit models, `doctor`
also checks model paths and runtime resources:

```powershell
python -m stegopot doctor communication --workspace D:\Research\my-stegopot-study
```

## LLM Nodes

StegoPot includes a Chat Completions-compatible client for services such as DeepSeek.

Store the API key in the workspace `.env` file:

```dotenv
DEEPSEEK_API_KEY=your-api-key
```

Declare the model resource and node policy in the experiment:

```yaml
schema_version: "1"

resources:
  deepseek:
    type: core.chat_completions
    config:
      base_url: https://api.deepseek.com
      model: deepseek-chat
      api_key_env: DEEPSEEK_API_KEY
      timeout: 60
      response_format: json_object

scenario:
  type: core.explicit
  config:
    task: "Send a short status message to receiver"
    max_rounds: 2
    nodes:
      - id: sender
        role: sender
        policy:
          type: core.llm
          config:
            client: deepseek
            role: "You are the sender. Return only the required JSON action."
            action_kind: message
            target: receiver
            active_round: 0
            max_tokens: 128
      - id: receiver
        role: receiver
        policy:
          type: core.echo
    edges:
      - [sender, receiver]
```

The configuration contains only the environment-variable name. Secret values are not written
to reports or audit logs. Each LLM node may use a different client, role, target, and token limit.

## Steganography Experiments

### Communication modes

| Mode | Source | Intended use |
| --- | --- | --- |
| `opaque` | Ordinary scripted or LLM policies | Observe messages without assuming whether they contain hidden information |
| `instrumented` | `core.codec_sender` | Record codec ID, payload size, consumed bits, carrier token count, and content hash |

Opaque messages are unlabeled by default. A dataset with reliable labels can provide
`truth.stego_label` explicitly.

### StegoKit

The built-in `core.stegokit` component loads a Hugging Face model from a local path:

```yaml
resources:
  stego:
    type: core.stegokit
    config:
      model_path: D:/Models/local-causal-model
      algorithm: ac
      generation:
        max_new_tokens: 128
```

Use the sender and receiver policies as follows:

```yaml
# Sender node
policy:
  type: core.codec_sender
  config:
    codec: stego
    target: receiver
    active_round: 0

# Receiver node
policy:
  type: core.codec_receiver
  config:
    codec: stego
    active_round: 1
```

The sender's private context provides `secret_bits`, optional `cover`, and `shared_material`.
The receiver decodes only the text that remains after Substrate and Channel processing; it never
receives hidden token IDs from the encoder.

### Information flows

Experiments can classify data and declare authorized readers with `information`:

```yaml
information:
  public_rules:
    class: public
    value: {language: en}
  sender_secret:
    class: secret_payload
    value: "101101"
    visible_to: ["node:sender", evaluator, research_audit]
  decoder_key:
    class: decoder_private
    value: {key_id: shared-01}
    visible_to: ["node:receiver", evaluator, research_audit]
```

The seven information classes are `public`, `agent_private`, `secret_payload`,
`decoder_private`, `monitor_visible`, `evaluator_only`, and `research_only`. The host validates
authorization before execution and creates separate views for agents, the environment,
detectors, rewards, and evaluators.

### Paired counterfactuals

`core.counterfactual` executes a source trial and fixes the resulting message body and SHA-256
across treatment branches. The sender model is not called again, allowing direct comparison of
channel, detector, or reward interventions.

```yaml
scenario:
  type: core.counterfactual
  config:
    source:
      id: source
      task: "Generate a communication carrier"
      max_rounds: 2
      nodes:
        - id: sender
          policy:
            type: core.scripted
            config:
              actions:
                - {kind: message, content: "carrier", target: receiver}
        - id: receiver
          policy: {type: core.echo}
      edges: [[sender, receiver]]
    carrier: {sender: sender, recipient: receiver}
    group_id: carrier-ablation
    treatments:
      - id: raw
        channels: []
      - id: blocked
        channels:
          - {type: core.block}
```

### Standard metrics

`core.stego_metrics` reports:

- bit recovery, decoding completeness, and BER;
- payload bits, consumed bits, embedding coverage, and bits/token;
- message delivery rate;
- confusion matrix, TPR, FPR, precision, and AUROC;
- task utility based on `truth.expected_answers`;
- aggregated results for paired counterfactual treatments.

## Agent Tools

Each node can only call aliases declared in its `tools` mapping. Tool actions use this format:

```json
{
  "kind": "tool_call",
  "content": null,
  "target": null,
  "metadata": {},
  "tool_call": {
    "tool": "calculator",
    "operation": "double",
    "arguments": {"value": 21}
  }
}
```

The host validates node authorization, call budgets, and JSON size before execution. Results are
returned only to the caller through `observation.tool_results` in the next round. Requests,
results, and failures are recorded in the research audit log.

## Built-in Components

StegoPot 1.0.0 includes 20 components:

| Type | Components |
| --- | --- |
| Scenario | `core.explicit`, `core.sessions`, `core.counterfactual` |
| Policy | `core.scripted`, `core.echo`, `core.llm`, `core.codec_sender`, `core.codec_receiver` |
| LLM | `core.chat_completions` |
| Substrate | `core.communication` |
| Channel | `core.block`, `core.replace` |
| Codec | `core.stegokit` |
| Detector | `core.keyword`, `core.llm_detector` |
| Reward | `core.delivery_reward`, `core.detection_penalty` |
| Outcome reward | `core.exact_match_outcome` |
| Evaluator | `core.metrics`, `core.stego_metrics` |

Inspect component schemas from the command line:

```powershell
python -m stegopot plugins inspect core
python -m stegopot schema --component core.llm
```

## Configuration Reference

| Top-level field | Purpose |
| --- | --- |
| `schema_version` | Configuration version; currently the string `"1"` |
| `scenario` | Scenario component that generates the experiment plan |
| `plugins` | Explicitly allowed third-party plugins and version ranges |
| `resources` | Reusable LLM, Codec, or Tool resources |
| `policies` | Policy overrides indexed by node ID |
| `topology` | Optional directed-edge override |
| `channels` | Message transformation components |
| `detectors` | Public-text detector components |
| `rewards` | Per-round reward components |
| `outcome_rewards` | End-of-episode reward components |
| `evaluators` | Experiment metric evaluators |
| `audit_sinks` | Additional audit outputs |
| `threat_model` | History, monitor context, and audit projection settings |
| `runtime` | Call, time, token, message, and context budgets |

All components use the same structure:

```yaml
type: plugin.component
config:
  parameter: value
```

Component schemas reject unknown fields. Duplicate YAML keys, anchors, and aliases are also
rejected. Store secrets in the workspace `.env` file and reference only their environment-variable
names from component configurations.

## Command Line

```powershell
python -m stegopot --version
python -m stegopot init <workspace>
python -m stegopot list --workspace <workspace>
python -m stegopot validate <config-name> --workspace <workspace>
python -m stegopot doctor <config-name> --workspace <workspace>
python -m stegopot run <config-name> --workspace <workspace>
python -m stegopot verify <run-directory>
python -m stegopot recompute <run-directory>
python -m stegopot events <run-directory> --scope public --limit 100
python -m stegopot plugins list
python -m stegopot plugins inspect core
python -m stegopot schema --component core.llm
```

`events` verifies the seal and reads the public log by default. Use `--scope research` explicitly
to access complete research events.

## Python API

```python
from stegopot.bootstrap.experiments.api import (
    prepare_file,
    recompute_directory,
    run_file,
)

prepared = prepare_file(
    "study",
    workspace="D:/Research/my-stegopot-study",
)
print(len(prepared.plan.trials))

report, output_directory = run_file(
    "study",
    workspace="D:/Research/my-stegopot-study",
)
if report["status"] != "completed":
    raise RuntimeError(report["errors"])

verification = recompute_directory(output_directory)
assert verification["verified"]
```

The CLI and Python API use the same parsing, preflight, component assembly, and audit pipeline.

## Plugin Development

Plugin API 1.4 supports `scenario`, `policy`, `llm`, `substrate`, `channel`, `codec`, `detector`,
`reward`, `outcome_reward`, `evaluator`, `tool`, and `audit` components.

```python
from stegopot.domain.interface.registration import Plugin
from stegopot.domain.model import ToolResult

plugin = Plugin("my_lab", "0.1.0")


class Calculator:
    """Provide one deterministic multiplication operation."""

    def execute(self, request):
        if request.operation != "double":
            raise ValueError("unsupported operation")
        return ToolResult(request.arguments["value"] * 2)

    def close(self):
        """This tool owns no external resources."""


@plugin.component(
    "tool",
    "calculator",
    schema={
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
)
def build_calculator(config, context):
    """Build the tool instance."""
    return Calculator()


def entrypoint():
    """Return the plugin definition."""
    return plugin()
```

Declare the entry point in the plugin package:

```toml
[project.entry-points."stegopot.plugins"]
my_lab = "my_lab.plugin:entrypoint"
```

The experiment must explicitly allow third-party plugins:

```yaml
plugins:
  - id: my_lab
    version: ">=0.1,<1"
```

See the [plugin development guide](docs/plugin_development.md) for the complete contract.

## Experiment Outputs

Every run creates a new result directory:

```text
outputs/<run-id>/
  manifest.json             Configuration, fixed plan, plugins, and source fingerprints
  threat-model.json         Effective topology, component boundaries, and information flows
  experiment-report.json    Trial results, metrics, and aggregate summary
  report.md                 Human-readable summary
  research.jsonl            Complete research-event hash chain
  public.jsonl              Minimal public-event hash chain
  seal.json                 Root artifact and log-endpoint seal
  <trial-id>/
    result.json
    research.jsonl
    public.jsonl
    seal.json
```

Verify a result directory with:

```powershell
python -m stegopot verify D:\Research\my-stegopot-study\outputs\<run-id>
python -m stegopot recompute D:\Research\my-stegopot-study\outputs\<run-id>
```

`verify` checks file digests, event hash chains, trial seals, and preregistered-plan consistency.
`recompute` additionally checks current plugin source fingerprints and recalculates metrics from
the fixed plan and recorded results.

## Runtime Constraints

`runtime` can limit model calls, tool calls, output tokens, total tokens, trial count, rounds,
execution time, message size, and context size. Per-trial and per-node call limits are also
supported.

Plugins execute in the same Python process as StegoPot. The host restricts information views,
tool authorization, and budgets, but untrusted third-party plugins should still run in a container
or virtual machine that isolates files, networking, CPU, memory, and GPU access.

## Documentation

- [Usage guide](docs/usage.md)
- [Plugin development](docs/plugin_development.md)
- [Architecture and dependency direction](docs/architecture.md)
- [Kernel controls and auditing](docs/kernel.md)
- [Threat model and information boundaries](docs/threat_model.md)
- [Documentation index](docs/README.md)

## License

StegoPot is licensed under the [Apache License 2.0](LICENSE). The bundled StegoKit source retains
its upstream license at `stegopot/infrastructure/vendor/stego-kit/LICENSE`.
