
import ast
from dataclasses import dataclass
from typing import Any


@dataclass
class TestCase:
    __test__ = False
    function_name: str
    args: tuple
    kwargs: dict
    expected_output: Any
    line_number: int
    source: str


class TestParser:
    """
    Parses Python assert statements and extracts
    function inputs and expected outputs.
    """

    def parse(self, source_code: str) -> list[TestCase]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError as exc:
            raise ValueError(
                f"Invalid Python test file: {exc}"
            ) from exc

        test_cases = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.Assert):
                continue

            test_case = self._parse_assertion(
                node, source_code
            )

            if test_case is not None:
                test_cases.append(test_case)

        return sorted(
            test_cases,
            key=lambda case: case.line_number
        )

    def _parse_assertion(
        self,
        node: ast.Assert,
        source_code: str
    ) -> TestCase | None:

        expression = node.test

        if not isinstance(expression, ast.Compare):
            return None

        if len(expression.ops) != 1:
            return None

        if not isinstance(expression.ops[0], ast.Eq):
            return None

        if len(expression.comparators) != 1:
            return None

        left = expression.left
        right = expression.comparators[0]

        # Support both:
        # assert function(x) == expected
        # assert expected == function(x)

        if isinstance(left, ast.Call):
            call_node = left
            expected_node = right

        elif isinstance(right, ast.Call):
            call_node = right
            expected_node = left

        else:
            return None

        if not isinstance(call_node.func, ast.Name):
            return None

        if any(
            isinstance(arg, ast.Starred)
            for arg in call_node.args
        ):
            return None

        try:
            args = tuple(
                ast.literal_eval(arg)
                for arg in call_node.args
            )

            kwargs = {
                keyword.arg: ast.literal_eval(keyword.value)
                for keyword in call_node.keywords
                if keyword.arg is not None
            }

            expected_output = ast.literal_eval(
                expected_node
            )

        except (ValueError, TypeError, SyntaxError):
            return None

        return TestCase(
            function_name=call_node.func.id,
            args=args,
            kwargs=kwargs,
            expected_output=expected_output,
            line_number=node.lineno,
            source=ast.get_source_segment(
                source_code, node
            ) or ""
        )
