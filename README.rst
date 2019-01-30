Teamplify runner
================

.. image:: https://travis-ci.org/teamplify/teamplify-runner.svg?branch=master
        :target: https://travis-ci.org/teamplify/teamplify-runner

About
-----

Teamplify is a personal assistant for your development team that helps you to
track the work progress and automatically notify the team about situations that
may require their attention. It is available in two deployment options:
`in the cloud <https://teamplify.com>`_ or on-premise. This package is the
installer for the on-premise version.

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

Teamplify requires a configuration file to run. You could create a sample
configuration file with the following command:

.. code:: shell

  $ teamplify configure

This would create a configuration file with default settings in your home
directory: ``~/.teamplify.ini``. Now, please use your favorite text editor and
adjust the contents of this file. You can leave the most of the settings with
their default values; however, you need to specify at least the following three:
``product_key`` in the ``[main]`` section, and ``host`` and ``port`` in the
``[web]`` section.

All configuration options explained:

``[main]``

- ``product_key`` - product key of your installation, required. Please
  `contact us <mailto:support@teamplify.com>`_ to get the product key;

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
