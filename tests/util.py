#!/usr/bin/python3

import os
import pytest
import random
import re
import subprocess
import sys
import tempfile
import threading
import time

from pathlib import Path

DIR = Path('..')
BCH_PATH = DIR / 'bcachefs'

VPAT = re.compile(r'ERROR SUMMARY: (\d+) errors from (\d+) contexts')

ENABLE_VALGRIND = os.getenv('BCACHEFS_TEST_USE_VALGRIND', 'yes') == 'yes'

class ValgrindFailedError(Exception):
    def __init__(self, log):
        self.log = log

def check_valgrind(logfile):
    log = logfile.read().decode('utf-8')
    m = VPAT.search(log)
    assert m is not None, 'Internal error: valgrind log did not match.'

    errors = int(m.group(1))
    if errors > 0:
        raise ValgrindFailedError(log)

def run(cmd, *args, valgrind=False, check=False):
    """Run an external program via subprocess, optionally with valgrind.

    This subprocess wrapper will capture the stdout and stderr. If valgrind is
    requested, it will be checked for errors and raise a
    ValgrindFailedError if there's a problem.
    """
    cmds = [cmd] + list(args)
    valgrind = valgrind and ENABLE_VALGRIND

    if valgrind:
        vout = tempfile.NamedTemporaryFile()
        vcmd = ['valgrind',
               '--leak-check=full',
               '--log-file={}'.format(vout.name)]
        cmds = vcmd + cmds

    print("Running '{}'".format(cmds))
    res = subprocess.run(cmds, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         encoding='utf-8', check=check)

    if valgrind:
        check_valgrind(vout)

    return res

def run_bch(*args, **kwargs):
    """Wrapper to run the bcachefs binary specifically."""
    cmds = [BCH_PATH] + list(args)
    return run(*cmds, **kwargs)

def sparse_file(lpath, size):
    """Construct a sparse file of the specified size.

    This is typically used to create device files for bcachefs.
    """
    path = Path(lpath)
    f = path.touch(mode = 0o600, exist_ok = False)
    os.truncate(path, size)

    return path

def device(tmpdir, name, size):
    """Create a sparse file for use with bcachefs format."""
    path = Path(tmpdir) / name
    return sparse_file(path, size)

def format_dev(tmpdir, name, size):
    """Format a default filesystem on specified device."""
    dev = device(tmpdir, name, size)
    run_bch('format', dev, check=True)
    return dev

def format_1g(tmpdir):
    """Format a default filesystem on a 1g device."""
    return format_dev(tmpdir, 'dev-1g', 1024**3)

def mountpoint(tmpdir):
    """Construct a mountpoint "mnt" for tests."""
    path = Path(tmpdir) / 'mnt'
    path.mkdir(mode = 0o700)
    return path

class Timestamp:
    '''Context manager to assist in verifying timestamps.

    Records the range of times which would be valid for an encoded operation to
    use.

    FIXME: The kernel code is currently using CLOCK_REALTIME_COARSE, but python
    didn't expose this time API (yet).  Probably the kernel shouldn't be using
    _COARSE anyway, but this might lead to occasional errors.

    To make sure this doesn't happen, we sleep a fraction of a second in an
    attempt to guarantee containment.

    N.B. this might be better tested by overriding the clock used in bcachefs.

    '''
    def __init__(self):
        self.start = None
        self.end = None

    def __enter__(self):
        self.start = time.clock_gettime(time.CLOCK_REALTIME)
        time.sleep(0.1)
        return self

    def __exit__(self, type, value, traceback):
        time.sleep(0.1)
        self.end = time.clock_gettime(time.CLOCK_REALTIME)

    def contains(self, test):
        '''True iff the test time is within the range.'''
        return self.start <= test <= self.end

class FuseError(Exception):
    def __init__(self, msg):
        self.msg = msg

class BFuse:
    '''bcachefs fuse runner.

    This class runs bcachefs in fusemount mode, and waits until the mount has
    reached a point suitable for testing the filesystem.

    bcachefs is run under valgrind by default, and is checked for errors.
    '''

    def __init__(self, dev, mnt):
        self.thread = None
        self.dev = dev
        self.mnt = mnt
        self.ready = threading.Event()
        self.proc = None
        self.returncode = None
        self.stdout = None
        self.stderr = None
        self.vout = None

    def run(self):
        """Background thread which runs "bcachefs fusemount" under valgrind"""

        vout = None
        cmd = []

        if ENABLE_VALGRIND:
            vout = tempfile.NamedTemporaryFile()
            cmd += [ 'valgrind',
                     '--leak-check=full',
                     '--log-file={}'.format(vout.name) ]

        cmd += [ BCH_PATH,
                 'fusemount', '-f', self.dev, self.mnt]

        print("Running {}".format(cmd))

        err = tempfile.TemporaryFile(mode='w+', encoding='utf-8')
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err,
                                     encoding='utf-8')

        out1 = self.expect(self.proc.stdout, r'^Fuse mount initialized.$')
        self.ready.set()

        print("Waiting for process.")
        (out2, _) = self.proc.communicate()
        print("Process exited.")

        err.seek(0)

        self.stdout = out1 + out2
        self.stderr = err.read()
        self.returncode = self.proc.returncode
        self.vout = vout

    def expect(self, pipe, regex):
        """Wait for the child process to mount."""

        c = re.compile(regex)

        out = ""
        while True:
            line = pipe.readline()
            print('Expect line "{}"'.format(line.rstrip()))
            out += line
            if c.match(line):
                print("Matched.")
                return out

        raise FuseError('stdout did not contain regex "{}"'.format(regex))

    def mount(self):
        print("Starting fuse thread.")

        assert not self.thread
        self.thread = threading.Thread(target=self.run)
        self.thread.start()

        self.ready.wait()
        print("Fuse is mounted.")

    def unmount(self, timeout=None):
        if not self.thread:
            return

        print("Unmounting fuse.")
        run("fusermount3", "-zu", self.mnt)
        print("Waiting for thread to exit.")

        self.thread.join(timeout)
        if self.thread.is_alive():
            self.proc.kill()
            self.thread.join()

        self.thread = None
        self.ready.clear()

        if self.vout:
            check_valgrind(self.vout)

    def verify(self):
        assert self.returncode == 0
        assert len(self.stdout) > 0
        #assert len(self.stderr) == 0

def have_fuse():
    res = run(BCH_PATH, 'fusemount', valgrind=False)
    return "Please supply a mountpoint." in res.stdout

def random_bytes(size):
    """Construct a bytearray full of random data."""
    return bytearray(random.getrandbits(8) for _ in range(size))
