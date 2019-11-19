#!/usr/bin/python3
#
# pytest fixture definitions.

import pytest
import util

def fuse_fixture(tmpdir, size):
    dev = util.format_dev(tmpdir, 'dev', size)
    mnt = util.mountpoint(tmpdir)
    bf = util.BFuse(dev, mnt)

    yield bf

    if bf.returncode is None:
        bf.unmount(timeout=5.0)

@pytest.fixture
def bfuse(tmpdir):
    '''A test requesting a "bfuse" is given one via this fixture.'''

    yield from fuse_fixture(tmpdir, 1024**3)

@pytest.fixture
def bfuse_16m(tmpdir):
    '''A test requesting a 16 MiB size "bfuse".'''

    yield from fuse_fixture(tmpdir, 16 * 1024**2)
