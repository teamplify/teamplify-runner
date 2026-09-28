import os
import re

import pytest

from teamplify_runner import acme_dns
from teamplify_runner.configurator import ConfigurationError, Configurator


PRODUCT_KEY = 'svr_Q5Luvv4yZbhbdale-kzbToeKyVsthN5yx35Hh'

# RFC 2606 reserves .invalid, so this name never resolves, with or without
# network access. Conversely, localhost resolves even without it. Tests that
# reach validate_hostname() must stick to these two.
UNRESOLVABLE_HOST = 'no-such-host.invalid'

skip_if_root = pytest.mark.skipif(os.geteuid() == 0, reason='root ignores file permissions')


@pytest.fixture(autouse=True)
def no_config_on_this_machine(monkeypatch):
    """Keep a configuration file installed on this machine out of the tests."""
    monkeypatch.setattr(Configurator, 'default_config_locations', [])


@pytest.fixture
def acme_credentials(tmp_path):
    """A DNS provider credentials file that passes validation."""
    credentials = tmp_path / 'acme-dns.yml'
    credentials.write_text('DNS_API: dns_cf\nCF_Token: secret\n')
    return str(credentials)


@pytest.fixture
def certs_dir(tmp_path):
    """A directory with a certificate pair for the `localhost` host."""
    certs = tmp_path / 'certs'
    certs.mkdir()
    (certs / 'localhost.crt').write_text('cert')
    (certs / 'localhost.key').write_text('key')
    return str(certs)


@pytest.fixture
def ssl_setups(certs_dir, acme_credentials):
    """The `[web]` options of every way to set up SSL, by name."""
    return {
        'no ssl': {'use_ssl': 'no'},
        'external ssl': {'use_ssl': 'external'},
        'own certificates': {'use_ssl': 'builtin', 'ssl_certs': certs_dir, 'host': 'localhost'},
        'http-01': {'use_ssl': 'builtin', 'acme_challenge': 'http-01', 'host': 'example.com'},
        'dns-01': {
            'use_ssl': 'builtin',
            'acme_challenge': 'dns-01',
            'acme_dns_api_config': acme_credentials,
            'host': 'example.com',
        },
        'acme-dns': {'use_ssl': 'builtin', 'acme_challenge': 'acme-dns', 'host': 'example.com'},
    }


def config(**sections):
    """
    Build a Configurator from the given sections, for example
    config(web={'host': 'localhost'}). Options not mentioned keep their
    defaults.
    """
    lines = []
    for section, options in sections.items():
        lines.append('[{0}]'.format(section))
        lines += ['{0} = {1}'.format(name, value) for name, value in options.items()]
    return Configurator().loads('\n'.join(lines))


def check(section, option, value, **other_options):
    """
    Validate a single option in isolation, against a configuration where the
    other options of the same section are set to `other_options`. Returns None
    when the value is valid, raises ConfigurationError when it is not.
    """
    options = dict(other_options, **{option: value})
    return config(**{section: options}).validate_option(section, option, str(value))


def error(section, option, value, **other_options):
    """The message that `check` raises for an invalid value."""
    with pytest.raises(ConfigurationError) as raised:
        check(section, option, value, **other_options)
    return str(raised.value)


# [main]


def test_product_key_accepts_a_well_formed_key():
    assert check('main', 'product_key', PRODUCT_KEY) is None


@pytest.mark.parametrize(
    'value,message',
    [
        ('', 'Product key is missing'),
        ('42', 'Invalid product key: 42'),
    ],
)
def test_product_key_rejects_an_invalid_key(value, message):
    assert error('main', 'product_key', value) == message


@pytest.mark.parametrize('value', ['stable', 'latest'])
def test_update_channel_accepts_known_channels(value):
    assert check('main', 'update_channel', value) is None


def test_update_channel_rejects_an_unknown_channel():
    assert error('main', 'update_channel', 'nightly') == (
        'Must be one of the following: stable, latest. You provided: nightly'
    )


@pytest.mark.parametrize('value', ['yes', 'no'])
def test_send_crash_reports_accepts_a_boolean(value):
    assert check('main', 'send_crash_reports', value) is None


def test_send_crash_reports_rejects_anything_else():
    assert 'Must be yes or no' in error('main', 'send_crash_reports', 'sometimes')


# [web] host


def test_host_accepts_a_resolvable_name():
    assert check('web', 'host', 'localhost') is None


@pytest.mark.parametrize(
    'value',
    [
        pytest.param(UNRESOLVABLE_HOST, id='unresolvable'),
        # ConfigParser is created without inline_comment_prefixes, so everything
        # after the value belongs to it
        pytest.param('-1 # comment after value', id='inline comment'),
    ],
)
def test_host_must_resolve(value):
    assert error('web', 'host', value) == "Can't resolve hostname: {0}".format(value)


