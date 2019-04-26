from sshtunnel import SSHTunnelForwarder
import os
import psycopg2
import psycopg2.extensions
import typing
import util


def connect_to_database():
    global sshforward

    cwf_user = os.environ['CWF_USER']
    cwf_pass = os.environ['CWF_PASS']

    cwf_use_ssh = os.getenv('CWF_USE_SSH', "0")

    if cwf_use_ssh == "1":
        cwf_host = os.environ['CWF_HOST']
        cwf_port = int(os.environ['CWF_PORT'])
        cwf_pkey = os.environ['CWF_PKEY']

        available_port = util.get_free_port()

        sshforward = SSHTunnelForwarder((cwf_host, 22),
                                        ssh_pkey=cwf_pkey,
                                        remote_bind_address=('localhost', cwf_port),
                                        local_bind_address=('localhost', available_port))

        sshforward.start()
    else:
        available_port = 5432

    if util.development_mode():
        conn = psycopg2.connect(
            "postgresql://{user:s}:{password:s}@localhost:{port:d}/connorwfitzgerald_dev".format(user=cwf_user,
                                                                                                 password=cwf_pass,
                                                                                                 port=available_port))
        # type: psycopg2.extensions.connection
    else:
        conn = psycopg2.connect(
            "postgresql://{user:s}:{password:s}@localhost:{port:d}/connorwfitzgerald_prod".format(user=cwf_user,
                                                                                                 password=cwf_pass,
                                                                                                 port=available_port))
        # type: psycopg2.extensions.connection

    return conn


connection = connect_to_database() # type: psycopg2.extensions.connection


