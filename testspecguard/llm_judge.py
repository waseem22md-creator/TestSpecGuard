
import ast
import json
import re

import ollama

from .parser import TestCase


class LLMJudge:
    """
    S3: Independent semantic test specification judge.

    Evaluation order:
    1. Check exact documented input/output examples.
    2. Attempt supported deterministic calculations.
    3. Use the LLM for remaining cases.

    The expected test output is never included in the LLM prompt.
    Python performs the final comparison.
    """

    _NOT_FOUND = object()

    def __init__(
        self,
        model: str = "qwen2.5-coder:7b",
        debug: bool = False,
    ):
        self.model = model
        self.debug = debug

    @staticmethod
    def _values_equal(actual, expected):
        """Compare values while distinguishing bool from int."""

        if isinstance(actual, bool) or isinstance(expected, bool):
            return type(actual) is type(expected) and actual == expected

        if isinstance(actual, (int, float)) and isinstance(
            expected, (int, float)
        ):
            return actual == expected

        return type(actual) is type(expected) and actual == expected

    def _build_result(
        self,
        test_case: TestCase,
        computed_output,
        reason: str,
        method: str,
    ) -> dict:
        """Compare a computed result with the test expectation."""

        aligned = self._values_equal(
            computed_output,
            test_case.expected_output,
        )

        verdict = "ALIGNED" if aligned else "MISALIGNED"

        if self.debug:
            print(
                f"[S3 {method}] Line {test_case.line_number}: "
                f"computed={computed_output!r}, "
                f"expected={test_case.expected_output!r}, "
                f"verdict={verdict}"
            )

        return {
            "status": "completed",
            "verdict": verdict,
            "is_misaligned": not aligned,
            "computed_output": repr(computed_output),
            "expected_output": repr(test_case.expected_output),
            "reason": reason,
        }

    def _find_documented_example(
        self,
        task_description: str,
        test_case: TestCase,
    ):
        """
        Find an exact input/output example in the task description.

        Supports simple Python doctest examples.
        """

        lines = task_description.splitlines()

        for index, line in enumerate(lines):
            line = line.strip()

            if not line.startswith(">>>"):
                continue

            expression = line[3:].strip()

            try:
                tree = ast.parse(expression, mode="eval")
                call = tree.body

                if not isinstance(call, ast.Call):
                    continue

                if not isinstance(call.func, ast.Name):
                    continue

                if call.func.id != test_case.function_name:
                    continue

                args = tuple(
                    ast.literal_eval(argument)
                    for argument in call.args
                )

                kwargs = {}

                for keyword in call.keywords:
                    if keyword.arg is None:
                        raise ValueError(
                            "Unpacking keyword arguments is unsupported"
                        )

                    kwargs[keyword.arg] = ast.literal_eval(
                        keyword.value
                    )

                if args != test_case.args:
                    continue

                if kwargs != test_case.kwargs:
                    continue

                # The output should immediately follow the doctest.
                if index + 1 >= len(lines):
                    continue

                output_line = lines[index + 1].strip()

                if not output_line or output_line.startswith(
                    (">>>", "...")
                ):
                    continue

                documented_output = ast.literal_eval(output_line)

                if self.debug:
                    print(
                        f"[S3 DOCUMENTED] Found exact example: "
                        f"{test_case.function_name}{args}, "
                        f"output={documented_output!r}"
                    )

                return documented_output

            except (SyntaxError, ValueError, TypeError):
                continue

        return self._NOT_FOUND

    def _judge_documented_example(
        self,
        task_description: str,
        test_case: TestCase,
    ):
        """Judge a test using a matching documented example."""

        documented_output = self._find_documented_example(
            task_description,
            test_case,
        )

        if documented_output is self._NOT_FOUND:
            return None

        return self._build_result(
            test_case=test_case,
            computed_output=documented_output,
            reason=(
                "Matched an exact input/output example "
                "in the task description."
            ),
            method="DOCUMENTED",
        )

    @staticmethod
    def _extract_subarray_power_arguments(test_case: TestCase):
        """
        Extract n, k and the input array.

        Supports:
            function(n, k, array)
        and:
            function(n=n, k=k, a=array)
        """

        args = test_case.args
        kwargs = test_case.kwargs

        if len(args) >= 3:
            n, k, values = args[0], args[1], args[2]
        else:
            n = kwargs.get("n")
            k = kwargs.get("k")

            values = kwargs.get(
                "a",
                kwargs.get(
                    "arr",
                    kwargs.get("array", kwargs.get("nums")),
                ),
            )

        if not isinstance(n, int) or isinstance(n, bool):
            return None

        if not isinstance(k, int) or isinstance(k, bool):
            return None

        if not isinstance(values, (list, tuple)):
            return None

        if not all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in values
        ):
            return None

        if n != len(values):
            return None

        if n < 0 or k < 0:
            return None

        return n, k, values

    def _try_deterministic_calculation(
        self,
        task_description: str,
        test_case: TestCase,
    ):
        """
        Calculate sum of subarray sums raised to k.

        Supported specification:
            Sum((sum of each contiguous subarray) ** k) modulo M.

        This path is used only when the task description clearly
        identifies the operation and explicitly provides a modulus.

        The implementation is O(n^2), so it is restricted to
        relatively small inputs.
        """

        description = task_description.lower()
        function_name = test_case.function_name.lower()

        is_subarray_power_problem = (
            "sum_of_subarray_powers" in function_name
            or (
                "subarray" in description
                and "sum" in description
                and "power" in description
            )
        )

        if not is_subarray_power_problem:
            return None

        arguments = self._extract_subarray_power_arguments(test_case)

        if arguments is None:
            return None

        n, k, values = arguments

        # Avoid expensive quadratic calculations on large inputs.
        if n > 1000:
            return None

        # Require an explicitly stated modulus.
        modulus_match = re.search(
            r"\bmod(?:ulo)?\s*(?:of\s*)?([0-9][0-9,]*)",
            description,
            re.IGNORECASE,
        )

        if modulus_match is None:
            return None

        modulus = int(modulus_match.group(1).replace(",", ""))

        if modulus <= 0:
            return None

        # Compute every contiguous subarray sum exactly once.
        total = 0

        for left in range(n):
            subarray_sum = 0

            for right in range(left, n):
                subarray_sum += values[right]

                total = (
                    total + pow(subarray_sum, k, modulus)
                ) % modulus

        if self.debug:
            print(
                f"[S3 DETERMINISTIC] Line {test_case.line_number}: "
                f"n={n}, k={k}, modulus={modulus}, "
                f"computed={total}"
            )

        return total

    def judge(
        self,
        task_description: str,
        test_case: TestCase,
    ) -> dict:

        # --------------------------------------------------
        # STEP 1: Check documented examples.
        # --------------------------------------------------

        documented_result = self._judge_documented_example(
            task_description,
            test_case,
        )

        if documented_result is not None:
            return documented_result

        # --------------------------------------------------
        # STEP 2: Attempt deterministic calculation.
        # --------------------------------------------------

        try:
            deterministic_output = self._try_deterministic_calculation(
                task_description,
                test_case,
            )

            if deterministic_output is not None:
                return self._build_result(
                    test_case=test_case,
                    computed_output=deterministic_output,
                    reason=(
                        "Calculated directly from the task specification "
                        "by enumerating every contiguous subarray and "
                        "applying the specified modulus."
                    ),
                    method="DETERMINISTIC",
                )

        except Exception as exc:
            if self.debug:
                print(
                    f"[S3 DETERMINISTIC] Line "
                    f"{test_case.line_number}: {exc}"
                )

        # --------------------------------------------------
        # STEP 3: Use the LLM when no deterministic method applies.
        # --------------------------------------------------

        prompt = f"""
You are an independent Python specification evaluator.

Your task is to calculate the exact return value of a function
using ONLY:
1. The task description.
2. The function name.
3. The positional arguments.
4. The keyword arguments.

STRICT INDEPENDENCE:
- The expected test output is not provided to you.
- Never guess or estimate the answer.
- Follow the task specification exactly.
- Do not invent missing requirements.
- If the specification is ambiguous or insufficient, return
  calculable=false.

CALCULATION PROCEDURE:

1. Identify the precise mathematical or algorithmic definition.
2. Identify relevant constraints, boundary conditions and modulo rules.
3. Choose a calculation method consistent with the specification.
4. Work through the supplied input.
5. Check intermediate calculations for arithmetic errors.
6. Verify the final result's type and representation.
7. Return calculable=true only when an exact result is established.

NUMERICAL AND ALGORITHMIC PROBLEMS:

- Do not skip required operations.
- Do not use approximate calculations.
- Pay attention to powers, summations, indexing and modular arithmetic.
- For modular arithmetic, apply the specified modulus correctly.
- For sums over ranges or subarrays, include every required range
  exactly once.
- Check boundary cases against the task definition where possible.
- Do not treat an example as a replacement for the general definition.

TASK DESCRIPTION:

{task_description}

FUNCTION NAME:

{test_case.function_name}

POSITIONAL ARGUMENTS:

{repr(test_case.args)}

KEYWORD ARGUMENTS:

{repr(test_case.kwargs)}

Return ONLY valid JSON in this format:

{{
    "calculable": true,
    "computed_output_repr": "123",
    "reason": "Brief explanation of the calculation method."
}}

If you cannot establish the exact result, return:

{{
    "calculable": false,
    "computed_output_repr": "",
    "reason": "The exact result could not be established reliably."
}}
"""

        try:
            response = ollama.chat(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                format="json",
                options={
                    "temperature": 0,
                },
            )

            response_content = response["message"]["content"]
            result = json.loads(response_content)

            if not isinstance(result, dict):
                raise ValueError("LLM response must be a JSON object")

            # Validate the calculable field.
            calculable = result.get("calculable")

            if not isinstance(calculable, bool):
                raise ValueError("Invalid calculable field")

            # Validate the reason field.
            reason = result.get("reason", "")

            if not isinstance(reason, str):
                raise ValueError("Invalid reason field")

            computed_repr = result.get("computed_output_repr")

            if not isinstance(computed_repr, str):
                raise ValueError(
                    "Invalid computed_output_repr field"
                )

            # --------------------------------------------------
            # STEP 4: Handle uncertain results.
            # --------------------------------------------------

            if not calculable:
                if self.debug:
                    print(
                        f"[S3 UNCERTAIN] Line "
                        f"{test_case.line_number}: {reason}"
                    )

                return {
                    "status": "completed",
                    "verdict": "UNCERTAIN",
                    "is_misaligned": False,
                    "computed_output": None,
                    "expected_output": repr(
                        test_case.expected_output
                    ),
                    "reason": reason or (
                        "Insufficient task information."
                    ),
                }

            # --------------------------------------------------
            # STEP 5: Safely parse the calculated output.
            # --------------------------------------------------

            try:
                computed_output = ast.literal_eval(computed_repr)

            except (ValueError, SyntaxError) as exc:
                raise ValueError(
                    f"Invalid Python literal returned by LLM: {exc}"
                )

            # --------------------------------------------------
            # STEP 6: Python determines the final verdict.
            # --------------------------------------------------

            return self._build_result(
                test_case=test_case,
                computed_output=computed_output,
                reason=reason,
                method="LLM",
            )

        except Exception as exc:
            if self.debug:
                print(
                    f"[S3 ERROR] Line {test_case.line_number}: {exc}"
                )

            return {
                "status": "invalid_response",
                "verdict": "UNCERTAIN",
                "is_misaligned": False,
                "computed_output": None,
                "expected_output": repr(
                    test_case.expected_output
                ),
                "reason": f"LLM output validation failed: {exc}",
            }
