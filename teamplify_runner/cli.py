#!/usr/bin/env python3
import json
import os
import re
import shlex
import sys
import time
from datetime import datetime

import click
import requests

from teamplify_runner import __version__, acme_dns
from teamplify_runner.configurator import BASE_DIR, ConfigurationError, Configurator
from teamplify_runner.utils import cd, compose, run
from teamplify_runner.version_checker import get_latest_version, is_update_available


IMAGES = {
    'db': 'mysql:8.4.9-oracle',
    'redis': 'redis:6.2.6',
    'nginx': 'jwilder/nginx-proxy:latest',
    'letsencrypt': 'jrcs/letsencrypt-nginx-proxy-companion:latest',
    'acme_dns': 'joohoi/acme-dns:v2.0.2',
    'smtp': 'mikenye/postfix:3.5.9',
    'app': 'public.ecr.aws/q5a3z0t4/teamplify/server',
}

ACME_DNS_CONTAINER = 'teamplify_acme_dns'
# Kept in the acme-dns volume next to its database, so that both are lost or
# kept together
ACME_DNS_CREDENTIALS = '/var/lib/acme-dns/teamplify-credentials.json'
ACME_DNS_VERIFIED = '/var/lib/acme-dns/teamplify-verified'


def _root_url(env):
    use_ssl = env.get('WEB_USE_SSL', '').lower()
    if use_ssl in ('builtin', 'external', 'yes', 'true', '1'):
        return 'https://' + env['WEB_HOST']
    port = env['WEB_PORT']
    root_url = 'http://' + env['WEB_HOST']
    if port != '80':
        root_url += ':' + port
    return root_url


def _wait_for_teamplify_start(url, max_minutes=10, check_interval_seconds=1):
    click.echo('\nTeamplify will be available at {0}\n'.format(url))

    status = 'Connecting'
    start_time = time.time()
    while time.time() < start_time + max_minutes * 60:
        seconds_since_launch = int(time.time() - start_time)
        minutes, seconds = divmod(seconds_since_launch, 60)
        # Add two spaces so we always overwrite the previous string
        click.echo(
            '{0}, {1} min {2} sec ...  \r'.format(status, minutes, seconds),
            nl=False,
        )
        time.sleep(check_interval_seconds)

        try:
            response = requests.get(url).text
        except (requests.ConnectionError, requests.Timeout):
            status = 'Connecting'
            continue

        if re.search(r"window.BUILD_NUMBER = '\d+'", response):
            click.echo('\n\nTeamplify successfully started!')
            return
        elif 'Welcome to nginx!' in response:
            status = 'Started nginx'
            continue
        elif 'Teamplify is starting...' in response:
            status = 'Teamplify is starting'
            continue
        else:
            raise RuntimeError(
                '\n\nUnexpected response from Teamplify: {0}\n\n'
                'Please check the Troubleshooting guide:\n -> '
                'https://github.com/teamplify/teamplify-runner/#troubleshooting'.format(response)
            )

    raise RuntimeError(
        "\n\nTeamplify didn't start in {0} minutes. "
        'Please check the Troubleshooting guide:\n'
        ' -> https://github.com/teamplify/teamplify-runner/#troubleshooting'.format(max_minutes)
    )


def _acme_dns_exec(command, input=None):
    # Only attach stdin when there is something to send: an attached terminal
    # would otherwise swallow what the administrator types at the next prompt
    interactive = '-i ' if input is not None else ''
    return run(
        f'docker exec {interactive}{ACME_DNS_CONTAINER} {command}',
        input=input,
        suppress_output=True,
        raise_on_error=False,
    )


