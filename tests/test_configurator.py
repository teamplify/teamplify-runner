import os
import re

import pytest

from teamplify_runner.configurator import ConfigurationError, Configurator


PRODUCT_KEY = 'svr_Q5Luvv4yZbhbdale-kzbToeKyVsthN5yx35Hh'

# RFC 2606 reserves .invalid, so this name never resolves, with or without
# network access. Conversely, localhost resolves even without it. Tests that
# reach validate_hostname() must stick to these two.
UNRESOLVABLE_HOST = 'no-such-host.invalid'


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


def test_product_key_must_be_present():
    assert error('main', 'product_key', '') == 'Product key is missing'


def test_product_key_must_match_the_format():
    assert error('main', 'product_key', '42') == 'Invalid product key: 42'


def test_product_key_accepts_a_well_formed_key():
    assert check('main', 'product_key', PRODUCT_KEY) is None


def test_update_channel_accepts_known_channels():
    assert check('main', 'update_channel', 'stable') is None
    assert check('main', 'update_channel', 'latest') is None


def test_update_channel_rejects_an_unknown_channel():
    assert error('main', 'update_channel', 'nightly') == (
        'Must be one of the following: stable, latest. You provided: nightly'
    )


def test_send_crash_reports_must_be_a_boolean():
    assert check('main', 'send_crash_reports', 'yes') is None
    assert check('main', 'send_crash_reports', 'no') is None
    assert 'Must be yes or no' in error('main', 'send_crash_reports', 'sometimes')


# [web] host


def test_host_must_resolve():
    assert check('web', 'host', 'localhost') is None
    assert error('web', 'host', UNRESOLVABLE_HOST) == (
        "Can't resolve hostname: {0}".format(UNRESOLVABLE_HOST)
    )


def test_host_keeps_an_inline_comment_as_part_of_the_value():
    # ConfigParser is created without inline_comment_prefixes, so everything
    # after the value belongs to it
    assert error('web', 'host', '-1 # comment after value') == (
        "Can't resolve hostname: -1 # comment after value"
    )


# [web] port and ssl_port


def test_port_must_be_a_valid_port_number():
    assert check('web', 'port', 8080) is None
    assert error('web', 'port', 'gav') == 'Must be an integer. You provided: gav'
    assert error('web', 'port', 70000) == 'Must be less or equal to 65535. You provided: 70000'


def test_the_two_ports_must_differ():
    # nginx cannot listen on one port both with and without TLS
    assert 'must be different' in error('web', 'port', 8080, ssl_port=8080)
    assert 'must be different' in error('web', 'ssl_port', 8080, port=8080)


def test_the_default_ports_differ():
    assert check('web', 'port', 80) is None
    assert check('web', 'ssl_port', 443) is None


def test_http_01_challenge_requires_the_standard_ports():
    letsencrypt = {'use_ssl': 'builtin', 'acme_challenge': 'http-01'}
    assert error('web', 'port', 8080, **letsencrypt) == (
        'The HTTP-01 challenge only validates the domain over the standard ports, so port '
        'must be 80. Switch acme_challenge to dns-01 or provide your own ssl_certs to use '
        'another port. You provided: 8080'
    )
    assert error('web', 'ssl_port', 8443, **letsencrypt) == (
        'The HTTP-01 challenge only validates the domain over the standard ports, so '
        'ssl_port must be 443. Switch acme_challenge to dns-01 or provide your own '
        'ssl_certs to use another port. You provided: 8443'
    )


def test_dns_01_challenge_allows_non_standard_ports(acme_credentials):
    dns_01 = {
        'use_ssl': 'builtin',
        'acme_challenge': 'dns-01',
        'acme_dns_api_config': acme_credentials,
    }
    assert check('web', 'port', 8080, **dns_01) is None
    assert check('web', 'ssl_port', 8443, **dns_01) is None


def test_own_certificates_allow_non_standard_ports(certs_dir):
    own_certs = {'use_ssl': 'builtin', 'ssl_certs': certs_dir, 'host': 'localhost'}
    assert check('web', 'port', 8080, **own_certs) is None
    assert check('web', 'ssl_port', 8443, **own_certs) is None


# [web] use_ssl and ssl_certs


def test_use_ssl_accepts_known_modes():
    for mode in ('no', 'builtin', 'external'):
        assert check('web', 'use_ssl', mode) is None


