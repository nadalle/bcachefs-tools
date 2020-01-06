#!/usr/bin/python3
#
# Tests of the fuse mount functionality.

import pytest
import os
import time
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

def test_unlink_metadata(bfuse):
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

def test_rmdir_metadata(bfuse):
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

    bfuse.unmount()
    bfuse.verify()

def test_unlink_data(bfuse):
    bfuse.mount()

    path = bfuse.mnt / "file"

    SIZE = 1024**2 * 50

    def free_bytes(stv):
        return stv.f_bfree * stv.f_frsize

    stv_pre_write = os.statvfs(bfuse.mnt)

    path.write_bytes(b'*' * 1024**2 * 50)

    stv_post_write = os.statvfs(bfuse.mnt)

    assert free_bytes(stv_pre_write) - free_bytes(stv_post_write) >= SIZE

    path.unlink()

    # wait for the possibly asynchronous unlink to happen.
    while os.statvfs(bfuse.mnt).f_files != stv_pre_write.f_files:
        time.sleep(0.5)

    stv_post_unlink = os.statvfs(bfuse.mnt)

    assert free_bytes(stv_pre_write) - free_bytes(stv_post_unlink) == \
        pytest.approx(128*1024)

    bfuse.unmount()
    bfuse.verify()

def test_unlink_inode_count(bfuse):
    bfuse.mount()

    path1 = bfuse.mnt / "file"
    path2 = bfuse.mnt / "dir"
    path3 = bfuse.mnt / "symlink"
    path4 = bfuse.mnt / "node"

    stv_pre_write = os.statvfs(bfuse.mnt)

    path1.touch()
    path2.mkdir()
    path3.symlink_to(path1)
    os.mkfifo(path4)

    stv_post_write = os.statvfs(bfuse.mnt)

    assert stv_post_write.f_files - stv_pre_write.f_files == 4

    path1.unlink()
    path2.rmdir()
    path3.unlink()
    path4.unlink()

    # The actual inode deletes are somewhat asynchronous
    while os.statvfs(bfuse.mnt).f_files != stv_pre_write.f_files:
        time.sleep(0.5)

    bfuse.unmount()
    bfuse.verify()

def test_unlink_open_file(bfuse):
    bfuse.mount()

    path = bfuse.mnt / "file"
    SIZE = 1024**2 * 10

    def free_bytes(stv):
        return stv.f_bfree * stv.f_frsize

    stv_pre_open = os.statvfs(bfuse.mnt)
    with open(path, "wb+") as f:
        stv_pre_write = os.statvfs(bfuse.mnt)

        f.write(b'*' * SIZE)
        f.flush()
        os.fsync(f.fileno())

        stv_post_write1 = os.statvfs(bfuse.mnt)
        assert free_bytes(stv_pre_write) - free_bytes(stv_post_write1) >= SIZE

        path.unlink()

        stv_post_unlink = os.statvfs(bfuse.mnt)
        assert free_bytes(stv_post_unlink) == free_bytes(stv_post_write1)
        assert stv_post_write1.f_files == stv_post_unlink.f_files

        # Verify we can still write
        f.write(b'+' * SIZE)
        f.flush()
        os.fsync(f.fileno())

        stv_post_write2 = os.statvfs(bfuse.mnt)
        assert free_bytes(stv_pre_write) - free_bytes(stv_post_write2) >= 2*SIZE

        # Verify correctness of data
        f.seek(0);
        data = f.read()
        assert(data[0:SIZE] == b'*' * SIZE)
        assert(data[SIZE:]  == b'+' * SIZE)

    # It should be deleted soon, but since it's asynchronous we have to poll
    while os.statvfs(bfuse.mnt).f_files != stv_pre_open.f_files:
        time.sleep(0.5)

    stv_post_close = os.statvfs(bfuse.mnt)
    assert stv_pre_open.f_files == stv_post_close.f_files
    assert free_bytes(stv_pre_open) - free_bytes(stv_post_close) == \
        pytest.approx(128*1024)

    bfuse.unmount()
    bfuse.verify()
