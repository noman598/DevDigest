# backend/evaluation/__init__.py
"""
StackPulse Evaluation Framework using the official RAGAS library.
"""

from .benchmark_data import BENCHMARK_TASKS
from .evaluate import (
    ToolSelectionEvaluator,
    RagasFaithfulnessEvaluator,
    RAGAS_INSTALLED,
    evaluate_tool_calling,
    evaluate_faithfulness,
    run_evaluation,
)

__all__ = [
    "BENCHMARK_TASKS",
    "ToolSelectionEvaluator",
    "RagasFaithfulnessEvaluator",
    "RAGAS_INSTALLED",
    "evaluate_tool_calling",
    "evaluate_faithfulness",
    "run_evaluation",
]
