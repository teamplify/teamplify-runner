Teamplify runner
================

.. image:: https://travis-ci.org/teamplify/teamplify-runner.svg?branch=master
        :target: https://travis-ci.org/teamplify/teamplify-runner

About
-----

Teamplify is a personal assistant for your development team, which helps you to
track the work progress and automatically notify the team about situations that
may require their attention. It is available in two deployment options:
`in the cloud <https://teamplify.com>`_ or on-premise. This package is the
installer for the on-premise version.

System requirements
-------------------

Teamplify was designed to run on Linux. For demonstration purposes you can also
deploy it on Mac OS X and it should work too. Windows is not supported. Before
you proceed to the installation, please make sure that your system has the
following components installed:

- Docker version 1.13 and above;
- Python 3.4 and above.

You can check the versions installed with the following commands (shown with an
example output):

.. code:: shell

  $ docker -v
  Docker version 18.06.1-ce, build e68fc7a215d7133c34aa18e3b72b4a21fd0c6136
  $ python3 --version
  Python 3.7.2

In terms of hardware, we recommend minimum of 2GB of RAM, 2 CPU cores and 20 GB
of disk space (SSD is strongly recommended). It should be enough for most
of small-to-medium sized organizations, up to few dozens of people. For
larger workloads you may need a more powerful server.

Installation
------------

Install the latest version of Teamplify installer with pip:

.. code:: shell

  $ pip3 install -U teamplify
