#ifndef _FUSE_INODE_H
#define _FUSE_INODE_H

#include <linux/types.h>

struct bf_inode;

void bf_inode_init(void);

void bf_inode_destroy(void);

struct bf_inode *bf_inode_get(uint64_t ino);

struct bf_inode *bf_inode_get_ref(uint64_t ino);

bool bf_inode_unlink(uint64_t ino);

bool bf_inode_put(uint64_t ino, uint64_t release_count);

#endif /* _FUSE_INODE_H */
