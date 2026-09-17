"""Local-model adapters for the image-driven detail-page flow.

This package provides the local-only Gemma and Flux adapters used by both the
CLI preview runner and the FastAPI service.
"""

from .adapters import LocalProductAnalyzer
from .clients import (
    LocalModelError,
    MlxServeChatClient,
    MlxServeImageClient,
    OllamaChatClient,
)
from .runner import (
    MlxServeBackgroundGenerator,
    MlxServeDetailViewGenerator,
    MlxServeUsageSceneGenerator,
    build_local_pipeline,
    save_pipeline_result,
)

__all__ = [
    "LocalModelError",
    "MlxServeChatClient",
    "MlxServeImageClient",
    "MlxServeBackgroundGenerator",
    "MlxServeDetailViewGenerator",
    "MlxServeUsageSceneGenerator",
    "LocalProductAnalyzer",
    "OllamaChatClient",
    "build_local_pipeline",
    "save_pipeline_result",
]
