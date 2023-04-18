import os

from pytest import fail

from teamplify_runner.configurator import ConfigurationError, Configurator


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def test_default_configuration_is_valid_except_product_key():
    expected_errors = [
        '[main] product_key: Product key is missing',
    ]
    configuration = Configurator().dumps()
    assert configuration.startswith('[')
    try:
        Configurator().loads(configuration).validate()
    except ConfigurationError as e:
        assert e.messages == expected_errors
    else:
        fail('Default configuration must fail on product key')


def test_valid_configurations():
    valid_config = 'conf_sample_valid.ini'
    try:
        c = Configurator().load(os.path.join(BASE_DIR, valid_config)).validate()
    except ConfigurationError:
        fail('Configuration {0} is expected to be valid'.format(valid_config))
    else:
        # it must have the default options, not mentioned in the source config
        env = c.env()
        assert 'DB_PORT' in env
        assert 'CRYPTO_SIGNING_KEY' in env


def test_deeply_invalid_configuration():
    invalid_config = os.path.join(BASE_DIR, 'conf_sample_invalid.ini')
    expected_errors = [
        '[main] product_key: Invalid product key: 42',
        '[web] port: Must be an integer. You provided: gav',
        '[web] use_ssl: Must be one of the following: no, builtin, external. '
        'You provided: not sure',
        "[db] host: Can't resolve hostname: -1 # comment after value",
        '[db] port: Must be less or equal to 65535. You provided: 70000',
        '[db] backup_mount: Must be a directory: not a valid path',
        '[db] unknown_key: Unknown option',
        '[email] address_from: Invalid email: not even a email',
        '[email] smtp_protocol: Must be one of the following: plain, ssl, tls. '
        'You provided: tcp',
        'Unknown section: [unknown_section]',
    ]
    try:
        Configurator().load(invalid_config).validate()
    except ConfigurationError as e:
        assert e.messages == expected_errors
    else:
        fail('Configuration {0} must be invalid'.format(invalid_config))
