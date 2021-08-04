# Teamplify runner

[![image](https://travis-ci.org/teamplify/teamplify-runner.svg?branch=master)](https://travis-ci.org/teamplify/teamplify-runner)

[Teamplify](https://teamplify.com) is a personal assistant for your development
team. It helps you track work progress and notify your team about situations
that may require their attention. It is available
[in the cloud](https://teamplify.com) or as an on-premise installation.

This package is the installer and runner for the on-premise version.

* [System requirements](#system-requirements)
   * [On Ubuntu, be sure to install pip3](#on-ubuntu-be-sure-to-install-pip3)
   * [Hardware](#hardware)
* [Installing](#installing)
   * [Installing on Linux](#installing-on-linux)
   * [Installing on Mac OS X](#installing-on-mac-os-x)
* [Configuration](#configuration)
   * [Where are configuration files located?](#where-are-configuration-files-located)
   * [A reference of all configuration options](#a-reference-of-all-configuration-options)
* [Starting and stopping the service](#starting-and-stopping-the-service)
* [What to do after the first run?](#what-to-do-after-the-first-run)
   * [Creating an admin account](#creating-an-admin-account)
* [Updating Teamplify](#updating-teamplify)
* [Backup and restore](#backup-and-restore)
* [A Sample maintenance script](#a-sample-maintenance-script)
* [Uninstall](#uninstall)
* [Troubleshooting](#troubleshooting)
   * [Teamplify won't start](#teamplify-wont-start)
   * [Email delivery issues](#email-delivery-issues)
   * [The connection is refused or not trusted in SSL-enabled mode](#the-connection-is-refused-or-not-trusted-in-ssl-enabled-mode)
   * [Other](#other)
* [License](#license)


## System requirements

Teamplify is designed to run on Linux. For demonstration purposes, it should
also deploy on Mac OS X. Windows is not supported.

Before you install, make sure that your system has the following components:

* [Docker version 1.13 and above](https://docs.docker.com/install/);
* [Python 3.6 and above](https://www.python.org/downloads/);
* [pip for Python 3](https://packaging.python.org/tutorials/installing-packages/#ensure-you-can-run-pip-from-the-command-line)

To check that the required versions are installed, run these commands (shown
with example output):

``` shell
$ docker -v
Docker version 18.06.1-ce, build e68fc7a215d7133c34aa18e3b72b4a21fd0c6136
$ python3 --version
Python 3.7.2
$ pip3 --version
pip 9.0.3 from /usr/lib/python3.7/site-packages (python 3.7)
```

### On Ubuntu, be sure to install `pip3`

On most systems, `Python 3` comes with `pip3`  pre-installed. However,
in Ubuntu `Python 3` and `pip3` are installed separately. To install
`pip3` run:

```shell
$ sudo apt install python3-pip
```

**Important**: after installing, exit the terminal and re-open it.
This forces the terminal to update its path configuration, so that you
can find the command line tools installed with `pip3` in your `$PATH`.

### Hardware

As a default server configuration, we recommend 4GB of RAM, 2 CPU cores, and
30 GB of disk space (SSD is strongly recommended). For most small-to-medium
organizations (up to a few dozen people), this should be enough. Larger
workloads, however, may need more resources. The recommended strategy is to
start with the default server configuration and scale up or down depending on
the workload.

## Installing

### Installing on Linux

After installing Docker, check Docker's
[post-installation steps for Linux](https://docs.docker.com/install/linux/linux-postinstall/).
You probably want to make sure that you can run Docker commands without
`sudo`, and that Docker is configured to start on boot.

Install the latest version of Teamplify runner with pip:

``` shell
$ pip3 install -U teamplify
```

### Installing on Mac OS X

On Mac OS X, we recommend installing Teamplify in a Python virtual
environment located in your home directory. This is because Teamplify needs to
mount its configuration files into Docker containers. By default on Mac OS X,
only the `/Users` folder is shared with Docker.

1. Create a new Python virtual environment for Teamplify in your home directory:
``` shell
$ python3 -m venv ~/.venv/teamplify
```

2. Activate it:
``` shell
$ source ~/.venv/teamplify/bin/activate
```

3. At this point, a `pip` command is linked to the virtual environment that
you just created. Install Teamplify runner with `pip`:
``` shell
$ pip install teamplify
```

## Configuration

Teamplify requires a configuration file to run.

1. Run the following command to create the initial file:
``` shell
$ teamplify configure
```
  _This creates a configuration file with default settings in your home
directory: `~/.teamplify.ini`. You can specify the location of
your file with the `--config` option._

2. Use your text editor to  adjust the contents of this file.
  You need to specify the following parameters:
  * `product_key` in the  `[main]` section
  * `host` and `port` in the `[web]` section
  
  Other parameters are optional and can keep their default values.
  You can review them at [the reference of all configuration options](#A-reference-of-all-configuration-options)

### Where are configuration files located?

When you run `teamplify configure`, it creates a configuration file.
Typically, this file is at `~/.teamplify.ini`.

However, that is not the only
possible location. Teamplify searches the following locations (listed from
highest priority to lowest priority):

1. First, it checks the location specified in the `--config` parameter in the
command line. Example:

   ``` shell
   $ teamplify --config /path/to/configuration/file start
   ```

2. An environment variable named `TEAMPLIFY_CONF`. Example:

   ``` shell
   $ TEAMPLIFY_CONF=/path/to/configuration/file teamplify start
   ```

3. In the home directory of the current user: `~/.teamplify.ini`;
4. At `/etc/teamplify/teamplify.ini`.


### A reference of all configuration options

`[main]`

- `product_key` - the product key of your installation. This is required.
  To get the product key, please email us at
  [support@teamplify.com](mailto:support@teamplify.com);

- `update_channel` - the application distribution channel to use. Can be set to
  `stable` or `latest`. The default setting is `stable` (recommended for most
  users). With the `stable` channel, you should expect a few updates per month.
  Updates in the latest channel are more frequent and contain all the latest
  features and bug-fixes. However, they also have a higher chance of
  introducing new bugs. Please note that Teamplify doesn't update itself
  automatically unless you've explicitly configured it to do so. See the
  [Updates](#updates) and [Maintenance script](#maintenance-script) sections
  below;

- `send_crash_reports` - possible values are `yes` and `no`, defaults to `yes`.
  When set to `yes`, the system automatically sends application crash
  reports to our team. We recommend keeping this option enabled as it helps us
  to detect bugs faster and ship fixes for them more quickly;

`[web]`

- `host` - domain name on which the Teamplify web interface will be running. It
  must be created in advance, and pointed to the server where you have
  installed Teamplify;
- `port` - port on which Teamplify web interface will be running, the default
  is `80`. If `use_ssl` is set to `yes` then `80` is the only allowed option;
- `use_ssl` - possible values are `no`, `builtin`, and `external`, defaults to
  `no`. When set to `builtin` or `external`, all traffic to your Teamplify
  server will be redirected to HTTPS on port `443`. When set to `builtin`,
  Teamplify runner will use [Let's Encrypt](https://letsencrypt.org) to
  automatically generate and renew SSL certificates for the domain that you
  specified in the `host` parameter above. If you're hosting Teamplify behind a
  proxy or load balancer that is already configured for SSL support, please set
  this parameter to `external`, and also make sure that your proxy correctly
  sets `X-Forwarded-Proto` HTTP header;

`[db]`

- `host` - defaults to `builtin_db`, that is, using the DB instance that is
  shipped with Teamplify. You can also switch to an external MySQL 5.7
  compatible database by providing its hostname instead of `builtin_db` and
  specifying other DB connection parameters below;
- `name` - the database name to use. Must be `teamplify` if `builtin_db` is
  used;
- `port` - the database port. Must be `3306` for `builtin_db`;
- `user` - DB user. Must be `root` for `builtin_db`;
- `password` - DB password. Must be `teamplify` for `builtin_db`;
- `backup_mount` - a path to a directory on the server which will be mounted
  into the built-in DB instance container. It is used as a temporary directory
  in the process of making and restoring backups;

`[email]`

- `address_from` - email address used by Teamplify in the FROM field of its
  email messages. It could be either a plain email address or an email address
  with a display name, like this:
  `Teamplify <teamplify@your-company-domain.com>`;
- `smtp_host` - hostname of an SMTP server used to send emails. Defaults to
  `builtin_smtp` which means using the SMTP server that is shipped with
  Teamplify. Built-in SMTP for Teamplify is based on Postfix, and it is
  production-ready. However, if you plan to use it, we strongly recommend that
  you add the address of Teamplify's server to the
  [SPF record](http://www.openspf.org/SPF_Record_Syntax) of the domain used
  in the `address_from` setting to prevent Teamplify emails from being marked
  as spam. Or, you can configure Teamplify to use an external SMTP server by
  providing its hostname instead of `builtin_smtp` and configuring other
  SMTP connection settings below;
- `smtp_protocol` - SMTP protocol to use. Can be `plain`, `ssl`, or `tls`.
  Must be `plain` if you use `builtin_smtp`;
- `smtp_port` - SMTP port to use. Must be `25` for `builtin_smtp`;
- `smtp_user` - username for the SMTP server. Must be blank for `builtin_smtp`;
- `smtp_password` - password for the SMTP server. Must be blank for
  `builtin_smtp`;

`[crypto]`

- `signing_key` - the random secret string used by Teamplify for signing
  cookies and generating CSRF protection tokens. It is automatically generated
  when you run `teamplify configure`, and typically you don't need to change
  it unless you think that it may be compromised. In such cases, replace it with
  another 50-character random string made of Latin characters and numbers
  (please note that this will force all existing users to log in to the system
  again).

## Starting and stopping the service

After you have created the configuration file, start Teamplify with:

``` shell
$ teamplify start
```

On the first run, the application has to download and configure many Docker
images. For this reason, the first run might take a while to start.

After the command completes, open Teamplify in your browser using the `host` and
the `port` that you provided in the `[web]` section of the configuration. After
starting the service, it might take a minute or two before it finally comes
online.

If you have problems starting Teamplify, please see the
[Troubleshooting](#troubleshooting) section below.

If you need to stop Teamplify, run:

``` shell
$ teamplify stop
```

After running Teamplify for the first time,
[follow the instructions to create an admin account](#create-an-admin-account)

There's also a convenient command to stop the service and start it again. This
is useful when applying changes made to the configuration:

``` shell
$ teamplify restart
```

## What to do after the first run?

After the first run, you need to create an admin account.

### Creating an admin account

After the application first starts, run the following command:

``` shell
$ teamplify createadmin --email <admin@email> --full-name <Full Name>
```

Please check the output to make sure that no errors occurred.

With the `createadmin` command, you can create as many
admin account as you want. However, after creating the first one,
it might be more convenient to create the others through the Teamplify UI.

## Updating Teamplify

Teamplify installation consists of the Teamplify runner and the Teamplify
product itself, which ships in the form of Docker images. We recommend
that you use the most recent version to keep up with the latest features and
bugfixes. The update process consists of two steps:

1. Update Teamplify runner:

   ``` shell
   $ pip3 install -U teamplify
   ```

2. Update Teamplify itself:

   ``` shell
   $ teamplify update
   ```

The `update` command automatically detects if a new version has been
downloaded and, if necessary, restarts the service. Because a service restart
causes  a short downtime, you should ideally update in periods of low user
activity. The `update` command restarts the service only when necessary. If no
update has been downloaded, there is no restart and therefore no service
interruption.

## Backup and restore

Teamplify stores your data in a MySQL database. As with any other database, it
might be a good idea to make backups from time to time to time.

To back up the built-in Teamplify database, run:

``` shell
$ teamplify backup [optional-backup-file-or-directory]
```

If launched without parameters, it makes a gzipped backup of the DB and
stores it in the current working directory, under a name in the format:

* `teamplify_<current-date>.sql.gz`,
  * for example, `teamplify_2019-01-31_06-58-57.sql.gz`.

You may specify the directory or file path where you'd like to save your backup.

To restore the built-in Teamplify database from a gzipped backup, run:

``` shell
$ teamplify restore <path-to-a-backup-file>
```

Please note that the commands above work with only a built-in database.
If you're running Teamplify with an external database, you need to use tools
for backups or restores that connect to that database directly.

## A Sample maintenance script

Backing up the data and keeping the software up-to-date are routine operations.
We recommend automating these processes. Below is a sample script you can use to
do so.

1. Create a file named `teamplify-maintenance.sh` with the following contents:

``` shell
#!/usr/bin/env bash

# Backups directory:
BACKUP_LOCATION=/backups/teamplify/

# How many days should we store the backups for:
BACKUP_STORE_DAYS=14

# Back up Teamplify DB and update Teamplify:
mkdir -p $BACKUP_LOCATION && \
    pip3 install -U teamplify && \
    teamplify backup $BACKUP_LOCATION && \
    teamplify update

# If the update was successful, clean up old backups:
if [ $? -eq 0 ]; then
  find $BACKUP_LOCATION -type f -mmin +$((60 * 24 * $BACKUP_STORE_DAYS)) \
      -name 'teamplify_*.sql.gz' -execdir rm -- '{}' \;
fi

# The final step is optional but recommended. Add your code so that would
# sync contents of $BACKUP_LOCATION to a physically remote location.
#
#   ... add your backups sync code below:
```

In the code above, adjust the path for `$BACKUP_LOCATION` and the value
for `$BACKUP_STORE_DAYS` as necessary. At the end of the script, you can add
your own code that would sync your backups to a remote location. This is an
optional but highly recommended precaution that would help you recover your
backup in the case of a disaster. For example, you can use
[aws s3 sync](https://docs.aws.amazon.com/cli/latest/reference/s3/sync.html) to
upload the backups to AWS S3.

2. When the maintenance script is ready, make it executable with
`chmod +x teamplify-maintenance.sh`.

3. Set the script to run as a daily cron job. Open the crontab schedule:

``` shell
$ crontab -e
```

Append the following entry (remember to replace the path to the script):

``` shell
0 3 * * * /path/to/the/script/teamplify-maintenance.sh
```

In the example above, the script is scheduled to run daily at 3 AM. See
[cron syntax](https://en.wikipedia.org/wiki/Cron) for a detailed explanation.
When ready, save and close the file.

## Uninstall

If you'd like to uninstall Teamplify, use the following steps.

**IMPORTANT**: The uninstall procedure erases all data stored in Teamplify.
Before doing this, [consider making a backup](#backup-and-restore).

1. Remove all Teamplify data, Docker images, volumes, and networks:

``` shell
$ teamplify erase
```

2. Uninstall Teamplify runner:

``` shell
$ pip3 uninstall teamplify
```

## Troubleshooting

So what could possibly go wrong?

### Teamplify won't start

Please check the following:

- The service won't start if the configuration file is missing or contains
  errors. In such cases, the `teamplify start` command will report a problem.
  Please inspect its output;
- There could be a problem with the domain name configuration. If the
  `teamplify start` command has completed successfully, you should see
  Teamplify's interface in the browser when you open an address specified in the
  `host` and `port` parameters in the `[web]` section of the
  [Configuration](#configuration). If that doesn't happen, i.e. if browser says
  that it can't find the server or the server is not responding, then most
  likely this is a problem with either the domain name or firewall
  configuration. Please make sure that the domain exists and points to the
  Teamplify server, and that the port is open in the firewall;
- If you see the "Teamplify is starting" message, you should give it a minute
  or two to come online. If nothing happens after a few minutes, there could be
  a problem during application start. Application logs may contain additional
  information:

  ``` shell
  $ docker logs teamplify_app
  ```

  Please let us know about the problem and attach the output from the command
  above. You can either
  [open an issue on Github](https://github.com/teamplify/teamplify-runner/issues),
  or contact us at [support@teamplify.com](mailto:support@teamplify.com), or
  use the live chat on [teamplify.com](https://teamplify.com).

### Email delivery issues

Emails can go to spam or sometimes aren't delivered at all. If you're
running a demo version of Teamplify on your desktop at home, this is
very likely to happen, since IPs of home internet providers have a large
chance of being blacklisted in spam databases. We recommend that you
try the following:

- If you're going to use the built-in SMTP server, consider running Teamplify
  on a server hosted in a data center or at your office, but not at home. Next,
  please make sure that you've added the IP of your Teamplify server to the
  [SPF record](http://www.openspf.org/SPF_Record_Syntax) of the domain used
  in `address_from` setting in the configuration file;
- Some email providers, for example, Google Mail, explicitly reject emails
  sent from blacklisted IPs. It might be helpful to examine SMTP server
  logs to see if that's what's happening:

  ``` shell
  $ docker logs teamplify_smtp
  ```

- Alternatively, if you have another SMTP server that is already configured
  and can reliably send emails, you can configure Teamplify to use this server
  instead of the built-in SMTP. See `[email]` section in
  [Configuration](#configuration) for details;


### The connection is refused or not trusted in SSL-enabled mode

During the first start, Teamplify runner generates a temporary self-issued SSL
certificate (not trusted) and then tries to create a valid certificate for your
domain via [Let's Encrypt](https://letsencrypt.org) that would replace the
temporary one. Besides that, it also creates a new set of 2048-bit DH parameters
to give your SSL configuration an A+ rating. This process is rather slow and may
take a few minutes to complete. If you open Teamplify in your browser and see
that the SSL connection can't be established or is not trusted, the problem may
be caused by DH params or the SSL certificate generations that are still in
progress. After DH params and the SSL certificate have been successfully
generated, they are saved for future use and subsequent restarts of the server
should be much faster.

If you have just started the server for the very first time, please give it a
few minutes to complete the initialization and then refresh the page in your
browser. If after a few minutes the browser reports that the connection is not
trusted, it probably means that the certificate generation has failed. Please
check the following:

1. That the domain that you specified in the `host` parameter can be resolved
   from the public Internet and is pointing to the server on which you have
   installed Teamplify;
2. That ports `80` and `443` are not blocked in the firewall.

It also might be helpful to check the logs:

``` shell
$ docker logs teamplify_letsencrypt
```

### Other

For any issue with Teamplify, we recommend that you try to
[check for updates](#updates) first. We release updates frequently. It's quite
possible that the problem that you encountered is already addressed in a newer
version.

If these suggested solutions don't work, don't hesitate to
[open an issue on Github](https://github.com/teamplify/teamplify-runner/issues)
or contact us at [support@teamplify.com](mailto:support@teamplify.com). You can
also use the live chat on [teamplify.com](https://teamplify.com). We're ready
to help!

## License

Teamplify runner is available under the MIT license. Please note that the MIT
license applies to Teamplify runner only, but not to the main Teamplify product.
Some Docker images downloaded by Teamplify runner will contain a proprietary
code that is not open source and is distributed under its own
[terms and conditions](https://teamplify.com/terms/).
