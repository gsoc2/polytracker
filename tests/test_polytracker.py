import sys

if sys.version_info < (3, 7):
    sys.exit('This script must be run with at least Python 3.7')

import contextlib
import os
# import pytest

import subprocess

from os.path import dirname, join as join, realpath
from pathlib import Path
from shutil import which
from subprocess import check_call, run

from typing import Generator, Optional

try:
    assert False
except AssertionError:
    pass
else:
    sys.exit("Error: assertions don't seem to be enabled?!")


################################################################################
# Utilities
################################################################################
def _find_program(name: str) -> str:
    res = which(name)
    if res is None:
        raise ValueError(f"unable to find `{name}` -- perhaps it's not in your PATH?")
    return res


# Cribbed from here: https://stackoverflow.com/a/24176022/201217
#
# Also yields the previous directory after changing, so you can use like
#
#     with chdir(new_dir) as prev_dir:
#         ...
@contextlib.contextmanager
def chdir(d) -> Generator[str, None, None]:
    prev_d = os.getcwd()
    os.chdir(d)
    try:
        yield prev_d
    finally:
        os.chdir(prev_d)


################################################################################
# Globals
################################################################################
PC: str = _find_program('polyclang')
PCPP: str = _find_program('polyclang++')
TESTS_DIR = realpath(dirname(__file__))

EXPECTED_STDERR_NO_POLYPATH = b"Unable to get required POLYPATH environment variable -- perhaps it's not set?\n"


################################################################################
# Test cases here!
################################################################################
def test_test1_no_polypath(tmpdir) -> None:
    with chdir(tmpdir):
        check_call([PC, '-Wall', '-O2', join(TESTS_DIR, 'test1.c'), '-o', 'test1'])
        p = run(['./test1'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert p.stdout == b""
        assert p.stderr == EXPECTED_STDERR_NO_POLYPATH
        assert p.returncode == 1


# TODO Check compile C, compile C++
# TODO Check indexing 0
# TODO Check setjmp/longjmp

def test_test1(tmpdir) -> None:
    f = join(TESTS_DIR, 'test1.c')
    env = os.environ.copy()
    env['POLYPATH'] = f
    with chdir(tmpdir):
        check_call([PC, '-Wall', '-O2', f, '-o', 'test1'])
        check_call(['./test1'], env=env)


def test_test2_no_polypath(tmpdir) -> None:
    with chdir(tmpdir):
        check_call([PCPP, '-Wall', '-O2', join(TESTS_DIR, 'test2.cpp'), '-o', 'test2'])
        p = run(['./test2'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert p.stdout == b""
        assert p.stderr == EXPECTED_STDERR_NO_POLYPATH
        assert p.returncode == 1


def test_test2(tmpdir) -> None:
    f = join(TESTS_DIR, 'test1.c')
    env = os.environ.copy()
    env['POLYPATH'] = f
    with chdir(tmpdir):
        check_call([PCPP, '-Wall', '-O2', join(TESTS_DIR, 'test2.cpp'), '-o', 'test2'])
        check_call(['./test2'], env=env)
