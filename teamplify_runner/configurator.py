import io
import os
import re
import socket
from collections import OrderedDict
from configparser import ConfigParser
from functools import partial

from teamplify_runner.utils import random_string


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class ConfigurationError(Exception):
    """
    Supports a single error or a list of errors
    """
    def __init__(self, message, *args, **kwargs):
        if isinstance(message, (list, tuple)):
            self.messages = message
            if len(self.messages) > 1:
                message = '%s errors found' % len(self.messages)
            else:
                message = self.messages[0]
        else:
            self.messages = [message]
        super().__init__(message, *args, **kwargs)

    def __str__(self):
        if len(self.messages) > 1:
            return '%s errors found:\n' % len(self.messages) + '\n'.join([
                ' -> %s' % m for m in self.messages
            ])
        return self.messages[0]


def validate_hostname(hostname):
    try:
        socket.gethostbyname(hostname)
    except socket.gaierror:
        raise ConfigurationError('Can\'t resolve hostname: %s' % hostname)


def validate_integer(value, min=None, max=None):
    try:
        value = int(value)
    except ValueError:
        raise ConfigurationError('Must be an integer. You provided: %s' % value)
    if min is not None and value < min:
        raise ConfigurationError(
            'Must be greater or equal to %s. You provided: %s' % (min, value),
        )
    if max is not None and value > max:
        raise ConfigurationError(
            'Must be less or equal to %s. You provided: %s' % (max, value),
        )


validate_port = partial(validate_integer, min=0, max=65535)


def validate_boolean(value):
    if value.lower() not in ('yes', 'no', 'y', 'n', 'true', 'false', '0', '1'):
        raise ConfigurationError(
            'Must be yes or no, or true / false, or 1 / 0. '
            'You provided: %s' % value,
        )


def str_to_bool(s):
    return s.lower() in ('yes', 'y', 'true', '1')


def validate_choice(value, choices):
    if value not in choices:
        raise ConfigurationError(
            'Must be one of the following: %s. You provided: %s' % (
                ', '.join(choices),
                value,
            ),
        )


def validate_email(value):
    """
    Not going to write insane regex here,
    just make sure that it contains exactly one @ surrounded by letters.
    """
    if not re.match(r'^[^@]*\w+@\w+[^@]*$', value):
        raise ConfigurationError('Invalid email: %s' % value)


def validate_product_key(value):
    if not value:
        raise ConfigurationError('Product key is missing')
    if not re.match('^svr_[A-Za-z0-9]{16}-[A-Za-z0-9]{20}$', value):
        raise ConfigurationError('Invalid product key: %s' % value)


