
from testspecguard.parser import TestParser


def test_parse_basic_assertions():
    source = """
assert digit_sum(135) == 9
assert digit_sum(123) == 6
assert digit_sum(45) == 9
"""

    parser = TestParser()
    results = parser.parse(source)

    assert len(results) == 3

    assert results[0].function_name == "digit_sum"
    assert results[0].args == (135,)
    assert results[0].expected_output == 9
    assert results[0].line_number == 2


def test_parse_reverse_equality():
    source = """
assert 5 == add(2, 3)
"""

    parser = TestParser()
    results = parser.parse(source)

    assert len(results) == 1
    assert results[0].function_name == "add"
    assert results[0].args == (2, 3)
    assert results[0].expected_output == 5


def test_parse_keyword_arguments():
    source = """
assert power(base=2, exponent=3) == 8
"""

    parser = TestParser()
    results = parser.parse(source)

    assert len(results) == 1
    assert results[0].kwargs == {
        "base": 2,
        "exponent": 3
    }
    assert results[0].expected_output == 8


def test_ignore_unsupported_assertions():
    source = """
assert add(2, 3) != 6
assert 10 > 5
"""

    parser = TestParser()
    results = parser.parse(source)

    assert len(results) == 0


def test_invalid_python():
    source = "assert add(2, == 5"

    parser = TestParser()

    try:
        parser.parse(source)
        assert False, "Expected ValueError"
    except ValueError:
        pass
