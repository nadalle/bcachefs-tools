#ifdef BCACHEFS_FUSE

#include <errno.h>

#include "libbcachefs/bcachefs.h"

struct bf_inode {
	uint64_t		key;
	uint64_t		open_count;
	bool			unlinked;

	struct rhash_head	hash;
};

static DEFINE_MUTEX(lock);
static struct rhashtable table;

static const struct rhashtable_params params = {
	.head_offset = offsetof(struct bf_inode, hash),
	.key_offset  = offsetof(struct bf_inode, key),
	.key_len     = sizeof(uint64_t),
};

void bf_inode_init(void)
{
	int ret = rhashtable_init(&table, &params);
	if (ret)
		die("rhashtable_init err %m");
}

/*
 * Free the inode cache, unreffing and calling unref_fn on all remaining
 * entries in the cache.
 */
void bf_inode_destroy(void)
{
	// XXX destroy each entry, missing free-and-destroy fn.
	rhashtable_destroy(&table);
}

static struct bf_inode *__bf_inode_get(uint64_t ino)
{
	struct bf_inode *bfi;

	bfi = rhashtable_lookup_fast(&table, &ino, params);
	if (bfi)
		return bfi;

	bfi = calloc(1, sizeof *bfi);
	if (!bfi)
		return ERR_PTR(-ENOMEM);

	bfi->key = ino;
	bfi->open_count = 0;

	int ret = rhashtable_lookup_insert_fast(&table, &bfi->hash, params);
	BUG_ON(ret == EEXIST);

	return bfi;
}

struct bf_inode *bf_inode_get(uint64_t ino)
{
	mutex_lock(&lock);
	struct bf_inode *bfi = __bf_inode_get(ino);
	mutex_unlock(&lock);

	return bfi;
}

/*
 * Lookup the given inode and acquire a new open ref on it.
 */
struct bf_inode *bf_inode_get_ref(uint64_t ino)
{
	mutex_lock(&lock);
	struct bf_inode *bfi = __bf_inode_get(ino);
	if (IS_ERR(bfi))
		goto out;

	++bfi->open_count;

out:
	mutex_unlock(&lock);

	return bfi;
}


/**
 * Mark an inode unlinked.  This is cached so we can tell if the inode needs to
 * be deleted when the last reference goes away.
 *
 * @return true If there were no references on the inode, false if the inode is
 * open.
 */
bool bf_inode_unlink(uint64_t ino)
{
	struct bf_inode *bfi;

	mutex_lock(&lock);
	bfi = rhashtable_lookup_fast(&table, &ino, params);
	if (bfi)
		bfi->unlinked = true;
	mutex_unlock(&lock);

	return bfi == NULL;
}

/**
 * Release a given inode this number of times.
 *
 * @return true if the inode can be deleted, false otherwise.
 */
bool bf_inode_put(uint64_t ino, uint64_t release_count)
{
	bool delete = false;

	mutex_lock(&lock);
	struct bf_inode *bfi = __bf_inode_get(ino);
	BUG_ON(!bfi);
	BUG_ON(IS_ERR(bfi));
	BUG_ON(bfi->open_count < release_count);

	bfi->open_count -= release_count;

	if (bfi->open_count > 0)
		goto out;

	delete = bfi->unlinked;

	int ret = rhashtable_remove_fast(&table, &bfi->hash, params);
	BUG_ON(ret);

	free(bfi);

out:
	mutex_unlock(&lock);

	return delete;
}

#endif
