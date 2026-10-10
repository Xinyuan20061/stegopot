"""面向 LLM 隐写与多智能体研究的可控实验底座。"""

from stegopot.application.services.runtime.model import ModelRuntime
from stegopot.domain.model.capability import Capability, MissingCapabilityError
from stegopot.domain.model.data import DatasetBundle, Sample, SplitPolicy
from stegopot.domain.model.intervention_runtime import Intervention
from stegopot.domain.model.reference import TensorRef, TracePolicy
from stegopot.domain.model.runtime import GenerationConfig, ModelInput

__version__ = "2.0.0"

__all__ = [
    "Capability", "DatasetBundle", "GenerationConfig", "Intervention",
    "MissingCapabilityError", "ModelInput", "ModelRuntime", "Sample",
    "SplitPolicy", "TensorRef", "TracePolicy", "__version__",
]
