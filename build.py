from glob import glob
from typing import Tuple, Dict
import argparse
import colorama
import cp
import itertools
import json
import os
import getpass
import paramiko
import re
import shutil
import subprocess
import sys
import time

python_file_globs = ['*.py', 'util/*.py', 'requirements.txt']
template_file_globs = ['templates']

windows = os.name == 'nt'

colorama.init()


###########
# LOGGING #
###########

def section_title(title):
    print("\u001b[37;1m{}\u001b[0m".format(title))


def info(text):
    start = time.perf_counter()

    sys.stdout.write(f"\t{text}... ")
    sys.stdout.flush()

    def done(final_string: str, success: bool):
        end = time.perf_counter()

        diff = end - start

        sys.stdout.write((f"\u001b[32;1m{final_string}\u001b[0m" if success
                          else f"\u001b[31;1m{final_string}\u001b[0m")
                         + f"  ({diff:.2f}s)\n")
        sys.stdout.flush()

        if not success:
            exit(1)

    return done


########
# UTIL #
########


def parse_semver(input_string: str, prefix: str = ""):
    reg_result = re.search("{}(\\d*)\.(\\d*)\.(\\d*)".format(prefix), input_string)

    return tuple(map(int, reg_result.group(1, 2, 3)))


def stringify_semver(input_string: Tuple[int, int, int]):
    return ".".join(map(str, input_string))


# https://stackoverflow.com/a/19974994
class MySFTPClient(paramiko.SFTPClient):
    def put_dir(self, source, target):
        """ Uploads the contents of the source directory to the target path. The
            target directory needs to exists. All subdirectories in source are
            created under target.
        """
        for item in os.listdir(source):
            if os.path.isfile(os.path.join(source, item)):
                self.put(os.path.join(source, item), '%s/%s' % (target, item))
            else:
                self.mkdir('%s/%s' % (target, item), ignore_existing=True)
                self.put_dir(os.path.join(source, item), '%s/%s' % (target, item))

    def mkdir(self, path, mode=511, ignore_existing=False):
        """ Augments mkdir by adding an option to not fail if the folder exists  """
        try:
            super(MySFTPClient, self).mkdir(path, mode)
        except IOError:
            if ignore_existing:
                pass
            else:
                raise


####################
# VERSION CHECKING #
####################

def check_npm_version():
    npm_func = info("Checking for npm version >= 5.6.0")

    result = subprocess.run(["npm", "-v"], stdout=subprocess.PIPE, shell=windows)

    if result.returncode == 127:
        npm_func("npm Not Found", False)
    if result.returncode != 0:
        npm_func(f"npm error:\n{result.stdout.decode('utf8')}", False)

    version = parse_semver(result.stdout.decode('utf8'))

    npm_func(f"{stringify_semver(version)}", version >= (5, 6, 0))

    return version


def check_node_version():
    node_func = info("Checking for node version >= 8.11")

    result = subprocess.run(["node", "-v"], stdout=subprocess.PIPE, shell=windows)

    if result.returncode == 127:
        node_func("node Not Found", False)
    if result.returncode != 0:
        node_func(f"node error:\n{result.stdout.decode('utf8')}", False)

    version = parse_semver(result.stdout.decode('utf8'), 'v')

    node_func(f"{stringify_semver(version)}", True)


def get_npm_deps():
    deps_func = info("Retrieving installed npm modules")

    command = ["npm", "-g", "ls", "-depth", "0", "--json"]
    result = subprocess.run(command, stdout=subprocess.PIPE, shell=windows)

    if result.returncode != 0:
        command_text = " ".join(command)
        deps_func(f"command: \"{command_text}\" error:\n{result.stdout}", False)

    installed_deps = json.loads(result.stdout.decode('utf8'))

    deps_func("Done", True)

    def extract_name_semver_pair(dep):
        return dep[0], parse_semver(dep[1]["version"])

    return {dep: ver for dep, ver in map(extract_name_semver_pair, installed_deps["dependencies"].items())}


def check_dep(dependency_dict: Dict[str, Tuple[int]], name: str, version: Tuple[int, int, int]):
    deps_func = info(f"npm package \'{name}\' >= {stringify_semver(version)}")
    try:
        dep_found = dependency_dict[name]
    except KeyError:
        deps_func(f"Not Found.", False)

    # noinspection PyUnboundLocalVariable
    deps_func(f"{stringify_semver(dep_found)}", dep_found >= version)


def check_purgecss():
    purgecss_func = info("Checking for purgecss version >= 1.0.1")

    result = subprocess.run(["purgecss", "-v"], stdout=subprocess.PIPE, shell=windows)

    if result.returncode == 127:
        purgecss_func("Not Found", False)
    if result.returncode != 0:
        purgecss_func(f"purgecss error:\n{result.stdout.decode('utf8')}", False)

    version = parse_semver(result.stdout.decode('utf8'))

    purgecss_func(f"{stringify_semver(version)}", version >= (1, 0, 1))