def test_use_ssl_rejects_an_unknown_mode():
    assert error('web', 'use_ssl', 'not sure') == (
        'Must be one of the following: no, builtin, external. You provided: not sure'
    )


def test_ssl_certs_accepts_a_directory_with_a_certificate_pair(certs_dir):
    assert check('web', 'ssl_certs', certs_dir, use_ssl='builtin', host='localhost') is None


def test_ssl_certs_accepts_a_directory_of_pem_files(tmp_path):
    pem_dir = tmp_path / 'localhost'
    pem_dir.mkdir()
    (pem_dir / 'fullchain.pem').write_text('cert')
    assert check('web', 'ssl_certs', tmp_path, use_ssl='builtin', host='localhost') is None


def test_ssl_certs_rejects_a_missing_directory():
    message = error('web', 'ssl_certs', '/no/such/dir', use_ssl='builtin', host='localhost')
    assert 'path to certificates directory must be valid' in message


def test_ssl_certs_rejects_a_directory_without_the_certificate(tmp_path):
    message = error('web', 'ssl_certs', tmp_path, use_ssl='builtin', host='localhost')
    assert "('localhost.crt', 'localhost.key')" in message


def test_ssl_certs_is_ignored_unless_ssl_is_builtin():
    assert check('web', 'ssl_certs', '/no/such/dir', use_ssl='external') is None
    assert check('web', 'ssl_certs', '/no/such/dir', use_ssl='no') is None


# [web] acme_challenge and acme_dns_api_config


def test_acme_challenge_accepts_known_challenges(acme_credentials):
    assert check('web', 'acme_challenge', 'http-01') is None
    assert (
        check(
            'web',
            'acme_challenge',
            'dns-01',
            use_ssl='builtin',
            acme_dns_api_config=acme_credentials,
        )
        is None
    )


def test_acme_challenge_rejects_an_unknown_challenge():
    assert error('web', 'acme_challenge', 'tls-alpn-01') == (
        'Must be one of the following: http-01, dns-01. You provided: tls-alpn-01'
    )


def test_acme_dns_api_config_is_required_for_dns_01():
    message = error('web', 'acme_dns_api_config', '', use_ssl='builtin', acme_challenge='dns-01')
    assert message.startswith('Required when acme_challenge is set to dns-01')


def test_acme_dns_api_config_must_exist():
    message = error(
        'web',
        'acme_dns_api_config',
        '/no/such/file.yml',
        use_ssl='builtin',
        acme_challenge='dns-01',
    )
    assert message == "Can't read /no/such/file.yml: No such file or directory"


def test_acme_dns_api_config_must_name_the_dns_api(tmp_path):
    credentials = tmp_path / 'acme-dns.yml'
    credentials.write_text('CF_Token: secret\n')
    message = error(
        'web',
        'acme_dns_api_config',
        credentials,
        use_ssl='builtin',
        acme_challenge='dns-01',
    )
    assert 'must contain a DNS_API line' in message


@pytest.mark.skipif(os.geteuid() == 0, reason='root can read any file')
def test_acme_dns_api_config_must_be_readable(tmp_path):
    credentials = tmp_path / 'acme-dns.yml'
    credentials.write_text('DNS_API: dns_cf\n')
    credentials.chmod(0o000)
    try:
        message = error(
            'web',
            'acme_dns_api_config',
            credentials,
            use_ssl='builtin',
            acme_challenge='dns-01',
        )
    finally:
        credentials.chmod(0o600)
    assert message.startswith("Can't read {0}: ".format(credentials))


def test_acme_dns_api_config_is_ignored_without_letsencrypt(certs_dir):
    assert check('web', 'acme_dns_api_config', '', acme_challenge='dns-01') is None
    assert (
        check(
            'web',
            'acme_dns_api_config',
            '',
            use_ssl='builtin',
            ssl_certs=certs_dir,
            host='localhost',
            acme_challenge='dns-01',
        )
        is None
    )


# [web] multi_workspace


def test_multi_workspace_must_be_a_boolean():
    assert 'Must be yes or no' in error('web', 'multi_workspace', 'maybe', host='localhost')


