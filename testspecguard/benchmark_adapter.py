
from dataclasses import replace

from .parser import TestParser, TestCase


class BenchmarkAdapter:
    """Adapts Impossible-LiveCodeBench records to TestSpecGuard."""

    def __init__(self):
        self.parser = TestParser()

    def parse_record(self, record: dict) -> list[TestCase]:
        required = ["task_id", "prompt", "test", "entry_point"]

        for field in required:
            if field not in record or not record[field]:
                raise ValueError(
                    f"Missing or empty benchmark field: {field}"
                )

        entry_point = record["entry_point"]

        # Parse the benchmark's check(candidate) assertions.
        test_cases = self.parser.parse(record["test"])

        if not test_cases:
            raise ValueError(
                f"No supported assertions found in {record['task_id']}"
            )

        # Replace the placeholder name with the actual function name.
        adapted_cases = [
            replace(case, function_name=entry_point)
            for case in test_cases
        ]

        return adapted_cases
