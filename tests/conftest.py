#!/usr/bin/python3
#
# pytest fixture definitions.

import pytest
import util

@pytest.fixture
def bfuse(tmpdir):
    '''A test requesting a "bfuse" is given one via this fixture.'''

    dev = util.format_1g(tmpdir)
    mnt = util.mountpoint(tmpdir)
    bf = util.BFuse(dev, mnt)

    yield bf

    bf.unmount(timeout=5.0)

@pytest.fixture
def valgrind_broken():
    '''A test which is broken with valgrind currently.'''

    util.ENABLE_VALGRIND = False
