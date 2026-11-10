
from collections import defaultdict
from typing import Any


class StaticContradictionChecker:
    """
    S1: Detects identical function inputs
    associated with different expected outputs.
    """

    def check(self, test_cases: list) -> list[dict[str, Any]]:
        grouped = defaultdict(list)

        for case in test_cases:
            input_key = (
                case.function_name,
                self._make_hashable(case.args),
                self._make_hashable(case.kwargs),
            )
            grouped[input_key].append(case)

        contradictions = []

        for cases in grouped.values():
            expected_outputs = {
                self._make_hashable(case.expected_output)
                for case in cases
            }

            if len(expected_outputs) > 1:
                first_case = cases[0]

                contradictions.append({
                    "function": first_case.function_name,
                    "inputs": {
                        "args": first_case.args,
                        "kwargs": first_case.kwargs,
                    },
                    "expected_outputs": [
                        case.expected_output for case in cases
                    ],
                    "line_numbers": [
                        case.line_number for case in cases
                    ],
                    "signal": "S1",
                    "status": "CONTRADICTION",
                })

        return contradictions

    def _make_hashable(self, value: Any) -> Any:
        """Convert nested containers into hashable values."""

        if isinstance(value, dict):
            items = [
                (
                    self._make_hashable(key),
                    self._make_hashable(val),
                )
                for key, val in value.items()
            ]
            return tuple(sorted(items, key=repr))

        if isinstance(value, (list, tuple)):
            return tuple(
                self._make_hashable(item) for item in value
            )

        if isinstance(value, set):
            return frozenset(
                self._make_hashable(item) for item in value
            )

        try:
            hash(value)
            return value
        except TypeError:
            return repr(value)