@pytest.mark.parametrize(
    'other_options',
    [
        {'use_ssl': 'no'},
        {'use_ssl': 'external'},
        {'use_ssl': 'builtin', 'acme_challenge': 'dns-01'},
        {'use_ssl': 'builtin', 'ssl_port': 8443, 'acme_challenge': 'dns-01'},
    ],
)
def test_multi_workspace_accepts_a_capable_configuration(other_options, acme_credentials):
    other_options = {**other_options, 'host': 'example.com'}
    if other_options.get('acme_challenge') == 'dns-01':
        other_options['acme_dns_api_config'] = acme_credentials
    assert check('web', 'multi_workspace', 'yes', **other_options) is None


@pytest.mark.parametrize('host', ['192.168.0.1', 'localhost'])
def test_multi_workspace_rejects_a_host_without_subdomains(host):
    message = error('web', 'multi_workspace', 'yes', host=host)
    assert message.startswith('Additional workspaces are served on subdomains of the host')


def test_multi_workspace_rejects_the_http_01_challenge():
    message = error('web', 'multi_workspace', 'yes', host='example.com', use_ssl='builtin')
    assert message.startswith('The HTTP-01 challenge cannot issue the wildcard certificate')


def test_multi_workspace_off_is_never_rejected():
    assert check('web', 'multi_workspace', 'no', host='localhost', use_ssl='builtin') is None


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


def test_backup_mount_must_be_a_writable_directory(tmp_path):
    assert check('db', 'backup_mount', tmp_path) is None
    assert error('db', 'backup_mount', 'not a valid path') == (
        'Must be a directory: not a valid path'
    )


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


def test_smtp_protocol_accepts_known_protocols():
    for protocol in ('plain', 'ssl', 'tls'):
        assert check('email', 'smtp_protocol', protocol) is None


def test_smtp_protocol_rejects_an_unknown_protocol():
    assert error('email', 'smtp_protocol', 'tcp') == (
        'Must be one of the following: plain, ssl, tls. You provided: tcp'
    )


def test_smtp_port_must_be_a_valid_port_number():
    assert check('email', 'smtp_port', 25) is None
    assert error('email', 'smtp_port', 'gav') == 'Must be an integer. You provided: gav'


def test_address_from_accepts_a_plain_address_and_a_display_name():
    assert check('email', 'address_from', 'support@teamplify.com') is None
    assert check('email', 'address_from', 'Teamplify <support@teamplify.com>') is None


def test_address_from_rejects_a_non_address():
    assert error('email', 'address_from', 'not even a email') == 'Invalid email: not even a email'


# [worker]


@pytest.mark.parametrize('option', ['slim_count', 'fat_count'])
def test_worker_counts_must_be_positive_integers(option):
    assert check('worker', option, 1) is None
    assert error('worker', option, 0) == 'Must be greater or equal to 1. You provided: 0'


# unknown sections and options


def test_unknown_section_is_rejected():
    with pytest.raises(ConfigurationError) as raised:
        Configurator().validate_option('nope', 'anything', 'value')
    assert str(raised.value) == 'Unknown section: [nope]'


def test_unknown_option_is_rejected():
    with pytest.raises(ConfigurationError) as raised:
        Configurator().validate_option('db', 'unknown_key', 'lol')
    assert str(raised.value) == 'Unknown option'


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


def test_configuration_error_lists_the_messages():
    single = ConfigurationError(['one problem'])
    assert str(single) == 'one problem'
    several = ConfigurationError(['first', 'second'])
    assert str(several) == '2 errors found:\n -> first\n -> second'


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
    written = re.sub(r'^; please note.*\n', '', path.read_text(), flags=re.M)
    assert written == Configurator().dumps()


def test_dump_writes_the_file_and_load_reads_it_back(tmp_path):
    path = str(tmp_path / 'teamplify.ini')
    original = config(main={'product_key': PRODUCT_KEY}, web={'host': 'example.com'})
    assert original.dump(path) is original
    assert original.config_path == path

    restored = Configurator().load(path)
    assert restored.config_path == path
    assert restored.dumps() == original.dumps()


def test_dump_hides_the_default_update_channel_but_keeps_a_custom_one(tmp_path):
    hidden = str(tmp_path / 'hidden.ini')
    Configurator().dump(hidden)
    assert 'update_channel' not in open(hidden).read()

    kept = str(tmp_path / 'kept.ini')
    config(main={'update_channel': 'latest'}).dump(kept)
    assert 'update_channel = latest' in open(kept).read()


