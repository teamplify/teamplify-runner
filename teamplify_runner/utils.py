import contextlib
import os
import random
import string
import traceback

import click
import sarge


@contextlib.contextmanager
def cd(path):
    cwd = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(cwd)


def run(cmd, raise_on_error=True, capture_output=True, suppress_output=False,
        exit_on_error=True, **kwargs):
    """
    Wrapper around sarge.run that can raise errors and capture stdout.
    """
    def echo_output(stdout, stderr):
        if stdout:
            click.echo(stdout)
        if stderr:
            click.echo(stderr, err=True)

    if capture_output:
        kwargs['stdout'] = sarge.Capture()
        kwargs['stderr'] = sarge.Capture()
    result = sarge.run(cmd, **kwargs)
    code = result.returncode
    if code and raise_on_error:
        if capture_output:
            echo_output(result.stdout.read(), result.stderr.read())
        # print two last traceback records: current line and run caller
        traceback.print_stack(limit=2)
        msg = 'Command failed, exit code {0}'.format(code)
        if exit_on_error:
            click.echo(msg)
            exit(1)
        else:
            raise RuntimeError(msg)
    if capture_output:
        stdout = result.stdout.read()
        result.stdout_lines = stdout.decode().split('\n')
        if result.stdout_lines[-1] == '':
            result.stdout_lines = result.stdout_lines[:-1]
        if not suppress_output:
            echo_output(stdout, result.stderr.read())
    return result


def compose(cmd, **kwargs):
    result = run('docker compose {0}'.format(cmd), **kwargs, raise_on_error=False)
    if result.returncode == 125:
        result = run('docker-compose {0}'.format(cmd), **kwargs)
        click.echo('WARNING: docker-compose is deprecated, please use Docker Compose V2')
    return result


def random_string(length):
    # Use /dev/urandom, see https://stackoverflow.com/a/23728630
    choice = random.SystemRandom().choice
    return ''.join(
        choice(string.ascii_letters + string.digits) for _ in range(length)
    )
