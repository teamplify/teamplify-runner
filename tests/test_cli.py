import pytest
from click.testing import CliRunner

from teamplify_runner import cli
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


APP_IMAGE = 'teamplify/server:stable'
NGINX_IMAGE = 'jwilder/nginx-proxy:latest'
ENV = {
    **{f'IMAGE_{name.upper()}': f'{name}:tag' for name in cli.IMAGES},
    'IMAGE_APP': APP_IMAGE,
    'IMAGE_NGINX': NGINX_IMAGE,
    'COMPOSE_PROFILES': 'ssl,letsencrypt',
}
LOCAL_IMAGE_IDS = {
    reference: f'id-{reference}' for key, reference in ENV.items() if key.startswith('IMAGE_')
}


class CallLog(list):
    def __init__(self):
        super().__init__()
        self.running = True
        self.image_ids = dict(LOCAL_IMAGE_IDS)
        self.pulled_image_ids = {}


@pytest.fixture
def log(monkeypatch):
    """Replaces Docker interactions of the update command with a call log."""
    calls = CallLog()

    def compose(cmd, **kwargs):
        calls.append(('compose', cmd, kwargs['env']['COMPOSE_PROFILES']))
        if cmd == 'pull':
            calls.image_ids.update(calls.pulled_image_ids)

    monkeypatch.setattr(cli, 'compose', compose)
    monkeypatch.setattr(cli, '_running', lambda env: calls.running)
    monkeypatch.setattr(cli, '_image_id', lambda name: calls.image_ids.get(name))
    monkeypatch.setattr(cli, '_offer_backup', lambda env: calls.append('backup'))
    monkeypatch.setattr(cli, '_stop', lambda env: calls.append('stop'))
    monkeypatch.setattr(cli, '_start', lambda env: calls.append('start'))
    monkeypatch.setattr(cli, '_remove_replaced_images', lambda ids: calls.append(('cleanup', ids)))
    return calls


def run_update():
    result = CliRunner().invoke(cli.update, obj={'env': dict(ENV)})
    assert result.exit_code == 0, result.output


PULL = ('compose', 'pull', 'ssl,letsencrypt')
CLEANUP = ('cleanup', LOCAL_IMAGE_IDS)


def test_update_applies_changes_without_full_restart_when_app_image_is_unchanged(log):
    log.pulled_image_ids = {NGINX_IMAGE: 'id-new-nginx'}
    run_update()
    assert log == ['backup', PULL, 'start', CLEANUP]


def test_update_restarts_everything_when_app_image_changes(log):
    log.pulled_image_ids = {APP_IMAGE: 'id-new-app'}
    run_update()
    assert log == ['backup', PULL, 'stop', 'start', CLEANUP]


def test_update_only_pulls_images_when_teamplify_is_stopped(log):
    log.running = False
    log.pulled_image_ids = {APP_IMAGE: 'id-new-app'}
    run_update()
    assert log == [PULL, CLEANUP]


def test_update_cleans_up_images_missing_before_the_pull(log):
    log.image_ids.pop(NGINX_IMAGE)
    log.pulled_image_ids = {NGINX_IMAGE: 'id-new-nginx'}
    run_update()
    assert log[-1] == ('cleanup', {**LOCAL_IMAGE_IDS, NGINX_IMAGE: None})


class FakeResult:
    def __init__(self, stdout_lines):
        self.stdout_lines = stdout_lines


@pytest.fixture
def docker(monkeypatch):
    """Replaces the Docker CLI with a fake that knows a fixed set of dangling images."""
    commands = []
    dangling = ['id-old-app', 'id-old-nginx', 'id-foreign']

    def run(cmd, **kwargs):
        commands.append(cmd)
        return FakeResult(dangling if 'dangling=true' in cmd else [])

    monkeypatch.setattr(cli, 'run', run)
    return commands


def test_remove_replaced_images_removes_only_dangling_previous_images(docker):
    cli._remove_replaced_images(
        {
            APP_IMAGE: 'id-old-app',
            NGINX_IMAGE: 'id-old-nginx',
            'redis:tag': 'id-redis',
            'acme_dns:tag': None,
        },
    )
    assert docker[-1] == 'docker rmi id-old-app id-old-nginx'


def test_remove_replaced_images_skips_rmi_without_replaced_images(docker):
    cli._remove_replaced_images({APP_IMAGE: 'id-app', 'redis:tag': None})
    assert not any(cmd.startswith('docker rmi') for cmd in docker)
