
from testspecguard.parser import TestParser
from testspecguard.static_checker import (
    StaticContradictionChecker
)


def test_detect_contradictory_outputs():

    source = """
assert digit_sum(135) == 9
assert digit_sum(135) == 7
"""

    cases = TestParser().parse(source)

    checker = StaticContradictionChecker()
    results = checker.check(cases)

    assert len(results) == 1
    assert results[0]["signal"] == "S1"
    assert results[0]["status"] == "CONTRADICTION"
    assert results[0]["line_numbers"] == [2, 3]


def test_no_contradictions():

    source = """
assert digit_sum(135) == 9
assert digit_sum(123) == 6
assert digit_sum(45) == 9
"""

    cases = TestParser().parse(source)

    checker = StaticContradictionChecker()
    results = checker.check(cases)

    assert len(results) == 0


def test_same_input_same_output():

    source = """
assert add(2, 3) == 5
assert add(2, 3) == 5
"""

    cases = TestParser().parse(source)

    checker = StaticContradictionChecker()
    results = checker.check(cases)

    assert len(results) == 0


def test_different_functions_are_not_conflicts():

    source = """
assert add(2, 3) == 5
assert multiply(2, 3) == 6
"""

    cases = TestParser().parse(source)

    checker = StaticContradictionChecker()
    results = checker.check(cases)

    assert len(results) == 0


def test_detect_list_output_conflict():

    source = """
assert get_values(1) == [1, 2]
assert get_values(1) == [1, 3]
"""

    cases = TestParser().parse(source)

    checker = StaticContradictionChecker()
    results = checker.check(cases)

    assert len(results) == 1
