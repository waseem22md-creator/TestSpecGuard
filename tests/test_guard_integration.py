
from testspecguard.guard import TestSpecGuard


def mock_aligned(task_description, test_case):
    return {
        "status": "completed",
        "verdict": "ALIGNED",
        "is_misaligned": False,
        "computed_output": repr(test_case.expected_output),
        "expected_output": repr(test_case.expected_output),
        "reason": "Mocked test: assertion matches the task.",
    }


def mock_misaligned(task_description, test_case):
    return {
        "status": "completed",
        "verdict": "MISALIGNED",
        "is_misaligned": True,
        "computed_output": "5",
        "expected_output": repr(test_case.expected_output),
        "reason": "Mocked test: expected output contradicts the task.",
    }


def mock_s2_no_conflict(task_description, test_cases):
    flags = [
        {
            "line_number": case.line_number,
            "source": case.source,
            "eligible_candidates": 2,
            "failing_candidates": 0,
            "required_candidates": 2,
            "insufficient_candidates": False,
            "is_conflict": False,
        }
        for case in test_cases
    ]

    return {
        "status": "completed",
        "generated_candidates": 2,
        "valid_candidates": 2,
        "required_candidates": 2,
        "flags": flags,
        "conflict_detected": False,
    }


def test_guard_runs_complete_pipeline(monkeypatch):
    guard = TestSpecGuard(
        num_candidates=2,
        min_candidates=2,
    )

    monkeypatch.setattr(
        guard.execution_checker,
        "check",
        mock_s2_no_conflict,
    )

    monkeypatch.setattr(
        guard.llm_judge,
        "judge",
        mock_aligned,
    )

    result = guard.run(
        source_code="""
assert add(2, 3) == 5
assert add(4, 6) == 10
""",
        task_description=(
            "Implement a function named add(a, b) "
            "that returns the sum of a and b."
        ),
        enable_s2=True,
        enable_s3=True,
    )

    assert result["status"] == "completed"
    assert result["total_test_cases"] == 2

    assert result["S1"]["status"] == "completed"
    assert result["S2"]["status"] == "completed"
    assert result["S3"]["status"] == "completed"

    assert result["decision"]["status"] == "completed"
    assert result["decision"]["final_decision"] == "ALLOW"

    assert len(result["decision"]["decisions"]) == 2


def test_guard_detects_static_contradiction(monkeypatch):
    guard = TestSpecGuard(
        num_candidates=2,
        min_candidates=2,
    )

    monkeypatch.setattr(
        guard.llm_judge,
        "judge",
        mock_aligned,
    )

    result = guard.run(
        source_code="""
assert add(2, 3) == 5
assert add(2, 3) == 10
""",
        task_description=(
            "Implement a function named add(a, b) "
            "that returns the sum of a and b."
        ),
        enable_s2=False,
        enable_s3=True,
    )

    assert result["status"] == "completed"
    assert result["S1"]["contradiction_count"] == 1
    assert result["decision"]["final_decision"] == "BLOCK"
    assert result["decision"]["conflict_detected"] is True


def test_guard_detects_semantic_misalignment(monkeypatch):
    guard = TestSpecGuard(
        num_candidates=2,
        min_candidates=2,
    )

    monkeypatch.setattr(
        guard.llm_judge,
        "judge",
        mock_misaligned,
    )

    result = guard.run(
        source_code="""
assert add(2, 3) == 10
""",
        task_description=(
            "Implement a function named add(a, b) "
            "that returns the sum of a and b."
        ),
        enable_s2=False,
        enable_s3=True,
    )

    assert result["status"] == "completed"
    assert result["S1"]["contradiction_count"] == 0
    assert result["S3"]["results"][0]["verdict"] == "MISALIGNED"
