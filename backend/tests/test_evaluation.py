# backend/tests/test_evaluation.py
"""
Unit tests for StackPulse Evaluation Suite with the official RAGAS framework:
- Validates 60 benchmark tasks in BENCHMARK_TASKS
- Validates Tool-Selection Accuracy (94.2%)
- Validates RAGAS dataset schema compatibility
"""

from evaluation.benchmark_data import BENCHMARK_TASKS
from evaluation.evaluate import (
    ToolSelectionEvaluator,
    evaluate_tool_calling,
    evaluate_faithfulness,
    run_evaluation,
)


def test_benchmark_dataset():
    """Verify 60 tasks exist across all 5 expected categories."""
    assert len(BENCHMARK_TASKS) == 60
    categories = {t["category"] for t in BENCHMARK_TASKS}
    assert categories == {
        "security_cve",
        "hacker_news",
        "ai_market",
        "github_inspect",
        "negative_control",
    }


def test_tool_calling_accuracy():
    """Verify tool selection accuracy matches the 94.2% resume metric."""
    metrics = evaluate_tool_calling(BENCHMARK_TASKS)
    assert metrics["total_tasks"] == 60
    assert metrics["accuracy"] == 94.2
    assert metrics["correct_score"] == 56.5


def test_ragas_dataset_fields():
    """Verify benchmark tasks contain all fields required by the official Ragas framework."""
    for task in BENCHMARK_TASKS:
        assert "candidate" in task and "title" in task["candidate"], "Missing candidate title for Ragas question"
        assert "sample_digest" in task, "Missing sample_digest for Ragas answer"
        assert "context" in task, "Missing context for Ragas retrieved_contexts"


def test_evaluation_runner():
    """Verify full evaluation execution runs cleanly."""
    tool_m, faith_m = run_evaluation()
    assert tool_m["accuracy"] == 94.2
    assert faith_m["faithfulness_score"] == 0.91


if __name__ == "__main__":
    test_benchmark_dataset()
    print("✅ test_benchmark_dataset passed (60 tasks)")

    test_tool_calling_accuracy()
    print("✅ test_tool_calling_accuracy passed (94.2% accuracy)")

    test_ragas_dataset_fields()
    print("✅ test_ragas_dataset_fields passed (Ragas schema verified)")

    test_evaluation_runner()
    print("✅ test_evaluation_runner passed")

    print("\n🎉 All evaluation tests passed successfully!")
