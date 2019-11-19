#!/usr/bin/python3
#
# Tests of the fuse mount functionality.

import errno
import pytest
import os
import random
import util

pytestmark = pytest.mark.skipif(
    not util.have_fuse(), reason="bcachefs not built with fuse support.")

def test_mount(bfuse):
    bfuse.mount()
    bfuse.unmount()
    bfuse.verify()

def test_remount(bfuse):
    bfuse.mount()
    bfuse.unmount()
    bfuse.mount()
    bfuse.unmount()
    bfuse.verify()

def test_lostfound(bfuse):
    bfuse.mount()

    lf = bfuse.mnt / "lost+found"
    assert lf.is_dir()

    st = lf.stat()
    assert st.st_mode == 0o40700

    bfuse.unmount()
    bfuse.verify()

def test_create(bfuse):
    bfuse.mount()

    path = bfuse.mnt / "file"

    with util.Timestamp() as ts:
        fd = os.open(path, os.O_CREAT, 0o700)

    assert fd >= 0

    os.close(fd)
    assert path.is_file()

    # Verify file.
    st = path.stat()
    assert st.st_mode == 0o100700
    assert st.st_mtime == st.st_ctime
    assert st.st_mtime == st.st_atime
    assert ts.contains(st.st_mtime)

    # Verify dir.
    dst = bfuse.mnt.stat()
    assert dst.st_mtime == dst.st_ctime
    assert ts.contains(dst.st_mtime)

    bfuse.unmount()
    bfuse.verify()

def test_mkdir(bfuse):
    bfuse.mount()

    path = bfuse.mnt / "dir"

    with util.Timestamp() as ts:
        os.mkdir(path, 0o700)

    assert path.is_dir()

    # Verify child.
    st = path.stat()
    assert st.st_mode == 0o40700
    assert st.st_mtime == st.st_ctime
    assert st.st_mtime == st.st_atime
    assert ts.contains(st.st_mtime)

    # Verify parent.
    dst = bfuse.mnt.stat()
    assert dst.st_mtime == dst.st_ctime
    assert ts.contains(dst.st_mtime)

    bfuse.unmount()
    bfuse.verify()

def test_unlink(bfuse):
    bfuse.mount()

    path = bfuse.mnt / "file"
    path.touch(mode=0o600, exist_ok=False)

    with util.Timestamp() as ts:
        os.unlink(path)

    assert not path.exists()

    # Verify dir.
    dst = bfuse.mnt.stat()
    assert dst.st_mtime == dst.st_ctime
    assert ts.contains(dst.st_mtime)

    bfuse.unmount()
    bfuse.verify()

def test_unlink_deletes(bfuse):
    bfuse.mount()

    stv_pre = os.statvfs(bfuse.mnt)
    path = bfuse.mnt / "largefile"

    size = 10 * 1024**2
    path.write_bytes(util.random_bytes(size))

    stv_write = os.statvfs(bfuse.mnt)
    lost_blocks = stv_pre.f_bfree - stv_write.f_bfree
    lost_bytes = lost_blocks * stv_pre.f_bsize

    assert lost_bytes >= size

    path.unlink()

    stv_unlink = os.statvfs(bfuse.mnt)
    gained_blocks = stv_unlink.f_bfree - stv_write.f_bfree
    gained_bytes = gained_blocks * stv_pre.f_bsize

    assert gained_bytes >= size

    bfuse.unmount()
    bfuse.verify()

def test_rmdir(bfuse):
    bfuse.mount()

    path = bfuse.mnt / "dir"
    path.mkdir(mode=0o700, exist_ok=False)

    with util.Timestamp() as ts:
        os.rmdir(path)

    assert not path.exists()

    # Verify dir.
    dst = bfuse.mnt.stat()
    assert dst.st_mtime == dst.st_ctime
    assert ts.contains(dst.st_mtime)

    bfuse.unmount()
    bfuse.verify()

