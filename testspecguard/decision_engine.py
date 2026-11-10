

from typing import Any


class DecisionEngine:
    """
    Combines S1, S2 and S3 signals to produce
    the final TestSpecGuard decision.

    F_i = S1_i OR (S2_i AND S3_i)
    """

    def decide(
        self,
        test_cases: list,
        s1_results: list[dict[str, Any]],
        s2_results: dict[str, Any],
        s3_results: list[dict[str, Any]],
    ) -> dict[str, Any]:

        # Collect S1 contradictions by line number
        s1_lines = set()

        for contradiction in s1_results:
            s1_lines.update(
                contradiction.get("line_numbers", [])
            )

        # Collect S2 conflicts by line number
        s2_lines = set()

        if isinstance(s2_results, dict):
            for flag in s2_results.get("flags", []):
                if flag.get("is_conflict"):
                    line = flag.get("line_number")
                    if line is not None:
                        s2_lines.add(line)

        # Collect S3 semantic misalignments by line number
        s3_lines = set()

        for result in s3_results:
            if (
                result.get("status") == "completed"
                and result.get("is_misaligned") is True
            ):
                line = result.get("line_number")
                if line is not None:
                    s3_lines.add(line)

        # Evaluate every parsed test case
        decisions = []

        for case in test_cases:
            line = case.line_number

            s1 = line in s1_lines
            s2 = line in s2_lines
            s3 = line in s3_lines

            # Final decision rule
            conflict = s1 or (s2 and s3)

            decisions.append({
                "line_number": line,
                "function": case.function_name,
                "S1": s1,
                "S2": s2,
                "S3": s3,
                "conflict": conflict,
                "verdict": (
                    "CONFLICT"
                    if conflict
                    else "NO_CONFLICT"
                ),
            })

        conflict_detected = any(
            item["conflict"] for item in decisions
        )

        return {
            "status": "completed",
            "final_decision": (
                "BLOCK"
                if conflict_detected
                else "ALLOW"
            ),
            "conflict_detected": conflict_detected,
            "total_evaluated": len(decisions),
            "decisions": decisions,
        }