# [web] port and ssl_port


@pytest.mark.parametrize('option', ['port', 'ssl_port'])
def test_ports_accept_a_valid_port_number(option):
    assert check('web', option, 8080) is None


@pytest.mark.parametrize(
    'value,message',
    [
        ('gav', 'Must be an integer. You provided: gav'),
        (70000, 'Must be less or equal to 65535. You provided: 70000'),
    ],
)
@pytest.mark.parametrize('option', ['port', 'ssl_port'])
def test_ports_reject_an_invalid_port_number(option, value, message):
    assert error('web', option, value) == message


@pytest.mark.parametrize('option,other', [('port', 'ssl_port'), ('ssl_port', 'port')])
def test_the_two_ports_must_differ(ssl_setups, option, other):
    # nginx cannot listen on one port both with and without TLS
    other_options = dict(ssl_setups['own certificates'], **{other: 8080})
    assert error('web', option, 8080, **other_options) == (
        'The web port and the ssl port must be different. You provided: 8080'
    )


@pytest.mark.parametrize('option,other', [('port', 'ssl_port'), ('ssl_port', 'port')])
@pytest.mark.parametrize('setup', ['no ssl', 'external ssl'])
def test_the_two_ports_may_coincide_without_builtin_ssl(ssl_setups, setup, option, other):
    # nginx only serves the web port here, and the ssl port merely says which
    # one the URLs of the installation carry
    other_options = dict(ssl_setups[setup], **{other: 8080})
    assert check('web', option, 8080, **other_options) is None


@pytest.mark.parametrize('option,value', [('port', 80), ('ssl_port', 443)])
def test_the_default_ports_differ(option, value):
    assert check('web', option, value) is None


@pytest.mark.parametrize(
    'option,value,message',
    [
        (
            'port',
            8080,
            'The HTTP-01 challenge only validates the domain over the standard ports, so '
            'port must be 80. Switch acme_challenge to dns-01 or provide your own ssl_certs '
            'to use another port. You provided: 8080',
        ),
        (
            'ssl_port',
            8443,
            'The HTTP-01 challenge only validates the domain over the standard ports, so '
            'ssl_port must be 443. Switch acme_challenge to dns-01 or provide your own '
            'ssl_certs to use another port. You provided: 8443',
        ),
    ],
)
def test_http_01_challenge_requires_the_standard_ports(ssl_setups, option, value, message):
    assert error('web', option, value, **ssl_setups['http-01']) == message


@pytest.mark.parametrize('option,value', [('port', 8080), ('ssl_port', 8443)])
@pytest.mark.parametrize('setup', ['dns-01', 'acme-dns', 'own certificates'])
def test_non_standard_ports_are_allowed_without_http_01(ssl_setups, setup, option, value):
    assert check('web', option, value, **ssl_setups[setup]) is None


# [web] use_ssl and ssl_certs


@pytest.mark.parametrize('value', ['no', 'builtin', 'external'])
def test_use_ssl_accepts_known_modes(value):
    assert check('web', 'use_ssl', value) is None


def test_use_ssl_rejects_an_unknown_mode():
    assert error('web', 'use_ssl', 'not sure') == (
        'Must be one of the following: no, builtin, external. You provided: not sure'
    )


def test_ssl_certs_accepts_a_directory_with_a_certificate_pair(certs_dir):
    assert check('web', 'ssl_certs', certs_dir, use_ssl='builtin', host='localhost') is None


def test_ssl_certs_rejects_a_missing_directory():
    message = error('web', 'ssl_certs', '/no/such/dir', use_ssl='builtin', host='localhost')
    assert 'path to certificates directory must be valid' in message


def test_ssl_certs_rejects_a_directory_without_the_certificate(tmp_path):
    message = error('web', 'ssl_certs', tmp_path, use_ssl='builtin', host='localhost')
    assert "('localhost.crt', 'localhost.key')" in message


def test_ssl_certs_rejects_a_certificate_without_a_key(tmp_path):
    (tmp_path / 'localhost.crt').write_text('cert')
    message = error('web', 'ssl_certs', tmp_path, use_ssl='builtin', host='localhost')
    assert "('localhost.crt', 'localhost.key')" in message


@pytest.mark.parametrize('use_ssl', ['external', 'no'])
def test_ssl_certs_is_ignored_unless_ssl_is_builtin(use_ssl):
    assert check('web', 'ssl_certs', '/no/such/dir', use_ssl=use_ssl) is None


