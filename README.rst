Teamplify runner
================

.. image:: https://travis-ci.org/teamplify/teamplify-runner.svg?branch=master
        :target: https://travis-ci.org/teamplify/teamplify-runner


WIP, NOT READY YET
------------------

The planned release date of the on-premise version of Teamplify is February
2019. If you see this message, it means that it's not ready yet and that the
installer would not work. If you're interested in trying on-premise version of
`Teamplify <https://teamplify.com>`_, please drop us a line at
`support@teamplify.com <mailto:support@teamplify.com>`_ and we'll be happy to
send you an update once it's ready.

----


* `About`_
* `System requirements`_
* `Installation`_
* `Configuration`_
* `Configuration file locations`_
* `Starting and stopping the service`_
* `Upgrades`_
* `Backup and restore`_
* `Troubleshooting`_
* `License`_


About
-----

`Teamplify <https://teamplify.com>`_ is a personal assistant for your
development team that helps you to track the work progress and automatically
notify the team about situations that may require their attention. It is
available in two deployment options: `in the cloud <https://teamplify.com>`_ or
on-premise. This package is the installer for the on-premise version.


System requirements
-------------------

Teamplify was designed to run on Linux. For demonstration purposes, you can also
deploy it on Mac OS X, and it should work too. Windows is not supported. Before
you proceed to the installation, please make sure that your system has the
following components installed:

- Docker version 1.13 and above;
- Python 3.4 and above.

You can check to see if the required versions are installed with the following
commands (shown with example output):

.. code:: shell

  $ docker -v
  Docker version 18.06.1-ce, build e68fc7a215d7133c34aa18e3b72b4a21fd0c6136
  $ python3 --version
  Python 3.7.2

In terms of hardware, we recommend 4GB of RAM, 2 CPU cores and 30 GB of disk
space (SSD is strongly recommended) as a default server configuration. For most
small-to-medium organizations (up to a few dozen people), this should be enough.
Larger workloads, however, may need a more powerful server. The recommended
strategy is to start from the default server configuration, and later tune it up
or down basing on the workload.


Installation
------------

Install the latest version of Teamplify runner with pip:

.. code:: shell

  $ pip3 install -U teamplify


Configuration
-------------

Teamplify requires a configuration file to run. You could create an initial
configuration file with the following command:

.. code:: shell

  $ teamplify configure

This would create a configuration file with default settings in your home
directory: ``~/.teamplify.ini``. Now, please use your favorite text editor and
adjust the contents of this file. You need to specify at least the following
three settings: ``product_key`` in the ``[main]`` section, and ``host`` and
``port`` in the ``[web]`` section. Others are optional and can stay with their
default values.

All configuration options explained:

``[main]``

- ``product_key`` - product key of your installation, required. Please email us
  at `support@teamplify.com <mailto:support@teamplify.com>`_ to get the product
  key;

``[web]``

- ``host`` - domain name on which Teamplify web interface would be running. It
  must be created in advance and pointing to the server on which you have
  installed Teamplify;
- ``port`` - port on which Teamplify web interface would be running;
- ``use_ssl`` - the only supported value at the moment is ``no``. Built-in SSL
  support will be available in future versions;

``[db]``

- ``host`` - defaults to ``builtin_db``, which means use the DB instance that is
  shipped with Teamplify. You can also switch to an external MySQL 5.7 database
  by providing its hostname instead of ``builtin_db`` and specifying other DB
  connection parameters below;
- ``name`` - the database name to use. Must be ``teamplify`` if ``builtin_db``
  is used;
- ``port`` - the database port. Must be ``3306`` for ``builtin_db``;
- ``user`` - DB user. Must be ``root`` for ``builtin_db``;
- ``password`` - DB password. Must be ``teamplify`` for ``builtin_db``;
- ``backup_mount`` - a directory on the server which would be mounted into the
  built-in DB instance container. It is used as a temporary directory in the
  process of making and restoring backups;

``[email]``

- ``address_from`` - email address used by Teamplify in FROM field of its email
  messages. It could be either a plain email address or an email address with
  a display name, like this: ``Teamplify <teamplify@your-company-domain.com>``;
- ``smtp_host`` - hostname of an SMTP server used to send emails. Defaults to
  ``builtin_smtp`` which means use the SMTP server that is shipped with
  Teamplify. Built-in SMTP for Teamplify is based on Postfix, and it is
  production-ready. However, if you plan to use it, we strongly recommend that
  you add the address of Teamplify server to the
  `SPF record <http://www.openspf.org/SPF_Record_Syntax>`_ of the domain used
  in ``address_from`` setting, to prevent Teamplify emails from being marked as
  spam. Or, you can configure Teamplify to use an external SMTP server by
  providing its hostname instead of ``builtin_smtp`` and configuring other SMTP
  connection settings below;
- ``smtp_protocol`` - SMTP protocol to use. Can be ``plain``, ``ssl``, or
  ``tls``. Must be ``plain`` if you use ``builtin_smtp``;
- ``smtp_port`` - SMTP port to use. Must be ``25`` for ``builtin_smtp``;
- ``smtp_user`` - username for the SMTP server. Must be blank for
  ``builtin_smtp``;
- ``smtp_password`` - password for the SMTP server.  Must be blank for
  ``builtin_smtp``;

``[crypto]``

- ``signing_key`` - the random secret string used by Teamplify for signing
  cookies and generating CSRF protection tokens. It is automatically generated
  when you run ``teamplify configure``, and typically you don't need to change
  it unless you think that it may be compromised. In such case replace it with
  another 50-characters random string made of Latin characters and numbers
  (please note that it would force all existing users to login into the system
  again).