# noinspection SpellCheckingInspection
def check_postcss():
    #
    # postcss
    #

    postcss_func = info("Checking for postcss version >= 5.0.1")

    result = subprocess.run(["postcss", "--version"], stdout=subprocess.PIPE, shell=windows)

    if result.returncode == 127:
        postcss_func("Not Found", False)
    if result.returncode != 0:
        postcss_func(f"postcss error:\n{result.stdout.decode('utf8')}", False)

    version = parse_semver(result.stdout.decode('utf8'))

    postcss_func(f"{stringify_semver(version)}", version >= (5, 0, 1))

    #
    # cssnano
    #

    cssnano_func = info("postcss plugin \'cssnano\'")

    result_cssnano = subprocess.run(["postcss", "-u", "cssnano"],
                                    input=b" ",
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    shell=windows)

    if result_cssnano.stderr.decode('utf8') == "Plugin Error: Cannot find module 'cssnano'":
        cssnano_func(f"Not Found", False)
    if result_cssnano.returncode != 0:
        cssnano_func(f"postcss error:\n{result_cssnano.stderr.decode('utf8')}", False)

    cssnano_func(f"Found", True)


###############
# BUILD STEPS #
###############

def clear_build_dir():
    clear_func = info("rm -r build build-staging")

    if os.path.isdir('build'):
        shutil.rmtree('build')
    if os.path.isdir('build-staging'):
        shutil.rmtree('build-staging')

    clear_func("Done", True)


def clear_site_run_files():
    clear_func = info("rm static/video_thumbnails/thumb")

    if os.path.exists('static/video_thumbnails/thumb'):
        shutil.rmtree('static/video_thumbnails/thumb')

    clear_func("Done", True)


def create_build_dir():
    build_dir_func = info("mkdir build")

    os.mkdir('build')

    build_dir_func("Done", True)


def copy_static_files():
    static_func = info("Copy static files")

    folders = [x for x in glob('static/*')
               if os.path.join("static", "css") not in x]

    os.mkdir('build/static')

    for f in folders:
        cp.cp(f, 'build/' + f)

    static_func("Done", True)


def get_npm_path():
    prefix_func = info("Finding npm prefix")

    result = subprocess.run(['npm', 'config', 'get', 'prefix'], stdout=subprocess.PIPE, shell=windows)

    if result.returncode != 0:
        prefix_func(f"npm error:\n{result.stdout.decode('utf8')}", False)

    path = result.stdout.decode('utf8').strip()

    prefix_func(path, True)

    return path


def compress_css(npm_module_root: str):
    sumfile_func = info("Creating sum.css")

    css = glob('static/css/*')

    sumfile = ""

    for c in css:
        with open(c, 'r') as f:
            sumfile += f.read()

    os.mkdir('build-staging/')
    with open('build-staging/sum.css', 'w') as f:
        f.write(sumfile)

    cp.cp('build-staging/sum.css', 'build-staging/sum-dce.css')

    sumfile_func("Done", True)

    '''purgecss
       --css build/static/staging/sum-lean.css
       --content templates/**/* templates/*.html
       -o build/static/staging/'''

    html = [val for val in glob("templates/**/*", recursive=True) if not os.path.isdir(val)]

    purge_func = info("CSS Dead Code Elimination")

    purge_args = ['purgecss', '--css', 'build-staging//sum-dce.css', '--content', *html, '-o', 'build-staging//']
    purge_result = subprocess.run(purge_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=windows)

    if purge_result.returncode != 0:
        command = " ".join(purge_args)
        purge_func(f"error while running \'{command}\':\n{purge_result.stdout.decode('utf8')}", False)

    purge_func("Done", True)

    '''NODE_PATH=/usr/lib/node_modules
       postcss
       build-staging/sum-dce.css
       --config postcss.config.js
       --no-map
       -o
       build-staging/sum-min.css'''

    minify_func = info("CSS Minifcation")

    minify_args = ['postcss',
                   'build-staging/sum-dce.css',
                   '--config', 'postcss.config.js',
                   '--no-map',
                   '-o', 'build-staging/sum-min.css']

    current_environ = os.environ.copy()
    if windows:
        current_environ.update({'NODE_PATH': os.path.join(npm_module_root, 'node_modules')})
    else:
        current_environ.update({'NODE_PATH': os.path.join(npm_module_root, 'lib/node_modules')})
    minify_result = subprocess.run(minify_args,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   env=current_environ,
                                   shell=windows)

    if minify_result.returncode != 0:
        command = " ".join(minify_args)
        minify_func(f"error while running \'{command}\':\n{minify_result.stderr.decode('utf8')}", False)

    minify_func("Done", True)

    #
    # copy css
    #

    css_copy_func = info("Copy CSS")

    os.makedirs('build/static/css', exist_ok=True)
    cp.cp('build-staging/sum-min.css', 'build/static/css/sum.css')

    css_copy_func("Done", True)


def copy_python_files():
    python_func = info("Copying Python Files")

    python_files = itertools.chain.from_iterable([glob(g) for g in python_file_globs])

    for f in python_files:
        if f == 'build.py':
            continue

        dir_name = os.path.dirname(f)
        if dir_name != '':
            os.makedirs(os.path.join('build/', dir_name), exist_ok=True)
        cp.cp(f, 'build/' + f)

    python_func("Done", True)