# [web] acme_challenge and acme_dns_api_config


@pytest.mark.parametrize('value', ['http-01', 'dns-01', 'acme-dns'])
def test_acme_challenge_accepts_known_challenges(value):
    assert check('web', 'acme_challenge', value) is None


def test_acme_challenge_rejects_an_unknown_challenge():
    assert error('web', 'acme_challenge', 'tls-alpn-01') == (
        'Must be one of the following: http-01, dns-01, acme-dns. You provided: tls-alpn-01'
    )


def test_acme_dns_accepts_a_host_with_subdomains(ssl_setups):
    assert check('web', 'acme_challenge', 'acme-dns', **ssl_setups['acme-dns']) is None


@pytest.mark.parametrize('host', ['localhost', '192.168.0.1'])
def test_acme_dns_rejects_a_host_without_subdomains(ssl_setups, host):
    options = dict(ssl_setups['acme-dns'], host=host)
    assert error('web', 'acme_challenge', 'acme-dns', **options) == (
        'acme-dns answers the challenges in a zone delegated from the host, which is not '
        'possible for IP addresses and single-label host names. You provided: {0}'.format(host)
    )


@pytest.mark.parametrize('setup', ['no ssl', 'external ssl', 'own certificates'])
def test_acme_dns_host_is_not_checked_without_letsencrypt(ssl_setups, setup):
    options = dict(ssl_setups[setup], host='localhost')
    assert check('web', 'acme_challenge', 'acme-dns', **options) is None


@pytest.mark.parametrize(
    'value,message',
    [
        (
            '',
            'Required when acme_challenge is set to dns-01: a path to the file with the '
            'credentials of your DNS provider',
        ),
        ('/no/such/file.yml', "Can't read /no/such/file.yml: No such file or directory"),
    ],
)
def test_acme_dns_api_config_must_point_to_a_file_for_dns_01(ssl_setups, value, message):
    assert error('web', 'acme_dns_api_config', value, **ssl_setups['dns-01']) == message


def test_acme_dns_api_config_must_name_the_dns_api(ssl_setups, tmp_path):
    credentials = tmp_path / 'no-dns-api.yml'
    credentials.write_text('CF_Token: secret\n')
    message = error('web', 'acme_dns_api_config', credentials, **ssl_setups['dns-01'])
    assert 'must contain a DNS_API line' in message


@skip_if_root
def test_acme_dns_api_config_must_be_readable(ssl_setups, tmp_path):
    credentials = tmp_path / 'unreadable.yml'
    credentials.write_text('DNS_API: dns_cf\n')
    credentials.chmod(0o000)
    try:
        message = error('web', 'acme_dns_api_config', credentials, **ssl_setups['dns-01'])
    finally:
        credentials.chmod(0o600)
    assert message.startswith("Can't read {0}: ".format(credentials))


@pytest.mark.parametrize(
    'setup,overrides',
    [
        pytest.param('no ssl', {'acme_challenge': 'dns-01'}, id='dns-01 without ssl'),
        pytest.param(
            'own certificates', {'acme_challenge': 'dns-01'}, id='dns-01 with own certificates'
        ),
        pytest.param('acme-dns', {}, id='acme-dns'),
    ],
)
def test_acme_dns_api_config_is_ignored_unless_dns_01_is_used(ssl_setups, setup, overrides):
    options = dict(ssl_setups[setup], **overrides)
    assert check('web', 'acme_dns_api_config', '', **options) is None


@skip_if_root
def test_credentials_readable_by_others_are_warned_about(ssl_setups, acme_credentials):
    os.chmod(acme_credentials, 0o644)
    warnings = config(web=ssl_setups['dns-01']).warnings()
    assert len(warnings) == 1
    assert warnings[0].startswith('The credentials of your DNS provider are readable by')


def test_private_credentials_are_not_warned_about(ssl_setups, acme_credentials):
    os.chmod(acme_credentials, 0o600)
    assert config(web=ssl_setups['dns-01']).warnings() == []


def test_credentials_of_another_challenge_are_not_looked_at(ssl_setups, acme_credentials):
    os.chmod(acme_credentials, 0o644)
    options = dict(ssl_setups['acme-dns'], acme_dns_api_config=acme_credentials)
    assert config(web=options).warnings() == []


# [web] multi_workspace


def test_multi_workspace_must_be_a_boolean():
    assert 'Must be yes or no' in error('web', 'multi_workspace', 'maybe', host='localhost')


