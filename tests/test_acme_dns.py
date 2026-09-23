import re
from collections import defaultdict

import pytest

from teamplify_runner import acme_dns


CREDENTIALS = acme_dns.Credentials(
    username='eabcdb41-d89f-4580-826f-3e62e9755ef2',
    password='pbAXVjlIOE01xbut7YnAbkhMQIkcwoHO0ek2j4Q0',
    subdomain='d420c923-bbd7-4056-ab64-c3ca54c9b3cf',
    fulldomain='d420c923-bbd7-4056-ab64-c3ca54c9b3cf._acme.example.com',
)


def test_zone_is_delegated_under_the_host():
    assert acme_dns.zone('Teamplify.Example.com') == '_acme.teamplify.example.com'


def test_server_config():
    expected = """\
[general]
listen = "0.0.0.0:53"
protocol = "both"
domain = "_acme.example.com"
nsname = "example.com"
nsadmin = "hostmaster.example.com"
records = [
    "_acme.example.com. NS example.com.",
]
debug = false

[database]
engine = "sqlite"
connection = "/var/lib/acme-dns/acme-dns.db"

[api]
ip = "0.0.0.0"
port = "80"
tls = "none"
disable_registration = false
corsorigins = []
use_header = false
header_name = "X-Forwarded-For"

[logconfig]
loglevel = "info"
logtype = "stdout"
logformat = "text"
"""
    assert acme_dns.server_config('Example.com') == expected


def test_required_records():
    assert [str(record) for record in acme_dns.required_records('example.com', CREDENTIALS)] == [
        '_acme.example.com. NS example.com.',
        '_acme-challenge.example.com. CNAME '
        'd420c923-bbd7-4056-ab64-c3ca54c9b3cf._acme.example.com.',
    ]


def test_credentials_survive_a_round_trip():
    assert acme_dns.parse_credentials(acme_dns.dump_credentials(CREDENTIALS)) == CREDENTIALS


def test_credentials_are_read_from_a_registration_response():
    response = (
        '{"username":"eabcdb41-d89f-4580-826f-3e62e9755ef2",'
        '"password":"pbAXVjlIOE01xbut7YnAbkhMQIkcwoHO0ek2j4Q0",'
        '"fulldomain":"d420c923-bbd7-4056-ab64-c3ca54c9b3cf._acme.example.com",'
        '"subdomain":"d420c923-bbd7-4056-ab64-c3ca54c9b3cf","allowfrom":[]}'
    )
    assert acme_dns.parse_credentials(response) == CREDENTIALS


@pytest.mark.parametrize(
    'text,message',
    [
        ('not json', 'Not a JSON document'),
        ('[]', 'Expected a JSON object'),
        ('{"username": "u", "password": ""}', 'Missing fields: password, subdomain, fulldomain'),
    ],
)
def test_incomplete_credentials_are_rejected(text, message):
    with pytest.raises(ValueError) as raised:
        acme_dns.parse_credentials(text)
    assert str(raised.value).startswith(message)


def test_acmesh_dns_api_config():
    assert acme_dns.acmesh_dns_api_config(CREDENTIALS) == (
        'DNS_API: "dns_acmedns"\n'
        'ACMEDNS_BASE_URL: "http://acme-dns"\n'
        'ACMEDNS_USERNAME: "eabcdb41-d89f-4580-826f-3e62e9755ef2"\n'
        'ACMEDNS_PASSWORD: "pbAXVjlIOE01xbut7YnAbkhMQIkcwoHO0ek2j4Q0"\n'
        'ACMEDNS_SUBDOMAIN: "d420c923-bbd7-4056-ab64-c3ca54c9b3cf"\n'
    )


def test_probe_token_has_the_format_acme_dns_accepts():
    assert re.fullmatch(r'[A-Za-z0-9_-]{43}', acme_dns.probe_token())


def test_txt_values_skip_the_followed_cname():
    output = [
        'd420c923-bbd7-4056-ab64-c3ca54c9b3cf._acme.example.com.',
        '"first"',
        '"second"',
    ]
    assert acme_dns.txt_values(output) == ['first', 'second']


class FakeDns:
    """A public resolver view of the zone, where published TXT values show up after a delay."""

    def __init__(self, cname=None, nameserver=None, visible_after=0, reachable=True):
        self.records = defaultdict(list)
        self.records[('CNAME', '_acme-challenge.example.com')] = [cname] if cname else []
        self.records[('NS', '_acme.example.com')] = [nameserver] if nameserver else []
        self.visible_after = visible_after
        self.reachable = reachable
        self.published = []
        self.txt_lookups = 0

    def lookup(self, record_type, name):
        if record_type == 'TXT':
            self.txt_lookups += 1
            if not self.reachable or self.txt_lookups <= self.visible_after:
                return []
            return [f'{CREDENTIALS.fulldomain}.'] + [f'"{value}"' for value in self.published]
        return self.records[(record_type, name)]

    def find_problems(self):
        return acme_dns.find_problems(
            'example.com',
            CREDENTIALS,
            lookup=self.lookup,
            publish_txt=self.published.append,
            attempts=3,
            sleep=lambda seconds: None,
        )


def delegated(**kwargs):
    return FakeDns(cname=f'{CREDENTIALS.fulldomain}.', nameserver='example.com.', **kwargs)


def test_a_working_delegation_has_no_problems():
    dns = delegated()
    assert dns.find_problems() == []
    assert len(dns.published) == 1


def test_a_published_value_is_waited_for():
    dns = delegated(visible_after=2)
    assert dns.find_problems() == []
    assert dns.txt_lookups == 3


def test_a_value_that_never_shows_up_is_reported():
    dns = delegated(reachable=False)
    assert dns.find_problems() == [
        'A test value published in acme-dns did not show up at _acme-challenge.example.com. '
        'Make sure that port 53 of this server is open to the Internet over both UDP and TCP',
    ]
    assert dns.txt_lookups == 3


def test_missing_records_are_reported_without_publishing_anything():
    dns = FakeDns()
    assert dns.find_problems() == [
        '_acme-challenge.example.com must be a CNAME to '
        'd420c923-bbd7-4056-ab64-c3ca54c9b3cf._acme.example.com., found nothing',
        '_acme.example.com must be delegated with an NS record to example.com., found nothing. '
        'If the record is in place, make sure that port 53 of this server is open to the '
        'Internet over both UDP and TCP',
    ]
    assert dns.published == []


def test_a_wrong_cname_is_reported_with_what_was_found():
    dns = FakeDns(cname='elsewhere.example.net.', nameserver='example.com.')
    assert dns.find_problems() == [
        '_acme-challenge.example.com must be a CNAME to '
        'd420c923-bbd7-4056-ab64-c3ca54c9b3cf._acme.example.com., found elsewhere.example.net.',
    ]


def test_records_are_compared_case_insensitively():
    dns = FakeDns(cname=f'{CREDENTIALS.fulldomain.upper()}.', nameserver='EXAMPLE.COM.')
    assert dns.find_problems() == []