def copy_template_files():
    template_func = info("Copying Template Files")

    template_files = itertools.chain.from_iterable([glob(g) for g in template_file_globs])

    for f in template_files:
        dir_name = os.path.dirname(f)
        if dir_name != '':
            os.makedirs(os.path.join('build/', dir_name), exist_ok=True)
        cp.cp(f, 'build/' + f)

    template_func("Done", True)


##########
# DEPLOY #
##########

def create_ssh_client(ssh_host: str):
    create_func = info("Creating SSH Client")

    client = paramiko.SSHClient()

    if os.path.exists('known_hosts'):
        client.load_host_keys('known_hosts')
    client.connect(ssh_host)

    create_func("Done", True)

    return client


def get_sudo_password():
    return getpass.getpass('\t[sudo] password for remote server: ')


def disable_running_services(ssh_session: paramiko.SSHClient, password: str):
    disable_func = info("Disabling connorwfitzgerald.com")

    stdin, stdout, stderr = ssh_session.exec_command("sudo supervisorctl stop connorwfitzgerald.com", get_pty=True)

    stdin.write(password + '\n')
    stdin.flush()

    if stdout.channel.recv_exit_status() != 0:
        print("stdout:", stdout.read().decode('utf8'))
        print("stderr:", stderr.read().decode('utf8'))
        disable_func("Error", False)

    disable_func("Done", True)


def copy_build(ssh_session: paramiko.SSHClient, path: str):
    copy_func = info("Copying Build")

    sftp: MySFTPClient = ssh_session.open_sftp()
    sftp.__class__ = MySFTPClient
    sftp.put_dir('build', path)

    copy_func("Done", True)


def update_venv(ssh_session: paramiko.SSHClient, path: str):
    disable_func = info("Updating venv")

    stdin, stdout, stderr = ssh_session.exec_command(f"bash -c 'source {path}/venv/bin/activate && "
                                                     f"pip install -r {path}/requirements.txt && "
                                                     f"deactivate'")

    if stdout.channel.recv_exit_status() != 0:
        print("stdout:", stdout.read().decode('utf8'))
        print("stderr:", stderr.read().decode('utf8'))
        disable_func("Error", False)

    disable_func("Done", True)


def enable_running_services(ssh_session: paramiko.SSHClient, password: str):
    disable_func = info("Enabling connorwfitzgerald.com")

    stdin, stdout, stderr = ssh_session.exec_command("sudo supervisorctl start connorwfitzgerald.com", get_pty=True)

    stdin.write(password + '\n')
    stdin.flush()

    if stdout.channel.recv_exit_status() != 0:
        print("stdout:", stdout.read().decode('utf8'))
        print("stderr:", stderr.read().decode('utf8'))

        disable_func("Error", False)

    disable_func("Done", True)


######################
# RELEASE DEV SERVER #
######################

def launch_dev_server():
    dev_func = info("Launching Dev Server")

    try:
        subprocess.run([sys.executable, 'app.py'], cwd='build')
    except KeyboardInterrupt:
        pass

    dev_func("Closed", True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument('--no-dependency-checking', action='store_true')

    choices = parser.add_mutually_exclusive_group()
    choices.add_argument('--release-dev-server', action='store_true')
    choices.add_argument('--deploy', nargs=2)

    parser_result = parser.parse_args()

    server = False
    deploy = False

    if parser_result.release_dev_server:
        server = True
    if parser_result.deploy is not None:
        deploy = True
        ssh_host, ssh_path = parser_result.deploy
    else:
        ssh_host, ssh_path = (None, None)

    build_func = info("\rStarting Build")
    print()

    if not parser_result.no_dependency_checking:
        section_title("General Dependencies")
        check_npm_version()
        check_node_version()
        npm_path = get_npm_path()
        deps = get_npm_deps()
        check_dep(deps, "cssnano", (4, 0, 0))
        check_dep(deps, "cssnano-preset-advanced", (4, 0, 0))
        check_dep(deps, "postcss-cli", (5, 0, 1))
        check_dep(deps, "purgecss", (1, 0, 1))
        check_purgecss()
        check_postcss()
    else:
        npm_path = get_npm_path()

    section_title("Building site")
    clear_build_dir()
    clear_site_run_files()
    create_build_dir()
    copy_static_files()
    copy_python_files()
    copy_template_files()
    compress_css(npm_path)

    build_func("Build Completed", True)

    if deploy:
        password = get_sudo_password()
        print()

        deploy_func = info("\rStarting Deploy")
        print()

        # noinspection PyUnboundLocalVariable
        client = create_ssh_client(ssh_host)

        disable_running_services(client, password)
        copy_build(client, ssh_path)
        update_venv(client, ssh_path)
        enable_running_services(client, password)

        deploy_func("Deploy Finished", True)

    if server:
        section_title("Dev Server")
        launch_dev_server()
