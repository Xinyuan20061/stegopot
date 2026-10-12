"""面向 LLM 隐写与多智能体研究的可控实验底座。"""

from stegopot.application.services.runtime.model import ModelRuntime
from stegopot.domain.model.attribution import (
    EAPEdge,
    EAPObservation,
    EAPResult,
    EAPScore,
)
from stegopot.domain.model.capability import Capability, MissingCapabilityError
from stegopot.domain.model.data import DatasetBundle, Sample, SplitPolicy
from stegopot.domain.model.intervention_runtime import Intervention
from stegopot.domain.model.reference import TensorRef, TracePolicy
from stegopot.domain.model.runtime import GenerationConfig, ModelInput
from stegopot.domain.model.sae import (
    SAECompatibilityError,
    SAEFeatureRef,
    SAEManifest,
    SAEReconstructionReport,
)

__version__ = "2.1.0"

__all__ = [
    "Capability", "DatasetBundle", "EAPEdge", "EAPObservation", "EAPResult",
    "EAPScore", "GenerationConfig", "Intervention", "MissingCapabilityError",
    "ModelInput", "ModelRuntime", "SAECompatibilityError", "SAEFeatureRef",
    "SAEManifest", "SAEReconstructionReport", "Sample", "SplitPolicy", "TensorRef",
    "TracePolicy", "__version__",
]