def _start_acme_dns(env):
    with cd(BASE_DIR):
        started = compose(
            'up --detach acme_dns',
            capture_output=False,
            env=env,
            raise_on_error=False,
        )
    if started.returncode != 0:
        click.echo(
            "\nCan't start the acme-dns server. It answers the DNS queries of the "
            'certificate authority, so it needs port 53 of this machine, over both UDP '
            'and TCP. A local DNS resolver is the usual reason for the port to be busy. '
            'On a host running systemd-resolved, free it with all three of:\n'
            ' -> set DNSStubListener=no in /etc/systemd/resolved.conf\n'
            ' -> ln -sf /run/systemd/resolve/resolv.conf /etc/resolv.conf\n'
            ' -> systemctl restart systemd-resolved',
            err=True,
        )
        exit(1)


def _acme_dns_credentials(env):
    _start_acme_dns(env)

    stored = _acme_dns_exec(f'cat {ACME_DNS_CREDENTIALS}')
    if stored.returncode == 0:
        try:
            return acme_dns.parse_credentials('\n'.join(stored.stdout_lines))
        except ValueError as e:
            click.echo(
                f'The stored acme-dns credentials are damaged: {e}\n'
                f'Remove {ACME_DNS_CREDENTIALS} from the {ACME_DNS_CONTAINER} container '
                'to register again. The _acme-challenge CNAME record will have to be '
                'changed after that.',
                err=True,
            )
            exit(1)

    # The API may take a moment to come up after the container starts
    for _ in range(30):
        response = _acme_dns_exec('wget -qO- --post-data= http://127.0.0.1/register')
        if response.returncode == 0:
            break
        time.sleep(1)
    else:
        click.echo("Can't register in acme-dns. Its own log follows:\n", err=True)
        run(
            f'docker logs --tail 50 {ACME_DNS_CONTAINER}',
            capture_output=False,
            raise_on_error=False,
        )
        exit(1)

    credentials = acme_dns.parse_credentials('\n'.join(response.stdout_lines))
    saved = _acme_dns_exec(
        f"sh -c 'cat > {ACME_DNS_CREDENTIALS}'",
        input=acme_dns.dump_credentials(credentials),
    )
    if saved.returncode != 0:
        click.echo("Can't store the acme-dns credentials", err=True)
        exit(1)
    return credentials


def _acme_dns_lookup(env, record_type, name):
    result = run(
        f'docker run --rm --entrypoint dig {env["IMAGE_LETSENCRYPT"]} '
        f'+short +time=5 +tries=2 {record_type} {name} @{acme_dns.PUBLIC_RESOLVER}',
        suppress_output=True,
        raise_on_error=False,
    )
    if result.returncode != 0:
        # A query that never reached the resolver tells us nothing about the
        # records, so it must not be reported as a missing one
        details = ' '.join(line for line in result.stdout_lines if line.strip())
        raise acme_dns.LookupFailed(
            f"Can't look up the {record_type} record of {name} through the public resolver "
            f'{acme_dns.PUBLIC_RESOLVER}: {details or "the query failed"}. This machine has '
            'to be able to send DNS queries to the Internet over port 53 to check the '
            'records, and Docker has to be able to run the '
            f'{env["IMAGE_LETSENCRYPT"]} image',
        )
    return result.stdout_lines


def _acme_dns_publish(credentials, value):
    data = json.dumps({'subdomain': credentials.subdomain, 'txt': value})
    result = _acme_dns_exec(
        'wget -qO- '
        f'--header {shlex.quote(f"X-Api-User: {credentials.username}")} '
        f'--header {shlex.quote(f"X-Api-Key: {credentials.password}")} '
        "--header 'Content-Type: application/json' "
        f'--post-data {shlex.quote(data)} '
        'http://127.0.0.1/update',
    )
    if result.returncode != 0:
        click.echo("Can't publish a test record in acme-dns", err=True)
        exit(1)


def _acme_dns_verified(credentials):
    """
    Whether the DNS records were already confirmed to work for exactly these
    credentials. The marker holds the name the CNAME record has to point at, so
    that credentials issued by a later registration are checked again instead
    of inheriting the confirmation given to the previous ones.
    """
    marker = _acme_dns_exec(f'cat {ACME_DNS_VERIFIED}')
    if marker.returncode != 0:
        return False
    return '\n'.join(marker.stdout_lines).strip() == credentials.fulldomain


