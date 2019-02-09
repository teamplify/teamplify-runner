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


def run(cmd, raise_on_error=True, capture_output=True, suppress_output=False,
        **kwargs):
    """
    Wrapper around sarge.run that can raise errors and capture stdout.
    """
    if capture_output:
        kwargs['stdout'] = sarge.Capture()
        kwargs['stderr'] = sarge.Capture()
    result = sarge.run(cmd, **kwargs)
    code = result.returncode
    if code and raise_on_error:
        raise RuntimeError('Command failed, exit code %s' % code)
    if capture_output:
        stdout = result.stdout.read()
        result.stdout_lines = stdout.decode().split('\n')
        if result.stdout_lines[-1] == '':
            result.stdout_lines = result.stdout_lines[:-1]
        if not suppress_output:
            if stdout:
                click.echo(stdout)
            stderr = result.stderr.read()
            if stderr:
                click.echo(stderr, err=True)
    return result


def random_string(length):
    # Use /dev/urandom, see https://stackoverflow.com/a/23728630
    choice = random.SystemRandom().choice
    return ''.join(
        choice(string.ascii_letters + string.digits) for _ in range(length)
    )