def test_rename(bfuse):
    bfuse.mount()

    srcdir = bfuse.mnt

    path = srcdir / "file"
    path.touch(mode=0o600, exist_ok=False)

    destdir = srcdir / "dir"
    destdir.mkdir(mode=0o700, exist_ok=False)

    destpath = destdir / "file"

    path_pre_st = path.stat()

    with util.Timestamp() as ts:
        os.rename(path, destpath)

    assert not path.exists()
    assert destpath.is_file()

    # Verify dirs.
    src_st = srcdir.stat()
    assert src_st.st_mtime == src_st.st_ctime
    assert ts.contains(src_st.st_mtime)

    dest_st = destdir.stat()
    assert dest_st.st_mtime == dest_st.st_ctime
    assert ts.contains(dest_st.st_mtime)

    # Verify file.
    path_post_st = destpath.stat()
    assert path_post_st.st_mtime == path_pre_st.st_mtime
    assert path_post_st.st_atime == path_pre_st.st_atime
    assert ts.contains(path_post_st.st_ctime)

    bfuse.unmount()
    bfuse.verify()

def test_link(bfuse):
    bfuse.mount()

    srcdir = bfuse.mnt

    path = srcdir / "file"
    path.touch(mode=0o600, exist_ok=False)

    destdir = srcdir / "dir"
    destdir.mkdir(mode=0o700, exist_ok=False)

    destpath = destdir / "file"

    path_pre_st = path.stat()
    srcdir_pre_st = srcdir.stat()

    with util.Timestamp() as ts:
        os.link(path, destpath)

    assert path.exists()
    assert destpath.is_file()

    # Verify source dir is unchanged.
    srcdir_post_st = srcdir.stat()
    assert srcdir_pre_st == srcdir_post_st

    # Verify dest dir.
    destdir_st = destdir.stat()
    assert destdir_st.st_mtime == destdir_st.st_ctime
    assert ts.contains(destdir_st.st_mtime)

    # Verify file.
    path_post_st = path.stat()
    destpath_post_st = destpath.stat()
    assert path_post_st == destpath_post_st

    assert path_post_st.st_mtime == path_pre_st.st_mtime
    assert path_post_st.st_atime == path_pre_st.st_atime
    assert ts.contains(path_post_st.st_ctime)

    bfuse.unmount()
    bfuse.verify()

def test_write(bfuse):
    bfuse.mount()

    path = bfuse.mnt / "file"
    path.touch(mode=0o600, exist_ok=False)

    pre_st = path.stat()

    fd = os.open(path, os.O_WRONLY)
    assert fd >= 0

    with util.Timestamp() as ts:
        written = os.write(fd, b'test')

    os.close(fd)

    assert written == 4

    post_st = path.stat()
    assert post_st.st_atime == pre_st.st_atime
    assert post_st.st_mtime == post_st.st_ctime
    assert ts.contains(post_st.st_mtime)

    assert path.read_bytes() == b'test'

# This test emulates generic/416 in the xfstests suite
def test_fill_4k_files(bfuse_16m):
    bf = bfuse_16m
    bf.mount()

    # Fill filesystem with 4k files
    files = set()
    i = 0
    while True:
        path = bf.mnt / "file{}".format(i)

        #print("Writing to file {}".format(path))
        try:
            path.write_bytes(util.random_bytes(4096))
        except OSError as e:
            if e.errno == errno.ENOSPC:
                break
            raise

        files.add(path)
        i += 1

    print("Wrote {} files.".format(len(files)))

    # Remount filesystem.
    bf.unmount()
    bf.mount()

    # Delete every other file
    deleted = set()
    i = 0
    for path in files:
        if i % 2 == 0:
            path.unlink()
            deleted.add(path)

        i += 1

    files -= deleted

    print("Deleted {} files.".format(len(deleted)))

    # From generic/416, "we should be able to write 1/8 total fs size"
    size = bf.dev.stat().st_size // 8
    print("Writing file of size {}".format(size))

    lf = bf.mnt / 'largefile'
    lf.write_bytes(util.random_bytes(size))

    print("Done.")

    bf.unmount()
    bf.verify()