def _mark_acme_dns_verified(credentials):
    saved = _acme_dns_exec(
        f"sh -c 'cat > {ACME_DNS_VERIFIED}'",
        input=credentials.fulldomain,
    )
    if saved.returncode != 0:
        click.echo(
            "Can't save the result of the DNS check, it will run again on the next start.",
            err=True,
        )


def _setup_acme_dns(env):
    """
    Get the acme-dns server ready and hand its credentials over to the Let's
    Encrypt companion. Until the DNS records are confirmed to work, walk the
    administrator through adding them.
    """
    credentials = _acme_dns_credentials(env)
    env['ACMESH_DNS_API_CONFIG'] = acme_dns.acmesh_dns_api_config(credentials)
    if _acme_dns_verified(credentials):
        return

    host = env['WEB_HOST']
    records = '\n'.join(f' -> {record}' for record in acme_dns.required_records(host, credentials))
    while True:
        click.echo('Checking the DNS records for acme-dns...')
        problems = acme_dns.find_problems(
            host,
            credentials,
            lookup=lambda record_type, name: _acme_dns_lookup(env, record_type, name),
            publish_txt=lambda value: _acme_dns_publish(credentials, value),
        )
        if not problems:
            _mark_acme_dns_verified(credentials)
            click.echo('The DNS records for acme-dns are in place.\n')
            return

        click.echo(
            '\nTo obtain certificates through acme-dns, add these records to the '
            f'DNS zone of {host}. This is only needed once:\n\n'
            f'{records}\n\n'
            f'The A record of {host} must point to this server, and port 53 of '
            'this server must be open to the Internet over both UDP and TCP. '
            'DNS changes may take a while to become visible.\n\n'
            'Problems found:\n' + '\n'.join(f' -> {problem}' for problem in problems) + '\n',
        )
        if not sys.stdin.isatty():
            click.echo('Add the records and run the command again.', err=True)
            exit(1)
        if not click.confirm('Check the records again?', default=True):
            exit(1)


def _start(env):
    click.echo('Starting services...')
    run('mkdir -p {0}'.format(env['DB_BACKUP_MOUNT']))
    if 'acme-dns' in env['COMPOSE_PROFILES'].split(','):
        _setup_acme_dns(env)
    with cd(BASE_DIR):
        web_count = int(env['WEB_COUNT'])
        app_replica_count = web_count - 1
        fat_count = int(env['WORKER_FAT_COUNT'])
        worker_fat_penalized_count = 1 if fat_count > 0 else 0
        worker_fat_count = (fat_count - worker_fat_penalized_count) if fat_count > 0 else 0
        compose(
            'up '
            '--detach '
            '--remove-orphans '
            '--scale app_replica={app_replica_count} '
            '--scale worker_slim={worker_slim_count} '
            '--scale worker_fat_penalized={worker_fat_penalized_count} '
            '--scale worker_fat={worker_fat_count}'.format(
                app_replica_count=app_replica_count,
                worker_slim_count=env['WORKER_SLIM_COUNT'],
                worker_fat_penalized_count=worker_fat_penalized_count,
                worker_fat_count=worker_fat_count,
            ),
            capture_output=False,
            env=env,
        )

    if env['WEB_HOST'].lower() == 'localhost':
        click.echo(
            click.style('\nWARNING:', fg='yellow')
            + " you're running Teamplify on localhost. This is "
            'probably OK if you only need to run a demo on your local machine. '
            'However, in this mode it will not be available to anyone from the '
            "network. If you'd like to make it available on the network, you "
            'need to provide a publicly visible domain name that points to '
            'this server.',
        )

    root_url = _root_url(env)
    try:
        _wait_for_teamplify_start(root_url)
    except RuntimeError as e:
        click.echo(click.style(str(e), fg='red'))
        exit(1)


