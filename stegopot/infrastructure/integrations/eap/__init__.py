"""StegoPot 内置的基础 Edge Attribution Patching 能力。"""

from stegopot.infrastructure.integrations.eap.patching import (
    EdgeDeltaOperator,
    build_edge_patch,
)
from stegopot.infrastructure.integrations.eap.scorer import EAPAnalyzer

__all__ = ["EAPAnalyzer", "EdgeDeltaOperator", "build_edge_patch"]
