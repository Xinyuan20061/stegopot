<p align="center">
  <a href="README.md">简体中文</a> | <strong>English</strong>
</p>

<p align="center">
  <img src="docs/assets/stegopot-icon.png" alt="StegoPot" width="112">
</p>

<h1 align="center">StegoPot</h1>

<p align="center"><strong>A controllable experimental substrate for LLM steganography and multi-agent research</strong></p>

<p align="center">
  <img src="https://img.shields.io/badge/version-2.0.0-2F81F7?style=flat-square" alt="Version 2.0.0">
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/PyTorch-optional-EE4C2C?style=flat-square&logo=pytorch&logoColor=white" alt="PyTorch optional">
  <img src="https://img.shields.io/badge/plugin%20API-1.5-4B5563?style=flat-square" alt="Plugin API 1.5">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-D22128?style=flat-square" alt="Apache-2.0 License"></a>
</p>

StegoPot unifies controlled model execution, internal-state access, dataset processing, multi-agent
interaction, steganography foundations, and experiment lifecycle management. The core does not
implement a paper-specific algorithm. Datasets, protocols, probes, attribution methods, metrics,
and scenarios are supplied by configuration and independently installed plugins.

## Capabilities

| Capability | Description |
| --- | --- |
| Controlled forward | Normal, selectively traced, graph-retaining, and intervened forward passes |
| Internal state | Activation and gradient access through layer/component/token-level `TensorRef` |
| Token-step generation | Inspect, intervene, sample, and explicitly commit each output token |
| Basic interventions | Replace, Zero, Scale, Add, Interpolate, and conditional triggering |
| Dataset pipeline | Source, transform, validate, grouped split, fingerprint, and store |
| Probe boundary | Build per-layer datasets from ActivationTrace; algorithms stay in plugins |
| Research lifecycle | Dataset -> Scenario -> Analyze -> Evaluate -> Save |
| Multi-agent runtime | Nodes, directed topology, channels, detectors, rewards, and sessions |
| Model backends | Hugging Face white-box adapter and Chat Completions black-box client |
| Steganography | Built-in StegoKit adapter and message-flow integration |
| Plugins | Strict schemas, decorator registration, dependency injection, capability preflight |
| Reproducibility | Configuration, environment, plugins, outputs, tensor references, and SHA-256 seal |

EAP, SAE, probe trainers, clean/corrupt pairs, one-bit protocols, paper scenarios, and bundled
experiments are intentionally outside the core.

## Architecture

```text
bootstrap
  ├── application: runtime, data, research, multi-agent engine
  └── infrastructure: model adapters, LLM clients, StegoKit, storage, audit
                         ↓
                       domain: models and interfaces
```

The package keeps four physical layers only: `domain`, `application`, `infrastructure`, and
`bootstrap`. See [Architecture](docs/architecture.md).

## Installation

```powershell
git clone https://github.com/Xinyuan20061/stegopot.git
cd stegopot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

Install `.[whitebox]` for Hugging Face internal-state access or `.[stego]` for StegoKit.

## Controlled Model API

```python
from stegopot import ModelInput, ModelRuntime, TensorRef, TracePolicy
from stegopot.infrastructure.model_adapters import HuggingFaceAdapter

adapter = HuggingFaceAdapter(
    model_path="D:/Models/your-causal-lm",
    revision="fixed-revision",
    local_files_only=True,
)
runtime = ModelRuntime(adapter)

ref = TensorRef(layer=12, component="resid_post", token=-1)
result = runtime.forward(
    ModelInput("Inspect this prompt"),
    policy=TracePolicy(refs=(ref,), store="cpu"),
)
print(result.trace.get(ref).shape)
runtime.close()
```

Gradient capture, interventions, and token-step generation are documented in
[Runtime Kernel](docs/kernel.md).

## Configuration

```powershell
stegopot init D:\Research\my-study
stegopot validate experiment --workspace D:\Research\my-study
stegopot doctor experiment --workspace D:\Research\my-study
stegopot run experiment --workspace D:\Research\my-study
```

Schema v2 composes externally supplied research components:

```yaml
schema_version: "2"
plugins: [my_study]
seed: 7
runtime:
  adapter:
    type: core.huggingface
    config:
      model_path: D:/Models/your-causal-lm
      revision: fixed-revision
      local_files_only: true
dataset:
  source:
    type: my_study.dataset
  count: 100
scenario:
  type: my_study.scenario
analyzers:
  - type: my_study.analyzer
metrics:
  - type: my_study.metric
```

`my_study.*` is provided by the user's plugin package. Component schemas, references, credentials,
and model capabilities are validated before model loading. Schema v1 remains available for
multi-agent message experiments.

## Plugins

```python
from stegopot.domain.interface.registration import Plugin
from stegopot.domain.model.capability import Capability

plugin = Plugin("my_study", "0.1.0")

@plugin.component(
    "analyzer",
    "gradient_method",
    requires=(Capability.ACTIVATION_READ, Capability.GRADIENT_READ),
)
def build_analyzer(config, context):
  return GradientAnalyzer(**config)
```

Plugins depend on capabilities, not the concrete Hugging Face adapter. They are loaded only when
explicitly enabled in the configuration. See [Plugin Development](docs/plugin_development.md).

## API Models, Agents, and StegoKit

`core.chat_completions` supports DeepSeek and compatible services. It is a black-box `llm`
resource and does not claim activation or gradient access. Schema v1 composes agent policies,
directed topologies, channels, detectors, rewards, tools, and evaluators. `core.stegokit` supplies
the core codec integration. See [Usage](docs/usage.md).

## Outputs and Trust Boundary

Schema v2 writes a unique run directory containing `config.json`, `metadata.json`,
`outputs.jsonl`, `metrics.json`, optional trace artifacts, and `manifest.json`.
Full activation capture is never enabled by default. Runtime events contain no raw tensors.

Plugins run as trusted in-process Python code. StegoPot enforces interface-level data boundaries,
not operating-system isolation. Run untrusted plugins in an external container or restricted
process.

## Documentation

- [Architecture](docs/architecture.md)
- [Runtime Kernel](docs/kernel.md)
- [Usage](docs/usage.md)
- [Plugin Development](docs/plugin_development.md)
- [Threat Model](docs/threat_model.md)