def _create_admin(env, email, full_name):
    click.echo('Creating admin...')
    cmd = 'docker exec teamplify_app /code/manage.py createadmin --email {0}'.format(email)
    if full_name:
        cmd += ' --full-name "{0}"'.format(full_name)
    run(cmd, capture_output=False, env=env)


def _stop(env):
    click.echo('Stopping services...')
    with cd(BASE_DIR):
        compose(
            'rm -v --stop --force',
            capture_output=False,
            env={**env, 'COMPOSE_PROFILES': '*'},
        )


def _running(env):
    with cd(BASE_DIR):
        output = compose(
            'ps -q app',
            suppress_output=True,
            env=env,
        ).stdout_lines
    return bool(output)


def _assert_builtin_db(env, exit_on_error=True):
    db_host = env['DB_HOST']
    if db_host != Configurator.defaults['db']['host']:
        if exit_on_error:
            click.echo(
                '\nWe are sorry, but the "teamplify backup" and '
                '"teamplify restore" commands are designed to work with '
                '"builtin_db" only. The current configuration specifies an '
                'external DB at:\n'
                ' -> {0}\n'
                'To perform backup or restore operations, please use tools that '
                'connect to this DB server directly.\n\n'
                'Command aborted.'.format(db_host),
                err=True,
            )
            exit(1)
        return False

    return True


def _backup(env, filename=None):
    now = datetime.utcnow().replace(microsecond=0)
    default_filename = '{0}_{1}.sql.gz'.format(
        env['DB_NAME'],
        now.isoformat('_').replace(':', '-'),
    )
    if not filename:
        target_file = default_filename
    elif os.path.isdir(filename):
        target_file = os.path.join(filename, default_filename)
    else:
        target_file = filename
    temp_filename = os.path.join('/backup', default_filename)
    cleanup_on_error = not os.path.exists(target_file)
    # check for write access on the host
    run('touch {0}'.format(target_file))
    # check for write access inside docker
    run('docker exec teamplify_db bash -c "touch {0}"'.format(temp_filename))
    command = (
        'MYSQL_PWD={password} mysqldump --single-transaction -u{user} '
        '-h {host} {db} | gzip > {filename}'.format(
            user=env['DB_USER'],
            password=env['DB_PASSWORD'],
            host='localhost',
            db=env['DB_NAME'],
            filename=temp_filename,
        )
    )
    click.echo('Making backup of Teamplify DB to:\n -> {0}'.format(target_file))
    click.echo('Please wait...')
    try:
        run(
            'docker exec teamplify_db bash -c "{command}"'.format(
                command=command,
            ),
            exit_on_error=False,
        )
    except RuntimeError:
        if cleanup_on_error:
            run('rm {0}'.format(target_file))
        exit(1)
    run(
        'mv {source} {target}'.format(
            source=os.path.join(env['DB_BACKUP_MOUNT'], default_filename),
            target=target_file,
        )
    )
    click.echo('Done.')


def _restore(env, filename):
    click.echo('Copying the backup...')
    restore_filename = 'restore.sql.gz'
    restore_mount = os.path.join(env['DB_BACKUP_MOUNT'], restore_filename)
    run('cp {0} {1}'.format(filename, restore_mount))
    try:
        sql = 'docker exec -e MYSQL_PWD="{password}" teamplify_db mysql -u{user} -e "%s"'.format(
            user=env['DB_USER'],
            password=env['DB_PASSWORD'],
        )
        click.echo('Dropping and re-creating the DB...')
        run(sql % ('drop database {0}'.format(env['DB_NAME'])))
        run(sql % ('create database {0}'.format(env['DB_NAME'])))
        click.echo('Restoring DB backup...')
        run(
            'docker exec -e MYSQL_PWD="{password}" teamplify_db bash -c "'
            'gunzip < {filename} | mysql -u{user} {db}"'.format(
                filename='/'.join(('/backup', restore_filename)),
                user=env['DB_USER'],
                password=env['DB_PASSWORD'],
                db=env['DB_NAME'],
            ),
        )
    finally:
        run('rm {0}'.format(restore_mount))
    click.echo('Done.')


