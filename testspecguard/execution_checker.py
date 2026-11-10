
"""
S2: Leave-One-Out Execution Checker

Generates candidate Python solutions using Ollama and checks
whether candidates passing all non-excluded tests fail an
excluded test.

IMPORTANT:
The subprocess runner provides timeout and temporary-directory
isolation, but is NOT a security sandbox.
"""

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

from pathlib import Path
from typing import Any

import ollama

from .parser import TestCase


class ExecutionChecker:

    def __init__(
        self,
        model: str = "qwen2.5-coder:3b",
        num_candidates: int = 5,
        min_candidates: int = 2,
        timeout: int = 5,
    ):

        if num_candidates < 1:
            raise ValueError("num_candidates must be at least 1")

        if min_candidates < 1:
            raise ValueError("min_candidates must be at least 1")

        if min_candidates > num_candidates:
            raise ValueError(
                "min_candidates cannot exceed num_candidates"
            )

        if timeout < 1:
            raise ValueError("timeout must be at least 1 second")

        self.model = model
        self.num_candidates = num_candidates
        self.min_candidates = min_candidates
        self.timeout = timeout

        # Persistent cache for candidate generation.
        self.cache_path = (
            Path(__file__).resolve().parent.parent
            / "evaluation"
            / "cache"
            / "candidate_cache.json"
        )
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------
    # 1. Extract Python code from an LLM response
    # --------------------------------------------------

    @staticmethod
    def _extract_code(response: str) -> str:

        blocks = re.findall(
            r"```(?:python)?\s*(.*?)```",
            response,
            flags=re.IGNORECASE | re.DOTALL,
        )

        if blocks:
            return blocks[0].strip()

        lines = response.splitlines()

        for index, line in enumerate(lines):
            if re.match(
                r"^\s*(def |async def |class |import |from )",
                line,
            ):
                return "\n".join(lines[index:]).strip()

        return response.strip()

    # --------------------------------------------------
    # 2. Extract the required function name
    # --------------------------------------------------

    @classmethod
    def _extract_entry_point(
        cls,
        task_description: str,
    ) -> str | None:
        """
        Extract the function name from the task description.
        """

        if not task_description:
            return None

        try:
            tree = ast.parse(task_description)

            for node in tree.body:
                if isinstance(
                    node,
                    (ast.FunctionDef, ast.AsyncFunctionDef),
                ):
                    return node.name

        except SyntaxError:
            pass

        match = re.search(
            r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(",
            task_description,
            flags=re.MULTILINE,
        )

        if match:
            return match.group(1)

        return None

    # --------------------------------------------------
    # 3. Persistent candidate-cache helpers
    # --------------------------------------------------

    def _candidate_cache_key(self, task_description: str) -> str:
        """Build a stable key for one task and generation configuration."""

        cache_identity = {
            "cache_version": "candidate-generation-v1",
            "task_description": task_description,
            "model": self.model,
            "num_candidates": self.num_candidates,
            "temperature_schedule": [
                0.7 + (index * 0.05)
                for index in range(self.num_candidates)
            ],
        }

        encoded = json.dumps(
            cache_identity,
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")

        return hashlib.sha256(encoded).hexdigest()

    def _load_candidate_cache(self) -> dict:
        """Load cached candidates; tolerate a missing or invalid cache."""

        if not self.cache_path.exists():
            return {}

        try:
            with self.cache_path.open("r", encoding="utf-8") as file:
                cached = json.load(file)

            return cached if isinstance(cached, dict) else {}

        except (OSError, json.JSONDecodeError) as exc:
            print(f"[S2 CACHE] Could not read cache; regenerating: {exc}")
            return {}

    def _save_candidate_cache(self, cache: dict) -> None:
        """Atomically save the candidate cache to disk."""

        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.cache_path.with_suffix(".json.tmp")

        with temporary_path.open("w", encoding="utf-8") as file:
            json.dump(cache, file, indent=2, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())

        temporary_path.replace(self.cache_path)

    # --------------------------------------------------
    # 4. Generate candidate solutions using Ollama
    # --------------------------------------------------

    def generate_candidates(
        self,
        task_description: str,
    ) -> list[str]:

        cache = self._load_candidate_cache()
        cache_key = self._candidate_cache_key(task_description)
        cached_entry = cache.get(cache_key)

        if isinstance(cached_entry, dict):

            cached_candidates = cached_entry.get("candidates")

            if isinstance(cached_candidates, list):

                valid_cached_candidates = []

                for code in cached_candidates:

                    if not isinstance(code, str) or not code.strip():
                        continue

                    try:
                        ast.parse(code)
                    except SyntaxError:
                        continue

                    if code not in valid_cached_candidates:
                        valid_cached_candidates.append(code)

                print(
                    f"[S2 CACHE] Reusing "
                    f"{len(valid_cached_candidates)} cached candidates."
                )

                return valid_cached_candidates

        candidates = []

        prompt = f"""
You are an expert competitive programming engineer.

Solve the following programming problem using a correct,
efficient algorithm.

PROBLEM:
{task_description}

REQUIREMENTS:

1. Read and understand the complete problem statement.

2. Identify the maximum input constraints before selecting
   an algorithm.

3. Estimate the time complexity of a straightforward
   brute-force solution.

4. Reject brute force if it cannot handle the maximum
   constraints efficiently.

5. Select an appropriate algorithm based on the problem.
   Consider dynamic programming, digit DP, greedy algorithms,
   binary search, graph algorithms and mathematical methods.

6. Preserve every condition in the problem statement,
   including divisibility, counting and range restrictions.

7. Preserve original input values when they are needed later.

8. Handle boundary conditions, leading zeros and special
   cases where applicable.

9. Verify that the time and space complexity are suitable
   for the maximum constraints.

10. Check the implementation for logical errors, missing
    conditions, incorrect function signatures and missing
    imports.

11. Implement the exact required function name and signature.

12. Do not generate unit tests.
13. Do not include example usage or print statements.
14. Do not assume access to hidden test cases.
15. Do not use unnecessary external packages.

Return only complete, executable Python source code.
Do not include explanations, Markdown or code fences.
"""

        for candidate_number in range(self.num_candidates):

            try:

                response = ollama.chat(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are an expert Python competitive "
                                "programmer. Produce correct, efficient, "
                                "executable Python code that follows the "
                                "problem constraints. Return code only."
                            ),
                        },
                        {
                            "role": "user",
                            "content": prompt,
                        },
                    ],
                    options={
                        "temperature": 0.7 + (candidate_number * 0.05),
                    },
                )

                raw_code = response["message"]["content"]

                if not raw_code or not raw_code.strip():
                    print(
                        f"Candidate {candidate_number + 1}: "
                        "Empty response from model."
                    )
                    continue

                code = self._extract_code(raw_code)

                if not code or not code.strip():
                    print(
                        f"Candidate {candidate_number + 1}: "
                        "No usable Python code extracted."
                    )
                    continue

                try:
                    ast.parse(code)

                except SyntaxError as exc:
                    print(
                        f"Candidate {candidate_number + 1}: "
                        f"Invalid Python syntax: {exc}"
                    )
                    continue

                if code not in candidates:

                    candidates.append(code)

                    print(
                        f"Candidate {candidate_number + 1}: "
                        "Generated successfully."
                    )

                else:

                    print(
                        f"Candidate {candidate_number + 1}: "
                        "Duplicate implementation skipped."
                    )

            except Exception as exc:

                print(
                    f"Candidate {candidate_number + 1} "
                    f"generation failed: {exc}"
                )

        print(
            f"\nCandidate generation complete: "
            f"{len(candidates)}/{self.num_candidates} "
            "unique candidates."
        )

        # Save the same candidate set for the matched task versions.
        cache[cache_key] = {
            "model": self.model,
            "num_candidates_requested": self.num_candidates,
            "generated_candidates": len(candidates),
            "candidates": candidates,
        }

        self._save_candidate_cache(cache)

        print(f"[S2 CACHE] Saved candidates to: {self.cache_path}")

        return candidates

    # --------------------------------------------------
    # 5. Execute one candidate against all test cases
    # --------------------------------------------------

    def _execute_candidate(
        self,
        candidate: str,
        test_cases: list[TestCase],
        entry_point: str | None = None,
    ) -> dict[str, Any]:

        test_data = []

        for test in test_cases:

            function_name = test.function_name

            if function_name == "candidate" and entry_point:
                function_name = entry_point

            test_data.append(
                {
                    "function_name": function_name,
                    "args": test.args,
                    "kwargs": test.kwargs,
                    "expected": test.expected_output,
                }
            )

        harness = f'''
import json

CANDIDATE = {candidate!r}
TESTS = {test_data!r}

namespace = {{}}

try:
    exec(CANDIDATE, namespace)

    for test in TESTS:
        if not callable(namespace.get(test["function_name"])):
            raise ValueError(
                "Required function not found: "
                + test["function_name"]
            )

except BaseException as exc:
    print("__TESTSPECGUARD__" + json.dumps({{
        "valid": False,
        "error": str(exc)
    }}))
    raise SystemExit(0)

results = []

for test in TESTS:
    try:
        function = namespace[test["function_name"]]

        actual = function(
            *test["args"],
            **test["kwargs"]
        )

        results.append(actual == test["expected"])

    except BaseException:
        results.append(False)

print("__TESTSPECGUARD__" + json.dumps({{
    "valid": True,
    "results": results
}}))
'''

        try:

            with tempfile.TemporaryDirectory() as temp_dir:

                script_path = Path(temp_dir) / "candidate.py"

                script_path.write_text(
                    harness,
                    encoding="utf-8",
                )

                safe_env = {
                    "PATH": os.environ.get("PATH", ""),
                    "HOME": temp_dir,
                    "TMPDIR": temp_dir,
                    "PYTHONIOENCODING": "utf-8",
                }

                completed = subprocess.run(
                    [
                        sys.executable,
                        "-I",
                        str(script_path),
                    ],
                    cwd=temp_dir,
                    env=safe_env,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    check=False,
                )

                marker = "__TESTSPECGUARD__"

                for line in reversed(
                    completed.stdout.splitlines()
                ):

                    if line.startswith(marker):

                        return json.loads(
                            line[len(marker):]
                        )

                return {
                    "valid": False,
                    "error": (
                        completed.stderr[-1000:]
                        or completed.stdout[-1000:]
                        or (
                            "Candidate execution failed "
                            f"(exit code {completed.returncode})"
                        )
                    ),
                }

        except subprocess.TimeoutExpired:

            return {
                "valid": False,
                "error": (
                    f"Execution timeout after {self.timeout} seconds"
                ),
            }

        except Exception as exc:

            return {
                "valid": False,
                "error": str(exc),
            }

    # --------------------------------------------------
    # 6. Leave-One-Out verification
    # --------------------------------------------------

    def check(
        self,
        task_description: str,
        test_cases: list[TestCase],
    ) -> dict[str, Any]:

        if not task_description.strip():
            raise ValueError("Task description cannot be empty")

        if not test_cases:
            return {
                "status": "no_test_cases",
                "flags": [],
                "conflict_detected": False,
            }

        entry_point = self._extract_entry_point(
            task_description
        )

        if entry_point:
            print(f"[S2] Required entry point: {entry_point}")

        else:
            print(
                "[S2] No entry point found in task description. "
                "Using parsed test function names."
            )

        # Candidate generation is cached by task description and
        # generation configuration. Test execution is NOT cached.
        candidates = self.generate_candidates(
            task_description
        )

        candidate_results = []
        candidate_diagnostics = []

        # Execute every candidate independently against this version's
        # complete test suite.
        for candidate_number, candidate in enumerate(
            candidates,
            start=1,
        ):

            if entry_point:
                result = self._execute_candidate(
                    candidate,
                    test_cases,
                    entry_point=entry_point,
                )

            else:
                result = self._execute_candidate(
                    candidate,
                    test_cases,
                )

            if result.get("valid"):

                outcomes = result.get("results", [])

                if (
                    isinstance(outcomes, list)
                    and len(outcomes) == len(test_cases)
                    and all(isinstance(value, bool) for value in outcomes)
                ):

                    candidate_results.append(outcomes)

                    passed = sum(outcomes)
                    failed = len(outcomes) - passed

                    failed_lines = [
                        test_cases[index].line_number
                        for index, value in enumerate(outcomes)
                        if not value
                    ]

                    diagnostic = {
                        "candidate": candidate_number,
                        "status": "valid",
                        "passed_tests": passed,
                        "failed_tests": failed,
                        "failed_line_numbers": failed_lines,
                    }

                    candidate_diagnostics.append(diagnostic)

                    print(
                        f"[S2] Candidate {candidate_number}: "
                        f"{passed}/{len(test_cases)} tests passed; "
                        f"failed lines={failed_lines}"
                    )

                else:

                    diagnostic = {
                        "candidate": candidate_number,
                        "status": "invalid",
                        "error": (
                            "Incorrect or invalid test outcomes returned"
                        ),
                    }

                    candidate_diagnostics.append(diagnostic)

                    print(
                        f"[S2] Candidate {candidate_number}: "
                        "Invalid test outcomes."
                    )

            else:

                error = result.get(
                    "error",
                    "Unknown execution error",
                )

                diagnostic = {
                    "candidate": candidate_number,
                    "status": "invalid",
                    "error": error,
                }

                candidate_diagnostics.append(diagnostic)

                print(
                    f"[S2] Candidate {candidate_number} failed: "
                    f"{error}"
                )

        valid_count = len(candidate_results)

        flags = []

        # Leave-one-out verification: exclude one test at a time.
        for excluded_index, excluded_test in enumerate(test_cases):

            eligible_count = 0
            failing_count = 0

            for outcomes in candidate_results:

                passes_remaining = all(
                    outcomes[index]
                    for index in range(len(test_cases))
                    if index != excluded_index
                )

                if passes_remaining:

                    eligible_count += 1

                    if not outcomes[excluded_index]:
                        failing_count += 1

            # Preserve the original S2 condition:
            # eligible_count >= m AND every eligible candidate fails
            # the excluded test.
            is_conflict = (
                eligible_count >= self.min_candidates
                and failing_count == eligible_count
            )

            flags.append(
                {
                    "line_number": excluded_test.line_number,
                    "source": excluded_test.source,
                    "eligible_candidates": eligible_count,
                    "failing_candidates": failing_count,
                    "required_candidates": self.min_candidates,
                    "insufficient_candidates": (
                        eligible_count < self.min_candidates
                    ),
                    "is_conflict": is_conflict,
                }
            )

        return {
            "status": "completed",
            "generated_candidates": len(candidates),
            "valid_candidates": valid_count,
            "required_candidates": self.min_candidates,
            "candidate_diagnostics": candidate_diagnostics,
            "flags": flags,
            "conflict_detected": any(
                item["is_conflict"]
                for item in flags
            ),
        }
