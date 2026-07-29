import pytest

from teamplify_runner.version_checker import is_update_available


@pytest.mark.parametrize(
    'curr,new,expected',
    [
        ('0.15.0', '0.15.0', False),
        ('0.15.0', '0.16.0', True),
        ('0.16.0', '0.15.0', False),
        ('0.15', '0.15.1', True),
        ('0.15.1', '0.15', False),
        ('0.99.99', '1.0.0', True),
    ],
)
def test_is_update_available(curr, new, expected):
    assert is_update_available(curr, new) is expected
