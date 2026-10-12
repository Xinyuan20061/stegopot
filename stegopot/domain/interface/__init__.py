"""StegoPot 对后端和插件公开的稳定协议。"""

from stegopot.domain.interface.attribution import EdgeAttributor
from stegopot.domain.interface.channel import ChannelTransform
from stegopot.domain.interface.codec import (
    Carrier,
    DecodeRequest,
    DecodeResult,
    EncodeRequest,
    EncodeResult,
    StegoCodec,
)
from stegopot.domain.interface.data import (
    DatasetSource,
    DatasetStore,
    DatasetTransform,
    DatasetValidator,
)
from stegopot.domain.interface.detector import StegoDetector
from stegopot.domain.interface.events import EventBus, EventSink
from stegopot.domain.interface.experiment import (
    Evaluator,
    OutcomeRewardFunction,
    RewardFunction,
    ScenarioProvider,
)
from stegopot.domain.interface.intervention import TensorOperator
from stegopot.domain.interface.llm import LLMClient, LLMMessage, LLMResponse
from stegopot.domain.interface.observation import (
    ObservationBuilder,
    ObservationContext,
)
from stegopot.domain.interface.plugin import (
    BuildContext,
    ComponentDefinition,
    PluginDefinition,
)
from stegopot.domain.interface.policy import Policy
from stegopot.domain.interface.probe import Probe, ProbeLoader
from stegopot.domain.interface.research import (
    Analyzer,
    Metric,
    Reporter,
    ResearchScenario,
)
from stegopot.domain.interface.runtime import (
    ControlledRuntime,
    GenerationStep,
    ModelAdapter,
    TokenGenerationSession,
)
from stegopot.domain.interface.sae import SAEModel
from stegopot.domain.interface.storage import ArtifactStore, TraceStore
from stegopot.domain.interface.stego import (
    StegoEmbedRequest,
    StegoEmbedResult,
    StegoExtractRequest,
    StegoExtractResult,
    StegoGenerationConfig,
    StegoTool,
)
from stegopot.domain.interface.substrate import (
    Substrate,
    SubstrateEvent,
    SubstrateResetContext,
    SubstrateStepContext,
    SubstrateStepResult,
)
from stegopot.domain.interface.tool import ToolExecutor

__all__ = [
    "Analyzer", "ArtifactStore", "BuildContext", "Carrier", "ChannelTransform",
    "ComponentDefinition", "ControlledRuntime", "DatasetSource", "DatasetStore",
    "DatasetTransform", "DatasetValidator", "DecodeRequest", "DecodeResult",
    "EdgeAttributor", "EncodeRequest", "EncodeResult", "Evaluator", "EventBus", "EventSink",
    "GenerationStep", "LLMClient", "LLMMessage", "LLMResponse", "Metric",
    "ModelAdapter", "ObservationBuilder", "ObservationContext",
    "OutcomeRewardFunction", "PluginDefinition", "Policy", "Probe",
    "ProbeLoader", "Reporter", "ResearchScenario", "RewardFunction",
    "SAEModel", "ScenarioProvider", "StegoCodec", "StegoDetector", "StegoEmbedRequest",
    "StegoEmbedResult", "StegoExtractRequest", "StegoExtractResult",
    "StegoGenerationConfig", "StegoTool", "Substrate", "SubstrateEvent",
    "SubstrateResetContext", "SubstrateStepContext", "SubstrateStepResult",
    "TensorOperator",
    "TokenGenerationSession", "ToolExecutor", "TraceStore",
]
