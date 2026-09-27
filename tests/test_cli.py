import pytest

from teamplify_runner.cli import _root_url


@pytest.mark.parametrize(
    'use_ssl,port,ssl_port,expected',
    [
        ('no', '80', '443', 'http://example.com'),
        ('no', '8080', '8443', 'http://example.com:8080'),
        ('builtin', '80', '443', 'https://example.com'),
        ('builtin', '8080', '8443', 'https://example.com:8443'),
        ('external', '8000', '443', 'https://example.com'),
        ('external', '8000', '8443', 'https://example.com'),
        ('yes', '80', '443', 'https://example.com'),
        ('true', '80', '8443', 'https://example.com:8443'),
    ],
)
def test_root_url(use_ssl, port, ssl_port, expected):
    env = {
        'WEB_HOST': 'example.com',
        'WEB_PORT': port,
        'WEB_SSL_PORT': ssl_port,
        'WEB_USE_SSL': use_ssl,
    }
    assert _root_url(env) == expected