Configuration file locations
----------------------------

When you run ``teamplify configure`` it would create a configuration file at
``~/.teamplify.ini``. However, this is not the only possible location. Teamplify
would look in the following locations (listed in the order of their priority,
from the highest to the lowest):

1. The location specified in the ``--config`` parameter in the command line.
   Example:

.. code:: shell

    $ teamplify start --config /path/to/configuration/file

2. An environment variable named ``TEAMPLIFY_CONF``. Example:

.. code:: shell

    $ TEAMPLIFY_CONF=/path/to/configuration/file teamplify start

3. In the home directory of the current user: ``~/.teamplify.ini``;

4. At ``/etc/teamplify/teamplify.ini``.


Starting and stopping the service
---------------------------------

After you created the configuration file, start Teamplify with:

.. code:: shell

    $ teamplify start

During the first run, it may take a while before the application starts since
it would need to download and configure a bunch of Docker images. When the
command has finished working, open Teamplify in your browser using the ``host``
and the ``port`` which you provided in ``[web]`` section of the configuration.
After starting the service, it may take a few more moments before it finally
comes online. If you have problems starting Teamplify, please see the
`Troubleshooting`_ section below.

If you need to stop Teamplify, run:

.. code:: shell

    $ teamplify stop

There's also a convenient command to stop the service and start it again. It
could be useful to apply the changes made to the configuration:

.. code:: shell

    $ teamplify restart


Upgrades
--------

Teamplify installation consists of Teamplify runner and Teamplify product
itself, which is shipped in the form of Docker images. We follow the concept of
rolling updates, releasing new versions of the product often (up to a few times
a week). We recommend that you use the most recent version to keep up with the
latest features and bugfixes. The upgrade process and consists of two steps:

1. Upgrade Teamplify runner:

.. code:: shell

    $ pip3 install -U teamplify

2. Upgrade Teamplify itself:

.. code:: shell

    $ teamplify upgrade

When a new version is downloaded, you should run ``teamplify restart`` to
replace your current running version with a new one.


Backup and restore
------------------

Teamplify stores your data in MySQL database. As with any other database, it
might be a good idea to make backups from time to time to ensure that the data
is not lost in case of a system crash.

To back up the built-in Teamplify database, run:

.. code:: shell

    $ teamplify backup [optional-filename-or-directory]

If launched without parameters, it would make a gzipped backup of the DB and
store it in the current working directory under a name in the format
``teamplify_<current-date>.sql.gz``, for example,
``teamplify_2019-01-31_06-58-57.sql.gz``. You can optionally specify a directory
or a path to a file where you'd like to save the backup.

To restore the built-in Teamplify database from a gzipped backup, run:

.. code:: shell

    $ teamplify restore <path-to-a-backup-file>

Please note that the commands above would work with the built-in database only.
If you're running Teamplify with an external database, please use other tools
for backups or restore that would connect to that database directly.


Troubleshooting
---------------

What could possibly go wrong:

Email delivery issues
~~~~~~~~~~~~~~~~~~~~~

Emails can go to spam or sometimes not being delivered at all. If you're running
a demo version of Teamplify at your desktop at home, this is very likely to
happen, since IPs of home internet providers have a large chance of being
blacklisted in spam databases. We recommend that you check the following:

* If you're going to use the built-in SMTP server, run Teamplify on a server
  hosted in a data center or your office, not at home. Make sure that you've
  added the IP of Teamplify server to
  the `SPF record <http://www.openspf.org/SPF_Record_Syntax>`_ of the domain
  used in ``address_from`` setting in the configuration file;
* Some email providers, for example, Google Mail, would explicitly reject emails
  sent from blacklisted IPs. It might be helpful to examine SMTP server logs to
  see if that's the case that is happening:

.. code:: shell

    $ docker logs teamplify_smtp

* Alternatively, if you have another SMTP server which is already configured and
  can reliably send emails, you can switch to it. See ``[email]`` section in
  `Configuration`_ for details;


Teamplify doesn't start
~~~~~~~~~~~~~~~~~~~~~~~

Please check the following:

* Service wouldn't start if the configuration file is missing or contains
  errors. In such case ``teamplify start`` command would report a problem,
  please check its output;
* There could be a problem with domain name configuration. If
  ``teamplify start`` command has completed successfully, you should see
  the "Teamplify is starting" message in the browser when you open an address
  specified in ``host`` and ``port`` parameters in ``[web]`` section of the
  `Configuration`_. If that doesn't happen, then most likely it is a problem
  with either domain name or firewall configuration. Please make sure that the
  domain exists and points to Teamplify server, and that the port is open in the
  firewall.
* If you see "Teamplify is starting" message, you should let it a minute or
  two to finally come online. If that doesn't happen after a few minutes, there
  could be a problem during application start. Check the logs with the following
  command:

.. code:: shell

    $ docker logs teamplify_app

Please let us know about the problem and attach the output from the command
above. You can either
`open an issue on Github <https://github.com/teamplify/teamplify-runner/issues>`_
or contact us at `support@teamplify.com <mailto:support@teamplify.com>`_.


Other
~~~~~

If you experience a problem that is not listed above, or the suggested solution
doesn't work, please don't hesitate to
`open an issue on Github <https://github.com/teamplify/teamplify-runner/issues>`_
or contact us at `support@teamplify.com <mailto:support@teamplify.com>`_. We're
ready to help!


License
-------

Teamplify runner is available under MIT license. Please note that MIT license
applies to Teamplify runner only, but not to Teamplify itself. Docker images
downloaded by Teamplify runner would contain a proprietary code which is not
open source and is distributed under its
own `terms and conditions <http://teamplify.com/terms/>`_.
