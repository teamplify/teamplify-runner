#!/usr/bin/env python3
import os
import time
from datetime import datetime

import click
import requests

from teamplify_runner import __version__
from teamplify_runner.configurator import BASE_DIR, ConfigurationError, Configurator
from teamplify_runner.utils import cd, compose, run


IMAGES = {
    'db': 'mysql:8.0.29-oracle',
    'redis': 'redis:6.2.6',
    'nginx': 'jwilder/nginx-proxy:latest',
    'letsencrypt': 'jrcs/letsencrypt-nginx-proxy-companion:latest',
    'smtp': 'mikenye/postfix:3.5.9',
    'app': 'public.ecr.aws/q5a3z0t4/teamplify/server',
}


def _root_url(env):
    port = env['WEB_PORT']
    root_url = 'http://' + env['WEB_HOST']
    if port != '80':
        root_url += ':' + port
    return root_url


def _wait_for_teamplify_start(url, max_minutes=10, check_interval_seconds=1):
    click.echo('\nTeamplify will be available at {0}\n'.format(url))

    start_time = time.time()
    while time.time() < start_time + max_minutes * 60:
        seconds_since_launch = int(time.time() - start_time)
        minutes, seconds = divmod(seconds_since_launch, 60)
        # Add two spaces so we always overwrite the previous string
        click.echo(
            'Startup in progress, {0} min {1} sec ...  \r'.format(minutes, seconds),
            nl=False,
        )

        try:
            response = requests.get(url).text
        except (requests.ConnectionError, requests.Timeout):
            time.sleep(check_interval_seconds)
            continue

        if 'window.BUILD_NUMBER' in response:
            click.echo('\n\nTeamplify successfully started!')
            return
        elif any(
            marker in response
            for marker in (
                'Welcome to nginx!',
                'Teamplify is starting...',
            )
        ):
            time.sleep(check_interval_seconds)
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


def _start(env):
    click.echo('Starting services...')
    run('mkdir -p {0}'.format(env['DB_BACKUP_MOUNT']))
    with cd(BASE_DIR):
        compose(
            'up '
            '--detach '
            '--remove-orphans '
            '--scale worker_slim={worker_slim_count} '
            '--scale worker_fat={worker_fat_count}'.format(
                worker_slim_count=env['WORKER_SLIM_COUNT'],
                worker_fat_count=env['WORKER_FAT_COUNT'],
            ),
            capture_output=False,
            env=env,
        )

    if env['WEB_HOST'].lower() == 'localhost':
        click.echo(
            click.style('\nWARNING:', fg='yellow') +
            " you're running Teamplify on localhost. This is "
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
    cmd = 'docker exec teamplify_app ' \
          '/code/manage.py createadmin --email {0}'.format(email)
    if full_name:
        cmd += ' --full-name "{0}"'.format(full_name)
    run(cmd, capture_output=False, env=env)


def _stop(env):
    click.echo('Stopping services...')
    with cd(BASE_DIR):
        compose(
            'rm -v --stop --force',
            capture_output=False,
            env=env,
        )


def _running(env):
    with cd(BASE_DIR):
        output = compose(
            'ps -q app',
            suppress_output=True,
            env=env,
        ).stdout_lines
    return bool(output)


def _assert_builtin_db(env):
    db_host = env['DB_HOST']
    if db_host != Configurator.defaults['db']['host']:
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
    run('touch {0}'.format(temp_filename))
    # check for write access inside docker
    run('docker exec teamplify_db bash -c "touch {0}"'.format(target_file))
    command = (
        'MYSQL_PWD={password} mysqldump --single-transaction -u{user} '
        '-h {host} {db} | gzip > {filename}'.format(
            user=env['DB_USER'],
            password=env['DB_PASSWORD'],
            host='localhost',
            db=env['DB_NAME'],
            filename=os.path.join('/backup', default_filename),
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
    run('mv {source} {target}'.format(
        source=os.path.join(env['DB_BACKUP_MOUNT'], default_filename),
        target=target_file,
    ))
    click.echo('Done.')


def _restore(env, filename):
    click.echo('Copying the backup...')
    restore_filename = 'restore.sql.gz'
    restore_mount = os.path.join(env['DB_BACKUP_MOUNT'], restore_filename)
    run('cp {0} {1}'.format(filename, restore_mount))
    try:
        sql = (
            'docker exec -e MYSQL_PWD="{password}" teamplify_db mysql -u{user} '
            '-e "%s"'.format(
                user=env['DB_USER'],
                password=env['DB_PASSWORD'],
            )
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


def cli(ctx, config):
    config = Configurator(config).load()
    if config.config_path:
        click.echo('Using the configuration file at {0}'.format(config.config_path))
    if ctx.invoked_subcommand != 'configure':
        try:
            config.validate()
        except ConfigurationError as e:
            title = 'Configuration problem'
            title += ' - ' if len(e.messages) > 1 else ':\n -> '
            click.echo(title + str(e), err=True)
            click.echo('Command aborted.', err=True)
            exit(1)
    ctx.obj['config'] = config
    env = config.env()
    for image_id, reference in IMAGES.items():
        env['IMAGE_{0}'.format(image_id.upper())] = reference
    env['IMAGE_APP'] += ':' + env['MAIN_UPDATE_CHANNEL']
    ctx.obj['env'] = env


cli.__doc__ = 'Teamplify runner v{0}'.format(__version__)


cli = click.group()(
    click.option('--config', type=click.Path(exists=True, dir_okay=False),
                 default=None, help='Optional, config file to use')(
        click.pass_context(cli),
    ))


@cli.command()
@click.pass_context
def configure(ctx):
    """
    Interactive configuration wizard
    """
    config = ctx.obj['config']
    config.remove_unknown().dump()
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
            'Current Teamplify DB will be overwritten from:\n'
            ' -> {0}\n'
            'Continue (y/N)? '.format(filename),
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


@cli.command()
@click.pass_context
def update(ctx):
    """
    Update to the latest version
    """
    env = ctx.obj['env']
    if _running(env):
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