@pytest.mark.parametrize(
    'setup,overrides',
    [
        pytest.param('no ssl', {}, id='no ssl'),
        pytest.param('external ssl', {}, id='external ssl'),
        pytest.param('dns-01', {}, id='dns-01'),
        pytest.param('dns-01', {'ssl_port': 8443}, id='dns-01 on a non-standard ssl port'),
        pytest.param('acme-dns', {}, id='acme-dns'),
    ],
)
def test_multi_workspace_accepts_a_capable_configuration(ssl_setups, setup, overrides):
    options = dict(ssl_setups[setup], host='example.com', **overrides)
    assert check('web', 'multi_workspace', 'yes', **options) is None


@pytest.mark.parametrize('host', ['192.168.0.1', 'localhost'])
def test_multi_workspace_rejects_a_host_without_subdomains(host):
    message = error('web', 'multi_workspace', 'yes', host=host)
    assert message.startswith('Additional workspaces are served on subdomains of the host')


def test_multi_workspace_rejects_the_http_01_challenge(ssl_setups):
    message = error('web', 'multi_workspace', 'yes', **ssl_setups['http-01'])
    assert message.startswith('The HTTP-01 challenge cannot issue the wildcard certificate')


# [web] count


def test_count_must_be_a_positive_integer():
    assert check('web', 'count', 1) is None
    assert error('web', 'count', 0) == 'Must be greater or equal to 1. You provided: 0'


# [db]


def test_db_host_is_not_resolved_for_the_builtin_db():
    assert check('db', 'host', 'builtin_db') is None


def test_db_host_must_resolve_when_external():
    assert check('db', 'host', 'localhost') is None
    assert error('db', 'host', UNRESOLVABLE_HOST) == (
        "Can't resolve hostname: {0}".format(UNRESOLVABLE_HOST)
    )


def test_db_port_must_be_a_valid_port_number():
    assert check('db', 'port', 3306) is None
    assert error('db', 'port', 70000) == 'Must be less or equal to 65535. You provided: 70000'


def test_backup_mount_must_be_a_directory(tmp_path):
    assert check('db', 'backup_mount', tmp_path) is None
    assert error('db', 'backup_mount', 'not a valid path') == (
        'Must be a directory: not a valid path'
    )


@skip_if_root
def test_backup_mount_must_be_writable(tmp_path):
    read_only = tmp_path / 'read-only'
    read_only.mkdir(mode=0o500)
    try:
        assert 'Write permission denied' in error('db', 'backup_mount', read_only)
    finally:
        read_only.chmod(0o700)


# [email]


def test_smtp_host_is_not_resolved_for_the_builtin_smtp():
    assert check('email', 'smtp_host', 'builtin_smtp') is None


def test_smtp_host_must_resolve_when_external():
    assert check('email', 'smtp_host', 'localhost') is None
    assert error('email', 'smtp_host', UNRESOLVABLE_HOST) == (
        "Can't resolve hostname: {0}".format(UNRESOLVABLE_HOST)
    )


@pytest.mark.parametrize('value', ['plain', 'ssl', 'tls'])
def test_smtp_protocol_accepts_known_protocols(value):
    assert check('email', 'smtp_protocol', value) is None


def test_smtp_protocol_rejects_an_unknown_protocol():
    assert error('email', 'smtp_protocol', 'tcp') == (
        'Must be one of the following: plain, ssl, tls. You provided: tcp'
    )


def test_smtp_port_must_be_a_valid_port_number():
    assert check('email', 'smtp_port', 25) is None
    assert error('email', 'smtp_port', 'gav') == 'Must be an integer. You provided: gav'


@pytest.mark.parametrize('value', ['support@teamplify.com', 'Teamplify <support@teamplify.com>'])
def test_address_from_accepts_a_plain_address_and_a_display_name(value):
    assert check('email', 'address_from', value) is None


def test_address_from_rejects_a_non_address():
    assert error('email', 'address_from', 'not even a email') == 'Invalid email: not even a email'


# [worker]


@pytest.mark.parametrize('option', ['slim_count', 'fat_count'])
def test_worker_counts_must_be_positive_integers(option):
    assert check('worker', option, 1) is None
    assert error('worker', option, 0) == 'Must be greater or equal to 1. You provided: 0'


# unknown sections and options


@pytest.mark.parametrize(
    'section,option,message',
    [
        ('nope', 'anything', 'Unknown section: [nope]'),
        ('db', 'unknown_key', 'Unknown option'),
    ],
)
def test_unknown_sections_and_options_are_rejected(section, option, message):
    with pytest.raises(ConfigurationError) as raised:
        Configurator().validate_option(section, option, 'value')
    assert str(raised.value) == message


# validate(): how the individual rules add up


