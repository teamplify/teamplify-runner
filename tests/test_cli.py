import pytest

from teamplify_runner.cli import _root_url


@pytest.mark.parametrize(
    'use_ssl,port,expected',
    [
        ('no', '80', 'http://example.com'),
        ('no', '8080', 'http://example.com:8080'),
        ('builtin', '80', 'https://example.com'),
        ('external', '8000', 'https://example.com'),
        ('yes', '80', 'https://example.com'),
        ('true', '80', 'https://example.com'),
    ],
)
def test_root_url(use_ssl, port, expected):
    env = {'WEB_HOST': 'example.com', 'WEB_PORT': port, 'WEB_USE_SSL': use_ssl}
    assert _root_url(env) == expected