def _remove_unused_images():
    unused_images = run(
        'docker images -f reference={0} -f dangling=true -q'.format(IMAGES['app']),
        suppress_output=True,
    ).stdout_lines
    click.echo('Cleanup: {0} stale image(s) found'.format(len(unused_images)))
    if unused_images:
        # Suppress errors because it might be possible
        # that some images are still used
        run(
            'docker rmi {0}'.format(' '.join(unused_images)),
            suppress_output=True,
            raise_on_error=False,
        )


def _check_for_updates():
    latest_version = get_latest_version()
    if not latest_version or not is_update_available(__version__, latest_version):
        return

    click.echo(
        click.style('A new version of Teamplify runner is available: ', fg='yellow')
        + 'v{0} (you have v{1}).'.format(latest_version, __version__),
    )
    update_hint = 'To update Teamplify runner, run:\n -> pip3 install -U teamplify\n'
    if not sys.stdin.isatty():
        click.echo(update_hint)
        return
    if click.confirm(
        'Would you like to stop the current command and update now?',
        default=True,
    ):
        click.echo(update_hint)
        exit(0)


def _abort_on_configuration_error(error):
    title = 'Configuration problem'
    title += ' - ' if len(error.messages) > 1 else ':\n -> '
    click.echo(title + str(error), err=True)
    click.echo('Command aborted.', err=True)
    exit(1)


def cli(ctx, config):
    try:
        _check_for_updates()
    except click.exceptions.Abort:
        # In case the user stopped the process reraise the error
        raise
    except Exception:
        # But the rest of the updates check errors should never break the CLI
        pass

    config = Configurator(config).load()
    if config.config_path:
        click.echo('Using the configuration file at {0}'.format(config.config_path))
    if ctx.invoked_subcommand != 'configure':
        try:
            config.validate()
        except ConfigurationError as e:
            _abort_on_configuration_error(e)
        for warning in config.warnings():
            click.echo(click.style('WARNING: ', fg='yellow') + warning)
    ctx.obj['config'] = config
    env = config.env()
    for image_id, reference in IMAGES.items():
        env['IMAGE_{0}'.format(image_id.upper())] = reference
    env['IMAGE_APP'] += ':' + env['MAIN_UPDATE_CHANNEL']
    ctx.obj['env'] = env


cli.__doc__ = 'Teamplify runner v{0}'.format(__version__)


cli = click.group()(
    click.option(
        '--config',
        type=click.Path(exists=True, dir_okay=False),
        default=None,
        help='Optional, config file to use',
    )(
        click.pass_context(cli),
    )
)


@cli.command()
@click.pass_context
def configure(ctx):
    """
    Interactive configuration wizard
    """
    config = ctx.obj['config']
    try:
        config.remove_unknown().dump()
    except ConfigurationError as e:
        _abort_on_configuration_error(e)
    click.echo('Current configuration saved to:\n -> {0}'.format(config.config_path))
    click.echo(
        '\nThe file above contains the full list of configurable options. '
        'Please use your favorite text editor to adjust them as necessary. '
        'When ready, run the following command to verify and apply your '
        'changes:\n'
        ' -> teamplify restart',
    )


@cli.command()
@click.pass_context
def start(ctx):
    """
    Start Teamplify
    """
    _start(ctx.obj['env'])


@cli.command()
@click.pass_context
@click.option(
    '--email',
    required=True,
    help='The email that the admin uses to sign in',
)
@click.option(
    '--full-name',
    'full_name',
    required=False,
    help="Admin's full name",
)
def createadmin(ctx, email, full_name):
    """
    Create an admin
    """
    _create_admin(ctx.obj['config'].env(), email, full_name)


@cli.command()
@click.pass_context
def stop(ctx):
    """
    Stop Teamplify
    """
    _stop(ctx.obj['env'])