def test_dump_can_keep_the_defaults(tmp_path):
    path = str(tmp_path / 'full.ini')
    Configurator().dump(path, hide_defaults=False)
    assert 'update_channel = stable' in open(path).read()


def test_dump_writes_the_email_note_as_a_comment(tmp_path):
    path = str(tmp_path / 'with-note.ini')
    Configurator().dump(path)
    notes = [line.strip() for line in open(path) if 'please note' in line]
    assert len(notes) == 1
    assert notes[0].startswith(';')

    loaded = Configurator().load(path)
    assert loaded.parser.options('email') == list(Configurator.defaults['email'])
    assert loaded.validate_option('email', 'smtp_host', 'builtin_smtp') is None


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


@pytest.mark.skipif(os.geteuid() == 0, reason='root can write any file')
def test_dump_reports_a_read_only_file(tmp_path):
    path = tmp_path / 'read-only.ini'
    path.write_text('')
    path.chmod(0o400)
    try:
        with pytest.raises(ConfigurationError) as raised:
            Configurator().dump(str(path))
    finally:
        path.chmod(0o600)
    assert str(raised.value) == (
        "Can't write the configuration file {0}: Permission denied".format(path)
    )
    assert path.read_text() == ''


@pytest.mark.skipif(os.geteuid() == 0, reason='root can write any file')
def test_dump_reports_an_unwritable_directory(tmp_path):
    read_only = tmp_path / 'read-only'
    read_only.mkdir(mode=0o500)
    path = read_only / 'teamplify.ini'
    try:
        with pytest.raises(ConfigurationError) as raised:
            Configurator().dump(str(path))
    finally:
        read_only.chmod(0o700)
    assert str(raised.value) == (
        "Can't write the configuration file {0}: Permission denied".format(path)
    )


def test_dump_reports_a_missing_directory(tmp_path):
    path = tmp_path / 'no-such-dir' / 'teamplify.ini'
    with pytest.raises(ConfigurationError) as raised:
        Configurator().dump(str(path))
    assert str(raised.value) == (
        "Can't write the configuration file {0}: No such file or directory".format(path)
    )


def test_dump_reports_a_path_that_is_not_a_file(tmp_path):
    with pytest.raises(ConfigurationError) as raised:
        Configurator().dump(str(tmp_path))
    assert str(raised.value) == (
        "Can't write the configuration file {0}: Is a directory".format(tmp_path)
    )


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


@pytest.mark.skipif(os.geteuid() == 0, reason='root can read any file')
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


@pytest.mark.skipif(os.geteuid() == 0, reason='root can read any file')
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


def test_env_without_ssl():
    env = config(web={'host': 'example.com', 'use_ssl': 'no'}).env()
    assert env['COMPOSE_PROFILES'] == 'nossl'
    assert env['HTTPS_METHOD'] == 'nohttps'
    assert 'WEB_SSL_PORT' not in env


def test_env_with_external_ssl():
    env = config(web={'host': 'example.com', 'use_ssl': 'external'}).env()
    assert env['COMPOSE_PROFILES'] == 'nossl'
    assert env['HTTPS_METHOD'] == 'nohttps'
    assert env['WEB_SSL_PORT'] == '443'


def test_env_with_builtin_ssl_and_own_certificates(certs_dir):
    env = config(web={'host': 'localhost', 'use_ssl': 'builtin', 'ssl_certs': certs_dir}).env()
    assert env['COMPOSE_PROFILES'] == 'ssl'
    assert env['HTTPS_METHOD'] == 'redirect'
    assert env['HTTPS_PORT'] == '443'


def test_env_with_builtin_ssl_and_letsencrypt():
    env = config(web={'host': 'example.com', 'use_ssl': 'builtin'}).env()
    assert env['COMPOSE_PROFILES'] == 'ssl,letsencrypt'
    assert env['ACME_CHALLENGE'] == 'HTTP-01'
    assert env['ACMESH_DNS_API_CONFIG'] == ''
    assert env['LETSENCRYPT_HOST'] == 'example.com'


