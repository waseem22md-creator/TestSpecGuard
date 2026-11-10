
from testspecguard.execution_checker import ExecutionChecker
from testspecguard.parser import TestCase


def make_tests():
    return [
        TestCase(
            function_name="solve",
            args=(1,),
            kwargs={},
            expected_output=1,
            line_number=1,
            source="assert solve(1) == 1",
        ),
        TestCase(
            function_name="solve",
            args=(2,),
            kwargs={},
            expected_output=2,
            line_number=2,
            source="assert solve(2) == 2",
        ),
        TestCase(
            function_name="solve",
            args=(3,),
            kwargs={},
            expected_output=3,
            line_number=3,
            source="assert solve(3) == 3",
        ),
    ]


def test_leave_one_out_detects_conflicting_test(monkeypatch):
    checker = ExecutionChecker(
        num_candidates=2,
        min_candidates=2,
    )

    monkeypatch.setattr(
        checker,
        "generate_candidates",
        lambda description: ["candidate_1", "candidate_2"],
    )

    outcomes = {
        "candidate_1": [True, False, True],
        "candidate_2": [True, False, True],
    }

    monkeypatch.setattr(
        checker,
        "_execute_candidate",
        lambda candidate, tests: {
            "valid": True,
            "results": outcomes[candidate],
        },
    )

    result = checker.check(
        "Implement a function that returns its input.",
        make_tests(),
    )

    assert result["status"] == "completed"
    assert result["valid_candidates"] == 2

    assert result["flags"][0]["is_conflict"] is False
    assert result["flags"][1]["is_conflict"] is True
    assert result["flags"][2]["is_conflict"] is False

    assert result["conflict_detected"] is True


def test_insufficient_candidates_disables_s2(monkeypatch):
    checker = ExecutionChecker(
        num_candidates=5,
        min_candidates=2,
    )

    monkeypatch.setattr(
        checker,
        "generate_candidates",
        lambda description: ["candidate_1"],
    )

    monkeypatch.setattr(
        checker,
        "_execute_candidate",
        lambda candidate, tests: {
            "valid": True,
            "results": [True, True, True],
        },
    )

    result = checker.check(
        "Implement a function that returns its input.",
        make_tests(),
    )

    assert result["status"] == "completed"
    assert result["valid_candidates"] == 1
    assert len(result["flags"]) == 3

    for flag in result["flags"]:
        assert flag["insufficient_candidates"] is True
        assert flag["is_conflict"] is False


def test_no_valid_candidates(monkeypatch):
    checker = ExecutionChecker(
        num_candidates=2,
        min_candidates=2,
    )

    monkeypatch.setattr(
        checker,
        "generate_candidates",
        lambda description: ["candidate_1", "candidate_2"],
    )

    monkeypatch.setattr(
        checker,
        "_execute_candidate",
        lambda candidate, tests: {
            "valid": False,
            "error": "Execution failed",
        },
    )

    result = checker.check(
        "Implement a function that returns its input.",
        make_tests(),
    )

    assert result["status"] == "completed"
    assert result["valid_candidates"] == 0
    assert len(result["flags"]) == 3

    for flag in result["flags"]:
        assert flag["insufficient_candidates"] is True
        assert flag["is_conflict"] is False