@cli.command()
@click.pass_context
def restart(ctx):
    """
    Restart Teamplify
    """
    env = ctx.obj['env']
    _stop(env)
    _start(env)


@cli.command()
@click.argument('filename', required=False)
@click.pass_context
def backup(ctx, filename):
    """
    Backup Teamplify DB to a GZipped archive
    """
    env = ctx.obj['env']
    _assert_builtin_db(env)
    _backup(env, filename)


@cli.command()
@click.argument('filename', type=click.Path(exists=True))
@click.option('--quiet', 'quiet', flag_value='quiet', default=None)
@click.pass_context
def restore(ctx, filename, quiet):
    """
    Restore Teamplify DB from a GZipped archive
    """
    env = ctx.obj['env']
    _assert_builtin_db(env)
    if not quiet:
        confirm = input(
            'Current Teamplify DB will be overwritten from:\n -> {0}\nContinue (y/N)? '.format(
                filename
            ),
        )
        if confirm.lower() != 'y':
            click.echo('DB restore cancelled, exiting')
            return
    _restore(env, filename)


def _image_id(name):
    try:
        return run(
            'docker image ls -q --no-trunc {0}'.format(name),
            suppress_output=True,
        ).stdout_lines[0]
    except IndexError:
        return None


def _offer_backup(env):
    # Don't offer to do a backup if an external DB is used
    if not _assert_builtin_db(env, exit_on_error=False):
        return

    if not sys.stdin.isatty() or click.confirm(
        'Would you like to backup the Teamplify DB before updating?',
        default=True,
    ):
        _backup(env)
        click.echo('')


@cli.command()
@click.pass_context
def update(ctx):
    """
    Update to the latest version
    """
    env = ctx.obj['env']
    if _running(env):
        _offer_backup(env)
        current_image = _image_id(env['IMAGE_APP'])
        run('docker pull {0}'.format(env['IMAGE_APP']), capture_output=False)
        new_image = _image_id(env['IMAGE_APP'])
        if current_image != new_image:
            _stop(env)
            _start(env)
            click.echo('')
    else:
        run('docker pull {0}'.format(env['IMAGE_APP']))
    _remove_unused_images()
    click.echo('Done.')


@cli.command()
@click.option('--quiet', 'quiet', flag_value='quiet', default=None)
@click.pass_context
def erase(ctx, quiet):
    """
    Erase all of Teamplify data and Docker images
    """
    if not quiet:
        confirm = input(
            '\nIMPORTANT: This command will erase all of the data stored in '
            'the built-in Teamplify DB, and also remove all Docker images, '
            'volumes, and networks used by Teamplify.\n\n'
            'Do you want to confirm the deletion of all Teamplify data (y/N)? ',
        )
        if confirm.lower() != 'y':
            click.echo('Erase command cancelled, exiting')
            return
    env = ctx.obj['env']
    _stop(env)
    click.echo('')
    networks = run(
        'docker network ls -f name=teamplify_runner* -q',
        suppress_output=True,
    ).stdout_lines
    if networks:
        click.echo('Removing {0} Docker network(s):'.format(len(networks)))
        run('docker network rm {0}'.format(' '.join(networks)), raise_on_error=False)
    volumes = run(
        'docker volume ls -f name=teamplify_runner* -q',
        suppress_output=True,
    ).stdout_lines
    if volumes:
        click.echo('Removing {0} Docker volume(s):'.format(len(volumes)))
        run('docker volume rm {0}'.format(' '.join(volumes)), raise_on_error=False)
    click.echo('Removing Docker images:')
    images = []
    for image_id, reference in IMAGES.items():
        if image_id == 'app':
            for channel in ('stable', 'latest'):
                images.append('{0}:{1}'.format(reference, channel))
        else:
            images.append(reference)
    run('docker rmi {0}'.format(' '.join(images)), raise_on_error=False)
    click.echo('Done.')


def main():
    cli(obj={})


if __name__ == '__main__':
    main()
