
from typing import Any

from .parser import TestParser
from .static_checker import StaticContradictionChecker
from .execution_checker import ExecutionChecker
from .llm_judge import LLMJudge
from .decision_engine import DecisionEngine


class TestSpecGuard:
    """
    Central integration layer for TestSpecGuard.

    S1 - Static Contradiction Detection
    S2 - Leave-One-Out Execution Checking
    S3 - LLM-Based Semantic Judging
    """

    __test__ = False

    def __init__(
        self,
        model: str = "qwen2.5-coder:3b",
        num_candidates: int = 5,
        min_candidates: int = 1,
        timeout: int = 5,
        judge_model: str = "qwen2.5-coder:7b",
    ) -> None:
        self.parser = TestParser()
        self.static_checker = StaticContradictionChecker()

        # S2: Candidate generation and execution model
        self.execution_checker = ExecutionChecker(
            model=model,
            num_candidates=num_candidates,
            min_candidates=min_candidates,
            timeout=timeout,
        )

        # S3: Independent semantic judging model
        self.llm_judge = LLMJudge(
            model=judge_model,
            debug=False,
        )

        self.decision_engine = DecisionEngine()

    def run(
        self,
        source_code: str,
        task_description: str,
        enable_s2: bool = True,
        enable_s3: bool = True,
    ) -> dict[str, Any]:

        if not source_code.strip():
            raise ValueError("Source code cannot be empty")

        if not task_description.strip():
            raise ValueError("Task description cannot be empty")

        # Parse assertions
        test_cases = self.parser.parse(source_code)

        if not test_cases:
            return {
                "status": "no_supported_assertions",
                "total_test_cases": 0,
                "S1": {
                    "status": "skipped",
                    "contradictions": [],
                },
                "S2": {
                    "status": "skipped",
                    "flags": [],
                },
                "S3": {
                    "status": "skipped",
                    "results": [],
                },
                "decision": {
                    "status": "skipped",
                    "final_decision": "NO_SUPPORTED_ASSERTIONS",
                },
            }

        # S1: Static contradiction detection
        s1_results = self.static_checker.check(test_cases)

        # S2: Leave-One-Out execution checking
        if enable_s2:
            try:
                s2_results = self.execution_checker.check(
                    task_description,
                    test_cases,
                )
            except Exception as exc:
                s2_results = {
                    "status": "error",
                    "error": str(exc),
                    "flags": [],
                }
        else:
            s2_results = {
                "status": "disabled",
                "flags": [],
            }

        # S3: Judge each assertion against the task description
        s3_results = []

        if enable_s3:
            for case in test_cases:
                try:
                    result = self.llm_judge.judge(
                        task_description=task_description,
                        test_case=case,
                    )

                    s3_results.append({
                        "function": case.function_name,
                        "line_number": case.line_number,
                        "expected_output": case.expected_output,
                        "verdict": result.get(
                            "verdict",
                            "UNCERTAIN",
                        ),
                        "is_misaligned": result.get(
                            "is_misaligned",
                            False,
                        ),
                        "reason": result.get("reason", ""),
                        "status": result.get(
                            "status",
                            "completed",
                        ),
                    })

                except Exception as exc:
                    s3_results.append({
                        "function": case.function_name,
                        "line_number": case.line_number,
                        "verdict": "UNCERTAIN",
                        "is_misaligned": False,
                        "status": "error",
                        "error": str(exc),
                    })

        # Final decision: S1 OR (S2 AND S3)
        decision_results = self.decision_engine.decide(
            test_cases=test_cases,
            s1_results=s1_results,
            s2_results=s2_results,
            s3_results=s3_results,
        )

        return {
            "status": "completed",
            "total_test_cases": len(test_cases),

            "S1": {
                "status": "completed",
                "contradictions": s1_results,
                "contradiction_count": len(s1_results),
            },

            "S2": s2_results,

            "S3": {
                "status": "completed" if enable_s3 else "disabled",
                "results": s3_results,
            },

            "decision": decision_results,

            "summary": {
                "S1_conflicts_detected": len(s1_results) > 0,

                "S2_conflicts_detected": (
                    s2_results.get("conflict_detected", False)
                    if isinstance(s2_results, dict)
                    else False
                ),

                "final_decision": decision_results.get(
                    "final_decision",
                    "UNKNOWN",
                ),
            },
        }