def test_default_configuration_is_valid_except_product_key():
    with pytest.raises(ConfigurationError) as raised:
        Configurator().validate()
    assert raised.value.messages == ['[main] product_key: Product key is missing']


def test_a_complete_configuration_validates():
    valid = config(main={'product_key': PRODUCT_KEY}, web={'host': 'localhost'})
    assert valid.validate() is valid


def test_validate_collects_every_error_with_its_location():
    broken = config(
        main={'product_key': '42'},
        web={'port': 'gav', 'use_ssl': 'not sure'},
        email={'smtp_protocol': 'tcp'},
    )
    with pytest.raises(ConfigurationError) as raised:
        broken.validate()
    assert raised.value.messages == [
        '[main] product_key: Invalid product key: 42',
        '[web] port: Must be an integer. You provided: gav',
        '[web] use_ssl: Must be one of the following: no, builtin, external. '
        'You provided: not sure',
        '[email] smtp_protocol: Must be one of the following: plain, ssl, tls. You provided: tcp',
    ]


def test_validate_reports_an_unknown_section_once():
    unknown = config(
        main={'product_key': PRODUCT_KEY},
        web={'host': 'localhost'},
        unknown_section={'with': 'lots', 'of': 'keys'},
    )
    with pytest.raises(ConfigurationError) as raised:
        unknown.validate()
    assert raised.value.messages == ['Unknown section: [unknown_section]']


@pytest.mark.parametrize(
    'messages,text',
    [
        pytest.param(['one problem'], 'one problem', id='one'),
        pytest.param(['first', 'second'], '2 errors found:\n -> first\n -> second', id='several'),
    ],
)
def test_configuration_error_lists_the_messages(messages, text):
    assert str(ConfigurationError(messages)) == text


# load / dump and their in-memory counterparts


def test_dumps_writes_the_whole_configuration():
    dumped = Configurator().dumps()
    dumped = re.sub(r'^(signing_key = ).+$', r'\1RANDOM', dumped, flags=re.M)
    dumped = re.sub(r'^(backup_mount = ).+$', r'\1BACKUP_MOUNT', dumped, flags=re.M)
    # \x20 is the space that an empty value leaves behind. Spelled out so that
    # an editor stripping trailing whitespace cannot silently break this test
    expected = """\
[main]
product_key =\x20
update_channel = stable
send_crash_reports = yes

[web]
host = localhost
port = 80
ssl_port = 443
ssl_certs =\x20
use_ssl = no
acme_challenge = http-01
acme_dns_api_config =\x20
multi_workspace = no
count = 2

[db]
host = builtin_db
name = teamplify
port = 3306
user = root
password = teamplify
backup_mount = BACKUP_MOUNT

[email]
address_from = Teamplify <support@teamplify.com>
smtp_host = builtin_smtp
smtp_protocol = plain
smtp_port = 25
smtp_user =\x20
smtp_password =\x20

[crypto]
signing_key = RANDOM

[worker]
slim_count = 1
fat_count = 3

"""
    assert dumped == expected


def test_dumps_and_loads_round_trip():
    original = config(main={'product_key': PRODUCT_KEY}, web={'host': 'example.com'})
    restored = Configurator().loads(original.dumps())
    assert restored.dumps() == original.dumps()


def test_load_and_loads_read_the_same_configuration(tmp_path):
    text = '[main]\nproduct_key = {0}\n[web]\nhost = example.com\nport = 8080\n'.format(
        PRODUCT_KEY,
    )
    path = tmp_path / 'teamplify.ini'
    path.write_text(text)
    from_file = Configurator().load(str(path))
    from_string = Configurator().loads(text)
    assert from_file.dumps() == from_string.dumps()
    # the remembered path is the only difference between them
    assert from_file.config_path == str(path)
    assert from_string.config_path is None


def test_dump_and_dumps_write_the_same_configuration(tmp_path):
    # dump() adds a note that dumps() does not, and by default it also hides
    # the options left at their defaults
    path = tmp_path / 'teamplify.ini'
    Configurator().dump(str(path), hide_defaults=False)
    written = path.read_text()
    assert written == Configurator().dumps()


def test_dump_writes_the_file_and_load_reads_it_back(tmp_path):
    path = str(tmp_path / 'teamplify.ini')
    original = config(main={'product_key': PRODUCT_KEY}, web={'host': 'example.com'})
    assert original.dump(path) is original
    assert original.config_path == path

    restored = Configurator().load(path)
    assert restored.config_path == path
    assert restored.dumps() == original.dumps()


