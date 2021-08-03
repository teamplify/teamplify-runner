#!/usr/bin/env python3
import os
from datetime import datetime

import click

from teamplify_runner import __version__
from teamplify_runner.configurator import BASE_DIR, ConfigurationError, \
    Configurator
from teamplify_runner.utils import cd, run


IMAGES = {
    'db': 'mysql:8.0.23',
    'redis': 'redis:6.0.5',
    'nginx': 'jwilder/nginx-proxy:latest',
    'letsencrypt': 'jrcs/letsencrypt-nginx-proxy-companion:latest',
    'smtp': 'instrumentisto/postfix:3.1.3',
    'app': 'public.ecr.aws/q5a3z0t4/teamplify/server',
}


def _root_url(env):
    port = env['WEB_PORT']
    root_url = 'http://' + env['WEB_HOST']
    if port != '80':
        root_url += ':' + port
    return root_url


def _start(env):
    click.echo('Starting services...')
    run('mkdir -p %s' % env['DB_BACKUP_MOUNT'])
    with cd(BASE_DIR):
        run(
            'docker-compose up -d --remove-orphans',
            capture_output=False,
            env=env,
        )
    root_url = _root_url(env)
    click.echo(
        '\nDone. It may take a few moments for the app to come online at:\n'
        ' -> %s\n\n'
        'If it isn\'t available immediately, please check again after '
        'a minute or two. If you experience any problems with the '
        'installation, please check the Troubleshooting guide:\n'
        ' -> https://github.com/teamplify/teamplify-runner/#troubleshooting'
        '' % root_url,
    )
    if env['WEB_HOST'].lower() == 'localhost':
        click.echo(
            '\nWARNING: you\'re running Teamplify on localhost. This is '
            'probably OK if you only need to run a demo on your local machine. '
            'However, in this mode it will not be available to anyone from the '
            'network. If you\'d like to make it available on the network, you '
            'need to provide a publicly visible domain name that points to '
            'this server.',
        )


def _create_admin(env, email, full_name):
    click.echo('Creating admin...')
    cmd = 'docker exec -it teamplify_app ' \
          '/code/manage.py createadmin --email %s' % email
    if full_name:
        cmd += ' --full-name %s' % full_name
    run(cmd, capture_output=False, env=env)


def _stop(env):
    click.echo('Stopping services...')
    with cd(BASE_DIR):
        run(
            'docker-compose rm -v --stop --force',
            capture_output=False,
            env=env,
        )


def _running(env):
    with cd(BASE_DIR):
        output = run(
            'docker-compose ps -q app',
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
            ' -> %s\n'
            'To perform backup or restore operations, please use tools that '
            'connect to this DB server directly.\n\n'
            'Command aborted.' % db_host,
            err=True,
        )
        exit(1)


def _backup(env, filename=None):
    now = datetime.utcnow().replace(microsecond=0)
    default_filename = '%s_%s.sql.gz' % (
        env['DB_NAME'],
        now.isoformat('_').replace(':', '-'),
    )
    if not filename:
        target_file = default_filename
    elif os.path.isdir(filename):
        target_file = os.path.join(filename, default_filename)
    else:
        target_file = filename
    cleanup_on_error = not os.path.exists(target_file)
    try:
        run('touch %s' % target_file)  # quick check for write access
    except RuntimeError:
        exit(1)
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
    click.echo('Making backup of Teamplify DB to:\n -> %s' % target_file)
    click.echo('Please wait...')
    try:
        run('docker exec teamplify_db bash -c "{command}"'.format(
            command=command,
        ))
    except RuntimeError as e:
        if cleanup_on_error:
            run('rm %s' % target_file)
        click.echo(str(e), err=True)
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
    run('cp %s %s' % (filename, restore_mount))
    try:
        sql = (
            'docker exec -e MYSQL_PWD="{password}" teamplify_db mysql -u{user} '
            '-e "%s"'.format(
                user=env['DB_USER'],
                password=env['DB_PASSWORD'],
            )
        )
        click.echo('Dropping and re-creating the DB...')
        run(sql % ('drop database %s' % env['DB_NAME']))
        run(sql % ('create database %s' % env['DB_NAME']))
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
        run('rm %s' % restore_mount)
    click.echo('Done.')


def _remove_unused_images():
    unused_images = run(
        'docker images -f reference=%s -f dangling=true -q' % (IMAGES['app']),
        suppress_output=True,
    ).stdout_lines
    click.echo('Cleanup: %s stale image(s) found' % len(unused_images))
    if unused_images:
        # Suppress errors because it might be possible
        # that some images are still used
        run(
            'docker rmi %s' % ' '.join(unused_images),
            suppress_output=True,
            raise_on_error=False,
        )


def cli(ctx, config):
    config = Configurator(config).load()
    if config.config_path:
        click.echo('Using the configuration file at %s' % config.config_path)
    if ctx.invoked_subcommand != 'configure':
        try:
            config.validate()
        except ConfigurationError as e:
            title = 'Configuration problem'
            title += ' - ' if len(e.messages) > 1 else ':\n -> '
            click.echo('%s%s' % (title, str(e)), err=True)
            click.echo('Command aborted.', err=True)
            exit(1)
    ctx.obj['config'] = config
    env = config.env()
    for image_id, reference in IMAGES.items():
        env['IMAGE_%s' % image_id.upper()] = reference
    env['IMAGE_APP'] += ':' + env['MAIN_UPDATE_CHANNEL']
    ctx.obj['env'] = env


cli.__doc__ = 'Teamplify runner v%s' % __version__


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
    click.echo('Current configuration saved to:\n -> %s' % config.config_path)
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
    help="The email that the admin uses to sign in",
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
            ' -> %s\n'
            'Continue (y/N)? ' % filename,
        )
        if confirm.lower() != 'y':
            click.echo('DB restore cancelled, exiting')
            return
    _restore(env, filename)


def _image_id(name):
    try:
        return run(
            'docker image ls -q --no-trunc %s' % name,
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
        run('docker pull %s' % env['IMAGE_APP'], capture_output=False)
        new_image = _image_id(env['IMAGE_APP'])
        if current_image != new_image:
            _stop(env)
            _start(env)
            click.echo('')
    else:
        run('docker pull %s' % env['IMAGE_APP'])
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
        click.echo('Removing %s Docker network(s):' % len(networks))
        run('docker network rm %s' % ' '.join(networks), raise_on_error=False)
    volumes = run(
        'docker volume ls -f name=teamplify_runner* -q',
        suppress_output=True,
    ).stdout_lines
    if volumes:
        click.echo('Removing %s Docker volume(s):' % len(volumes))
        run('docker volume rm %s' % ' '.join(volumes), raise_on_error=False)
    click.echo('Removing Docker images:')
    images = []
    for image_id, reference in IMAGES.items():
        if image_id == 'app':
            for channel in ('stable', 'latest'):
                images.append('%s:%s' % (reference, channel))
        else:
            images.append(reference)
    run('docker rmi %s' % ' '.join(images), raise_on_error=False)
    click.echo('Done.')


def main():
    cli(obj={})


if __name__ == '__main__':
    main()