class Configurator:
    defaults = OrderedDict((
        ('main', OrderedDict((
            ('product_key', ''),
            ('update_channel', 'stable'),
            ('send_crash_reports', 'yes'),
        ))),
        ('web', OrderedDict((
            ('host', 'localhost'),
            ('port', 80),
            ('use_ssl', 'no'),
        ))),
        ('db', OrderedDict((
            ('host', 'builtin_db'),
            ('name', 'teamplify'),
            ('port', 3306),
            ('user', 'root'),
            ('password', 'teamplify'),
            ('backup_mount', os.path.join(BASE_DIR, 'backup')),
        ))),
        ('email', OrderedDict((
            ('address_from', 'Teamplify <support@teamplify.com>'),
            ('smtp_host', 'builtin_smtp'),
            ('smtp_protocol', 'plain'),
            ('smtp_port', 25),
            ('smtp_user', ''),
            ('smtp_password', ''),
        ))),
        ('crypto', OrderedDict((
            ('signing_key', random_string(50)),
        ))),
    ))
    default_config_locations = [
        os.environ.get('TEAMPLIFY_CONF', ''),
        os.path.expanduser('~/.teamplify.ini'),
        '/etc/teamplify/teamplify.ini',
    ]
    default_save_location = os.path.expanduser('~/.teamplify.ini')

    def __init__(self, config_path=None):
        if config_path:
            self.config_path = config_path
        else:
            self.config_path = None
            for path in self.default_config_locations:
                if os.path.isfile(path):
                    self.config_path = path
                    break
        self.parser = ConfigParser()
        self.parser.read_dict(self.defaults)

    def load(self, config_path=None):
        if config_path:
            self.config_path = config_path
        if self.config_path:
            if not os.path.exists(self.config_path):
                raise RuntimeError('File not found: %s' % self.config_path)
            self.parser.read(self.config_path)
        return self

    def loads(self, configuration):
        self.parser.read_string(configuration)
        return self

    def dump(self, config_path=None):
        self.config_path = config_path \
                           or self.config_path \
                           or self.default_save_location
        with open(self.config_path, 'w') as f:
            self.parser.write(f)
        return self

    def dumps(self):
        fp = io.StringIO()
        with fp:
            self.parser.write(fp)
            return fp.getvalue()

    def ssl_mode(self):
        use_ssl = self.parser.get('web', 'use_ssl', fallback='').lower()
        if use_ssl in ('builtin', 'external'):
            return use_ssl
        elif str_to_bool(use_ssl):
            return 'builtin'
        return ''

    def env(self):
        env = {}
        for section in self.parser.sections():
            for option in self.parser.options(section):
                name = section.upper() + '_' + option.upper()
                env[name] = str(self.parser.get(section, option, fallback=''))
        if self.ssl_mode() == 'builtin':
            env['LETSENCRYPT_HOST'] = env['WEB_HOST']
        else:
            env['LETSENCRYPT_HOST'] = ''
        return env

    def validate(self):
        errors = []
        for section in self.parser.sections():
            if section not in self.defaults:
                # Check unknown sections here, because we don't want lots of
                # errors for each option in unknown section
                errors.append('Unknown section: [%s]' % section)
                continue
            for option in self.parser.options(section):
                try:
                    self.validate_option(
                        section=section,
                        option=option,
                        value=self.parser.get(section, option),
                    )
                except ConfigurationError as e:
                    errors.append('[%s] %s: %s' % (section, option, str(e)))
        if errors:
            raise ConfigurationError(errors)
        return self

    def validate_option(self, section, option, value):
        if section not in self.defaults:
            raise ConfigurationError('Unknown section: [%s]' % section)

        if option not in self.defaults[section]:
            raise ConfigurationError('Unknown option')

        value = self.parser.get(section, option)
        if section == 'main':
            if option == 'product_key':
                validate_product_key(value)
            elif option == 'send_crash_reports':
                validate_boolean(value)
            elif option == 'update_channel':
                validate_choice(value, ['stable', 'latest'])
        elif section == 'web':
            if option == 'host':
                validate_hostname(value)
            elif option == 'port':
                validate_port(value)
                if value == '443':
                    raise ConfigurationError(
                        'Can\'t use port 443 because it\'s reserved for the '
                        'SSL-enabled configuration. Please choose another port',
                    )
                if value != '80' and self.ssl_mode():
                    raise ConfigurationError(
                        'For SSL-enabled configuration port must be set to 80. '
                        'You provided: %s' % value,
                    )
            elif option == 'use_ssl':
                validate_choice(value, ['no', 'builtin', 'external'])
        elif section == 'db':
            if option == 'host' and value.lower() != 'builtin_db':
                validate_hostname(value)
            elif option == 'port':
                validate_port(value)
            elif option == 'backup_mount':
                if not os.path.isdir(value):
                    raise ConfigurationError('Must be a directory: %s' % value)
                if not os.access(value, os.W_OK):
                    raise ConfigurationError(
                        'Write permission denied: %s' % value,
                    )
        elif section == 'email':
            if option == 'smtp_host' and value.lower() != 'builtin_smtp':
                validate_hostname(value)
            elif option == 'smtp_protocol':
                validate_choice(value, ['plain', 'ssl', 'tls'])
            elif option == 'smtp_port':
                validate_port(value)
            elif option == 'address_from':
                validate_email(value)

    def remove_unknown(self):
        unknown_sections = []
        for section in self.parser.sections():
            if section not in self.defaults:
                unknown_sections.append(section)
                continue
            unknown_options = []
            for option in self.parser.options(section):
                if option not in self.defaults[section]:
                    unknown_options.append(option)
            for option in unknown_options:
                self.parser.remove_option(section, option)
        for section in unknown_sections:
            self.parser.remove_section(section)
        return self
