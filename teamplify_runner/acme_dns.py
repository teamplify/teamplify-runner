"""
Certificates for installations whose DNS has no API, through a self-hosted
acme-dns server.

The administrator delegates a small zone, `_acme.<host>`, to this server once
and points `_acme-challenge.<host>` at a name inside it. From then on the
DNS-01 challenges are answered by acme-dns running next to Teamplify, so
certificates, the wildcard one included, are issued and renewed without anyone
touching the main DNS again.

This module holds the parts that don't talk to Docker: the acme-dns server
configuration, the records the administrator has to add, the configuration
handed over to the Let's Encrypt companion, and the check that the delegation
works from the public Internet.
"""

import json
import secrets
import time
from typing import Callable, List, NamedTuple


ZONE_LABEL = '_acme'

# Where the other containers of the installation reach the acme-dns API. The
# API is never published outside of the Docker network
API_URL = 'http://acme-dns'

# The checks go through a public resolver, so that they see what a certificate
# authority validating the domain from the Internet sees
PUBLIC_RESOLVER = '1.1.1.1'


class LookupFailed(Exception):
    """
    A DNS query could not be made at all, which says nothing about the records
    themselves. Its message explains what went wrong.
    """


class Credentials(NamedTuple):
    """The account that acme-dns issues on registration."""

    username: str
    password: str
    subdomain: str
    fulldomain: str


class Record(NamedTuple):
    """A DNS record, in the form it is added to a zone."""

    name: str
    type: str
    value: str

    def __str__(self) -> str:
        return f'{self.name} {self.type} {self.value}'


def zone(host: str) -> str:
    """The zone delegated to acme-dns for the given Teamplify host."""
    return f'{ZONE_LABEL}.{host.lower()}'


def challenge_name(host: str) -> str:
    return f'_acme-challenge.{host.lower()}'


def server_config(host: str) -> str:
    """
    The acme-dns configuration for the given host.

    The zone is delegated to the host itself, so the administrator only adds
    the NS and CNAME records: the A record of the host already points to this
    server.
    """
    host = host.lower()
    delegated = zone(host)
    return f"""\
[general]
listen = "0.0.0.0:53"
protocol = "both"
domain = "{delegated}"
nsname = "{host}"
nsadmin = "hostmaster.{host}"
records = [
    "{delegated}. NS {host}.",
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


def required_records(host: str, credentials: Credentials) -> List[Record]:
    """The records the administrator adds to the main DNS zone, once."""
    return [
        Record(f'{zone(host)}.', 'NS', f'{host.lower()}.'),
        Record(f'{challenge_name(host)}.', 'CNAME', f'{credentials.fulldomain}.'),
    ]


def parse_credentials(text: str) -> Credentials:
    """
    Read the credentials from a registration response or from the stored copy.
    Raises ValueError when the text is not a complete set of credentials.
    """
    try:
        data = json.loads(text)
    except ValueError as e:
        raise ValueError(f'Not a JSON document: {e}')
    if not isinstance(data, dict):
        raise ValueError('Expected a JSON object')
    missing = [field for field in Credentials._fields if not data.get(field)]
    if missing:
        raise ValueError(f'Missing fields: {", ".join(missing)}')
    return Credentials(**{field: str(data[field]) for field in Credentials._fields})


def dump_credentials(credentials: Credentials) -> str:
    return json.dumps(credentials._asdict())


def acmesh_dns_api_config(credentials: Credentials) -> str:
    """The DNS API configuration that the Let's Encrypt companion passes to acme.sh."""
    values = {
        'DNS_API': 'dns_acmedns',
        'ACMEDNS_BASE_URL': API_URL,
        'ACMEDNS_USERNAME': credentials.username,
        'ACMEDNS_PASSWORD': credentials.password,
        'ACMEDNS_SUBDOMAIN': credentials.subdomain,
    }
    # JSON strings are valid YAML double-quoted scalars
    return ''.join(f'{name}: {json.dumps(value)}\n' for name, value in values.items())


def probe_token() -> str:
    """A throwaway TXT value in the exact format acme-dns accepts: 43 base64url characters."""
    return secrets.token_urlsafe(32)


def txt_values(lookup_output: List[str]) -> List[str]:
    """
    The TXT values in `dig +short` output. A recursive resolver prints the
    CNAME it followed first, so only the quoted lines are values.
    """
    return [line.strip().strip('"') for line in lookup_output if line.strip().startswith('"')]


def find_problems(
    host: str,
    credentials: Credentials,
    lookup: Callable[[str, str], List[str]],
    publish_txt: Callable[[str], None],
    attempts: int = 6,
    delay: float = 5,
    sleep: Callable[[float], None] = time.sleep,
) -> List[str]:
    """
    Check through a public resolver that the delegation works, and return a
    description of every problem found. An empty list means that a
    certificate authority will be able to validate the domain.

    `lookup(type, name)` returns the `dig +short` output lines for a query and
    raises `LookupFailed` when the query itself could not be made, and
    `publish_txt(value)` sets a TXT value in acme-dns. The last check publishes
    a throwaway value and waits for it to come back through the CNAME, which
    is exactly the path a certificate authority takes.
    """
    try:
        return _find_problems(host, credentials, lookup, publish_txt, attempts, delay, sleep)
    except LookupFailed as e:
        return [str(e)]


def _find_problems(host, credentials, lookup, publish_txt, attempts, delay, sleep):
    problems = []

    expected_target = f'{credentials.fulldomain}.'.lower()
    targets = [line.strip().lower() for line in lookup('CNAME', challenge_name(host))]
    if expected_target not in targets:
        found = ', '.join(targets) if targets else 'nothing'
        problems.append(
            f'{challenge_name(host)} must be a CNAME to {expected_target}, found {found}',
        )

    expected_nameserver = f'{host.lower()}.'
    nameservers = [line.strip().lower() for line in lookup('NS', zone(host))]
    if expected_nameserver not in nameservers:
        found = ', '.join(nameservers) if nameservers else 'nothing'
        problems.append(
            f'{zone(host)} must be delegated with an NS record to {expected_nameserver}, '
            f'found {found}. If the record is in place, make sure that port 53 of this '
            'server is open to the Internet over both UDP and TCP',
        )

    if problems:
        return problems

    token = probe_token()
    publish_txt(token)
    for attempt in range(attempts):
        if token in txt_values(lookup('TXT', challenge_name(host))):
            return []
        if attempt < attempts - 1:
            sleep(delay)
    return [
        f'A test value published in acme-dns did not show up at {challenge_name(host)}. '
        'Make sure that port 53 of this server is open to the Internet over both UDP '
        'and TCP',
    ]