def test_env_with_the_dns_01_challenge(acme_credentials):
    env = config(
        web={
            'host': 'example.com',
            'use_ssl': 'builtin',
            'acme_challenge': 'dns-01',
            'acme_dns_api_config': acme_credentials,
        }
    ).env()
    assert env['ACME_CHALLENGE'] == 'DNS-01'
    assert env['ACMESH_DNS_API_CONFIG'] == 'DNS_API: dns_cf\nCF_Token: secret\n'


def test_env_ignores_the_dns_01_challenge_with_own_certificates(certs_dir, acme_credentials):
    env = config(
        web={
            'host': 'localhost',
            'use_ssl': 'builtin',
            'ssl_certs': certs_dir,
            'acme_challenge': 'dns-01',
            'acme_dns_api_config': acme_credentials,
        }
    ).env()
    assert env['ACME_CHALLENGE'] == 'HTTP-01'
    assert env['ACMESH_DNS_API_CONFIG'] == ''


def test_env_without_multi_workspace():
    env = config(web={'host': 'example.com', 'use_ssl': 'builtin'}).env()
    assert env['WEB_MULTI_WORKSPACE'] == 'no'
    assert env['VIRTUAL_HOST'] == 'example.com'
    assert env['LETSENCRYPT_HOST'] == 'example.com'


def test_env_with_multi_workspace(acme_credentials):
    env = config(
        web={
            'host': 'example.com',
            'use_ssl': 'builtin',
            'acme_challenge': 'dns-01',
            'acme_dns_api_config': acme_credentials,
            'multi_workspace': 'yes',
        }
    ).env()
    assert env['WEB_MULTI_WORKSPACE'] == 'yes'
    assert env['VIRTUAL_HOST'] == 'example.com,*.example.com'
    assert env['LETSENCRYPT_HOST'] == 'example.com,*.example.com'


def test_env_keeps_the_bare_letsencrypt_host_without_multi_workspace(acme_credentials):
    env = config(
        web={
            'host': 'example.com',
            'use_ssl': 'builtin',
            'acme_challenge': 'dns-01',
            'acme_dns_api_config': acme_credentials,
        }
    ).env()
    assert env['VIRTUAL_HOST'] == 'example.com'
    assert env['LETSENCRYPT_HOST'] == 'example.com'


def test_env_derives_the_postmaster_address_from_the_domain():
    assert config(web={'host': 'teamplify.example.com'}).env()['POSTMASTER_EMAIL'] == (
        'postmaster@example.com'
    )


def test_env_keeps_the_whole_ip_in_the_postmaster_address():
    assert config(web={'host': '192.168.0.1'}).env()['POSTMASTER_EMAIL'] == (
        'postmaster@192.168.0.1'
    )


# the helpers that the rules above are built on


@pytest.mark.parametrize(
    'use_ssl,expected',
    [('no', ''), ('builtin', 'builtin'), ('external', 'external'), ('yes', 'builtin')],
)
def test_ssl_mode(use_ssl, expected):
    assert config(web={'use_ssl': use_ssl}).ssl_mode() == expected


def test_uses_letsencrypt_needs_builtin_ssl_without_certificates(certs_dir):
    assert config(web={'use_ssl': 'builtin'}).uses_letsencrypt() is True
    assert config(web={'use_ssl': 'external'}).uses_letsencrypt() is False
    assert config(web={'use_ssl': 'builtin', 'ssl_certs': certs_dir}).uses_letsencrypt() is False


def test_acme_challenge_is_normalized_to_the_companion_spelling():
    assert Configurator().acme_challenge() == 'HTTP-01'
    assert config(web={'acme_challenge': 'dns-01'}).acme_challenge() == 'DNS-01'
    assert config(web={'acme_challenge': 'DNS-01'}).acme_challenge() == 'DNS-01'


def test_multi_workspace_is_off_by_default():
    assert Configurator().multi_workspace() is False
    assert config(web={'multi_workspace': 'yes'}).multi_workspace() is True


def test_acme_dns_api_config_returns_the_file_contents(acme_credentials):
    assert config(web={'acme_dns_api_config': acme_credentials}).acme_dns_api_config() == (
        'DNS_API: dns_cf\nCF_Token: secret\n'
    )


def test_acme_dns_api_config_is_empty_when_unreadable():
    assert Configurator().acme_dns_api_config() == ''
    assert config(web={'acme_dns_api_config': '/no/such/file.yml'}).acme_dns_api_config() == ''
