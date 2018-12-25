import contextlib
import os
import random
import string

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


def run(cmd, raise_on_error=True, **kwargs):
    """
    Wrapper around sarge.run which can raise errors and capture stdout.
    """
    result = sarge.run(
        cmd,
        stdout=sarge.Capture(),
        stderr=sarge.Capture(),
        **kwargs,
    )
    stdout = result.stdout.read()
    stderr = result.stderr.read()
    if stdout:
        click.echo(stdout)
    if stderr:
        click.echo(stderr, err=True)
    code = result.returncode
    if code and raise_on_error:
        raise RuntimeError('Command failed, exit code %s' % code)
    result.stdout_lines = stdout.decode().split('\n')
    if result.stdout_lines[-1] == '':
        result.stdout_lines = result.stdout_lines[:-1]
    return result


def random_string(length):
    # Use /dev/urandom, see https://stackoverflow.com/a/23728630
    choice = random.SystemRandom().choice
    return ''.join(
        choice(string.ascii_letters + string.digits) for _ in range(length),
    )