@pytest.mark.parametrize(
    'main,hide_defaults,line',
    [
        pytest.param({}, True, None, id='default channel hidden'),
        pytest.param({'update_channel': 'latest'}, True, 'update_channel = latest', id='custom'),
        pytest.param({}, False, 'update_channel = stable', id='defaults kept'),
    ],
)
def test_dump_hides_the_update_channel_left_at_its_default(tmp_path, main, hide_defaults, line):
    path = tmp_path / 'teamplify.ini'
    config(main=main).dump(str(path), hide_defaults=hide_defaults)
    lines = [written for written in path.read_text().splitlines() if 'update_channel' in written]
    assert lines == ([line] if line else [])


def test_load_only_overrides_the_options_that_the_file_sets(tmp_path):
    path = tmp_path / 'partial.ini'
    path.write_text('[web]\nhost = example.com\n')
    loaded = Configurator().load(str(path))
    assert loaded.parser.get('web', 'host') == 'example.com'
    assert loaded.parser.get('web', 'port') == '80'
    assert loaded.parser.get('db', 'name') == 'teamplify'


def test_load_an_empty_file_keeps_the_defaults(tmp_path):
    path = tmp_path / 'empty.ini'
    path.write_text('')
    loaded = Configurator().load(str(path))
    assert loaded.dumps() == Configurator().dumps()
    assert loaded.config_path == str(path)


def test_dump_overwrites_an_existing_configuration(tmp_path):
    existing = tmp_path / 'teamplify.ini'
    # deliberately longer than its replacement, so that a truncation bug would
    # leave a tail of the old contents behind
    existing.write_text('[web]\nhost = old.example.com\n' + '; filler\n' * 100)
    replacement = config(web={'host': 'new.example.com'})
    replacement.dump(str(existing))

    assert Configurator().load(str(existing)).dumps() == replacement.dumps()
    # comments are dropped on load, so the tail has to be checked in the file
    assert 'filler' not in existing.read_text()


def read_only_file(tmp_path):
    path = tmp_path / 'read-only.ini'
    path.write_text('')
    path.chmod(0o400)
    return path


def unwritable_directory(tmp_path):
    directory = tmp_path / 'read-only'
    directory.mkdir(mode=0o500)
    return directory / 'teamplify.ini'


def missing_directory(tmp_path):
    return tmp_path / 'no-such-dir' / 'teamplify.ini'


def a_directory(tmp_path):
    return tmp_path


@pytest.mark.parametrize(
    'prepare,reason',
    [
        pytest.param(read_only_file, 'Permission denied', marks=skip_if_root, id='read-only file'),
        pytest.param(
            unwritable_directory,
            'Permission denied',
            marks=skip_if_root,
            id='unwritable directory',
        ),
        pytest.param(missing_directory, 'No such file or directory', id='missing directory'),
        pytest.param(a_directory, 'Is a directory', id='path is a directory'),
    ],
)
def test_dump_reports_a_failed_write(tmp_path, prepare, reason):
    path = prepare(tmp_path)
    before = path.read_text() if path.is_file() else None
    with pytest.raises(ConfigurationError) as raised:
        Configurator().dump(str(path))
    assert str(raised.value) == "Can't write the configuration file {0}: {1}".format(path, reason)
    assert (path.read_text() if path.is_file() else None) == before


def test_the_config_path_can_be_given_to_the_constructor(tmp_path):
    path = tmp_path / 'teamplify.ini'
    path.write_text('[web]\nhost = example.com\n')
    assert Configurator(str(path)).load().parser.get('web', 'host') == 'example.com'


def test_no_config_path_is_found_when_no_location_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(
        Configurator,
        'default_config_locations',
        [str(tmp_path / 'nowhere.ini')],
    )
    assert Configurator().config_path is None


def test_the_first_existing_default_location_wins(tmp_path, monkeypatch):
    present = tmp_path / 'present.ini'
    present.write_text('[web]\n')
    monkeypatch.setattr(
        Configurator,
        'default_config_locations',
        [str(tmp_path / 'missing.ini'), str(present)],
    )
    assert Configurator().config_path == str(present)


@skip_if_root
def test_an_unreadable_default_location_gives_way_to_the_next(tmp_path, monkeypatch):
    unreadable = tmp_path / 'unreadable.ini'
    unreadable.write_text('[web]\nhost = unreadable.example.com\n')
    unreadable.chmod(0o000)
    readable = tmp_path / 'readable.ini'
    readable.write_text('[web]\nhost = example.com\n')
    monkeypatch.setattr(
        Configurator,
        'default_config_locations',
        [str(unreadable), str(readable)],
    )
    try:
        configurator = Configurator().load()
    finally:
        unreadable.chmod(0o600)
    assert configurator.config_path == str(readable)
    assert configurator.parser.get('web', 'host') == 'example.com'


