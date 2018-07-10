from glob import glob
from typing import Tuple, Dict
import colorama
import cp
import json
import os
import itertools
import re
import shutil
import subprocess
import sys
import time


python_file_globs = ['*.py', 'util/*.py', 'requirements.txt']
template_file_globs = ['templates']


windows = os.name == 'nt'


colorama.init()


def section_title(title):
    print("\u001b[37;1m{}\u001b[0m".format(title))


def info(text):
    start = time.perf_counter()

    sys.stdout.write(f"\t{text}... ")
    sys.stdout.flush()

    def done(text: str, success: bool):
        end = time.perf_counter()

        diff = end - start

        sys.stdout.write((f"\u001b[32;1m{text}\u001b[0m" if success else f"\u001b[31;1m{text}\u001b[0m") + f"  ({diff:.2f}s)\n")
        sys.stdout.flush()

        if not success:
            exit(1)

    return done


def parse_semver(input: str, prefix: str = ""):
    reg_result = re.search(f"{prefix}(\\d*)\.(\\d*)\.(\\d*)", input)

    return tuple(map(int, reg_result.group(1, 2, 3)))


def stringify_semver(input: Tuple[int, int, int]):
    return ".".join(map(str, input))


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


def get_npm_path():
    prefix_func = info("Finding npm prefix")

    result = subprocess.run(['npm', 'config', 'get', 'prefix'], stdout=subprocess.PIPE, shell=windows)

    if result.returncode != 0:
        prefix_func(f"npm error:\n{result.stdout.decode('utf8')}")

    path = result.stdout.decode('utf8').strip()

    prefix_func(path, True)

    return path


def get_npm_deps():
    deps_func = info("Retrieving installed npm modules")

    command = ["npm", "-g", "ls", "-depth", "0", "--json"]
    result = subprocess.run(command, stdout=subprocess.PIPE, shell=windows)

    if result.returncode != 0:
        command_text = " ".join(command)
        deps_func(f"command: \"{command_text}\" error:\n{result.stdout}", False)

    installed_deps = json.loads(result.stdout.decode('utf8'))

    deps_func("Done", True)

    return {dep : ver for dep, ver in map(lambda dep: (dep[0], parse_semver(dep[1]["version"])), installed_deps["dependencies"].items())}


def check_dep(deps: Dict[str, Tuple[int]], name: str, version: Tuple[int, int, int]):
    deps_func = info(f"npm package \'{name}\' >= {stringify_semver(version)}")
    try:
        dep_found = deps[name]
    except KeyError:
        deps_func(f"Not Found.", False)

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

    result_cssnano = subprocess.run(["postcss", "-u", "cssnano"], input=b" ", stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=windows)

    if result_cssnano.stderr.decode('utf8') == "Plugin Error: Cannot find module 'cssnano'":
        cssnano_func(f"Not Found", False)
    if result_cssnano.returncode != 0:
        cssnano_func(f"postcss error:\n{result_cssnano.stderr.decode('utf8')}", False)

    cssnano_func(f"Found", True)


def clear_builddir():
    clear_func = info("rm -r build build-staging")

    if os.path.isdir('build'):
        shutil.rmtree('build')
    if os.path.isdir('build-staging'):
        shutil.rmtree('build-staging')

    clear_func("Done", True)


def create_builddir():
    builddir_func = info("mkdir build")

    os.mkdir('build')

    builddir_func("Done", True)


def copy_static_files():
    static_func = info("Copy static files")

    folders = [x for x in glob('static/*') if x != 'static/css']
    os.mkdir('build/static')

    for f in folders:
        cp.cp(f, 'build/' + f)

    static_func("Done", True)


def compress_css(npm_path: str):
    sumfile_func = info("Creating sum.css")

    css = glob('static/css/*')

    sumfile = ""

    for c in css:
        with open(c, 'r') as f:
            sumfile += f.read()

    os.mkdir('build-staging/')
    with open('build-staging//sum.css', 'w') as f:
        f.write(sumfile)

    cp.cp('build-staging//sum.css', 'build-staging//sum-dce.css')

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
        purge_func(f"error while running \'{command}\':\n{purge_result.stdout.decode('utf8')}")

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

    minify_result = subprocess.run(minify_args,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   env={'NODE_PATH': os.path.join(npm_path, 'lib/node_modules')})

    if minify_result.returncode != 0:
        command = " ".join(purge_args)
        minify_func(f"error while running \'{command}\':\n{purge_result.stderr.decode('utf8')}", False)

    minify_func("Done", True)


def copy_python_files():
    python_func = info("Copying Python Files")

    python_files = itertools.chain.from_iterable([glob(g) for g in python_file_globs])

    for f in python_files:
        if f == 'build.py':
            continue

        dirname = os.path.dirname(f)
        if dirname != '':
            os.makedirs(os.path.join('build/', dirname), exist_ok=True)
        cp.cp(f, 'build/' + f)

    python_func("Done", True)


def copy_template_files():
    template_func = info("Copying Template Files")

    template_files = itertools.chain.from_iterable([glob(g) for g in template_file_globs])

    for f in template_files:
        dirname = os.path.dirname(f)
        if dirname != '':
            os.makedirs(os.path.join('build/', dirname), exist_ok=True)
        cp.cp(f, 'build/' + f)

    template_func("Done", True)


if __name__ == "__main__":
    build_func = info("\rStarting Build")
    print()

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

    section_title("Building site")
    clear_builddir()
    create_builddir()
    copy_static_files()
    copy_python_files()
    copy_template_files()
    compress_css(npm_path)

    build_func("Build Completed", True)