@skip_if_root
def test_no_config_path_is_found_when_every_location_is_unreadable(tmp_path, monkeypatch):
    unreadable = tmp_path / 'unreadable.ini'
    unreadable.write_text('[web]\nhost = example.com\n')
    unreadable.chmod(0o000)
    monkeypatch.setattr(Configurator, 'default_config_locations', [str(unreadable)])
    try:
        configurator = Configurator().load()
    finally:
        unreadable.chmod(0o600)
    assert configurator.config_path is None
    assert configurator.dumps() == Configurator().dumps()


# remove_unknown()


def test_remove_unknown_drops_unknown_sections_and_options():
    configurator = config(
        web={'host': 'example.com', 'nonsense': 'value'},
        unknown_section={'with': 'lots', 'of': 'keys'},
    )
    assert configurator.remove_unknown() is configurator
    assert 'unknown_section' not in configurator.parser.sections()
    assert 'nonsense' not in configurator.parser.options('web')
    assert configurator.parser.get('web', 'host') == 'example.com'


def test_remove_unknown_makes_the_configuration_validatable():
    configurator = config(
        main={'product_key': PRODUCT_KEY},
        web={'host': 'localhost', 'nonsense': 'value'},
        unknown_section={'of': 'keys'},
    )
    assert configurator.remove_unknown().validate() is configurator


def test_remove_unknown_keeps_a_clean_configuration_intact():
    configurator = config(web={'host': 'example.com'})
    before = configurator.dumps()
    assert configurator.remove_unknown().dumps() == before


# env()


def test_env_exposes_every_option_as_section_underscore_name():
    env = config(web={'host': 'example.com'}).env()
    assert env['WEB_HOST'] == 'example.com'
    assert env['DB_PORT'] == '3306'
    assert env['MAIN_UPDATE_CHANNEL'] == 'stable'
    assert env['CRYPTO_SIGNING_KEY']


@pytest.mark.parametrize(
    'setup,overrides,expected',
    [
        pytest.param(
            'no ssl',
            {},
            {'COMPOSE_PROFILES': 'nossl', 'HTTPS_METHOD': 'nohttps', 'WEB_SSL_PORT': None},
            id='no ssl',
        ),
        pytest.param(
            'external ssl',
            {},
            {'COMPOSE_PROFILES': 'nossl', 'HTTPS_METHOD': 'nohttps', 'WEB_SSL_PORT': '443'},
            id='external ssl',
        ),
        pytest.param(
            'own certificates',
            {},
            {'COMPOSE_PROFILES': 'ssl', 'HTTPS_METHOD': 'redirect', 'HTTPS_PORT': '443'},
            id='own certificates',
        ),
        pytest.param(
            'http-01',
            {},
            {
                'COMPOSE_PROFILES': 'ssl,letsencrypt',
                'ACME_CHALLENGE': 'HTTP-01',
                'ACMESH_DNS_API_CONFIG': '',
                'ACME_DNS_CONFIG': '',
            },
            id='http-01',
        ),
        pytest.param(
            'dns-01',
            {},
            {
                'COMPOSE_PROFILES': 'ssl,letsencrypt',
                'ACME_CHALLENGE': 'DNS-01',
                'ACMESH_DNS_API_CONFIG': 'DNS_API: dns_cf\nCF_Token: secret\n',
                'ACME_DNS_CONFIG': '',
            },
            id='dns-01',
        ),
        pytest.param(
            'acme-dns',
            {'host': 'Example.com'},
            {
                'COMPOSE_PROFILES': 'ssl,letsencrypt,acme-dns',
                'ACME_CHALLENGE': 'DNS-01',
                # filled in at startup, once acme-dns has issued the credentials
                'ACMESH_DNS_API_CONFIG': '',
                'ACME_DNS_CONFIG': acme_dns.server_config('example.com'),
            },
            id='acme-dns',
        ),
        pytest.param(
            'own certificates',
            {'acme_challenge': 'dns-01'},
            {'COMPOSE_PROFILES': 'ssl', 'ACME_CHALLENGE': 'HTTP-01', 'ACMESH_DNS_API_CONFIG': ''},
            id='dns-01 ignored with own certificates',
        ),
        pytest.param(
            'own certificates',
            {'acme_challenge': 'acme-dns'},
            {'COMPOSE_PROFILES': 'ssl', 'ACME_DNS_CONFIG': ''},
            id='acme-dns ignored with own certificates',
        ),
        pytest.param(
            'external ssl',
            {'acme_challenge': 'acme-dns'},
            {'COMPOSE_PROFILES': 'nossl', 'ACME_DNS_CONFIG': ''},
            id='acme-dns ignored with external ssl',
        ),
    ],
)
def test_env_for_each_ssl_setup(ssl_setups, setup, overrides, expected):
    env = config(web=dict(ssl_setups[setup], **overrides)).env()
    assert {name: env.get(name) for name in expected} == expected


@pytest.mark.parametrize(
    'setup,multi_workspace,virtual_host,letsencrypt_host',
    [
        ('http-01', 'no', 'example.com', 'example.com'),
        ('dns-01', 'no', 'example.com', 'example.com'),
        ('dns-01', 'yes', 'example.com,*.example.com', 'example.com,*.example.com'),
        ('acme-dns', 'no', 'example.com', 'example.com'),
        ('acme-dns', 'yes', 'example.com,*.example.com', 'example.com,*.example.com'),
    ],
)
def test_env_hosts(ssl_setups, setup, multi_workspace, virtual_host, letsencrypt_host):
    env = config(web=dict(ssl_setups[setup], multi_workspace=multi_workspace)).env()
    assert env['VIRTUAL_HOST'] == virtual_host
    assert env['LETSENCRYPT_HOST'] == letsencrypt_host


@pytest.mark.parametrize(
    'host,postmaster',
    [
        pytest.param('teamplify.example.com', 'postmaster@example.com', id='domain'),
        pytest.param('192.168.0.1', 'postmaster@192.168.0.1', id='ip address'),
    ],
)
def test_env_postmaster_address(host, postmaster):
    assert config(web={'host': host}).env()['POSTMASTER_EMAIL'] == postmaster


# the helpers that the rules above are built on


@pytest.mark.parametrize(
    'use_ssl,expected',
    [('no', ''), ('builtin', 'builtin'), ('external', 'external'), ('yes', 'builtin')],
)
def test_ssl_mode(use_ssl, expected):
    assert config(web={'use_ssl': use_ssl}).ssl_mode() == expected


@pytest.mark.parametrize(
    'setup,overrides,letsencrypt,acme_dns_in_use',
    [
        pytest.param('no ssl', {}, False, False, id='no ssl'),
        pytest.param('external ssl', {}, False, False, id='external ssl'),
        pytest.param('own certificates', {}, False, False, id='own certificates'),
        pytest.param('http-01', {}, True, False, id='http-01'),
        pytest.param('dns-01', {}, True, False, id='dns-01'),
        pytest.param('acme-dns', {}, True, True, id='acme-dns'),
        pytest.param(
            'external ssl',
            {'acme_challenge': 'acme-dns'},
            False,
            False,
            id='acme-dns ignored with external ssl',
        ),
        pytest.param(
            'own certificates',
            {'acme_challenge': 'acme-dns'},
            False,
            False,
            id='acme-dns ignored with own certificates',
        ),
    ],
)
def test_uses_letsencrypt_and_acme_dns(
    ssl_setups,
    setup,
    overrides,
    letsencrypt,
    acme_dns_in_use,
):
    configurator = config(web=dict(ssl_setups[setup], **overrides))
    assert configurator.uses_letsencrypt() is letsencrypt
    assert configurator.uses_acme_dns() is acme_dns_in_use


@pytest.mark.parametrize(
    'web,expected',
    [
        pytest.param({}, 'http-01', id='default'),
        pytest.param({'acme_challenge': 'DNS-01'}, 'dns-01', id='dns-01'),
        pytest.param({'acme_challenge': 'ACME-DNS'}, 'acme-dns', id='acme-dns'),
    ],
)
def test_acme_challenge_is_normalized(web, expected):
    assert config(web=web).acme_challenge() == expected


@pytest.mark.parametrize(
    'web,expected',
    [
        pytest.param({}, False, id='default'),
        pytest.param({'multi_workspace': 'yes'}, True, id='enabled'),
    ],
)
def test_multi_workspace(web, expected):
    assert config(web=web).multi_workspace() is expected


def test_acme_dns_api_config_returns_the_file_contents(acme_credentials):
    assert config(web={'acme_dns_api_config': acme_credentials}).acme_dns_api_config() == (
        'DNS_API: dns_cf\nCF_Token: secret\n'
    )


@pytest.mark.parametrize(
    'web',
    [
        pytest.param({}, id='not set'),
        pytest.param({'acme_dns_api_config': '/no/such/file.yml'}, id='unreadable'),
    ],
)
def test_acme_dns_api_config_is_empty_without_a_readable_file(web):
    assert config(web=web).acme_dns_api_config() == ''
