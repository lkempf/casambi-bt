"""Tests for the Cache module."""

import pathlib

import pytest
from anyio import Path

from CasambiBt._cache import CACHE_VERSION, Cache


async def test_cache_init_default():
    """Test default path initialization."""
    c = Cache(None)
    assert c._cachePath.name == "casambi-bt-store"


async def test_cache_init_custom(tmp_path: pathlib.Path):
    """Test custom path initialization."""
    custom_path = tmp_path / "custom_cache"
    c = Cache(custom_path)
    assert str(c._cachePath) == str(custom_path)


async def test_cache_set_uuid(tmp_path: pathlib.Path):
    """Test setting the UUID."""
    c = Cache(tmp_path)
    await c.setUuid("test-uuid")
    assert c._uuid == "test-uuid"


async def test_cache_context_manager_creates_dirs(tmp_path: pathlib.Path):
    """Test that the context manager creates necessary directories."""
    c = Cache(tmp_path)
    uuid = "test-uuid-1"
    await c.setUuid(uuid)

    async with c as cache_dir:
        assert isinstance(cache_dir, Path)
        assert str(cache_dir).endswith(uuid)
        assert await cache_dir.exists()

    # Check version file was created in the parent cache directory
    version_file = Path(tmp_path) / ".cachever"
    assert await version_file.exists()
    assert await version_file.read_text() == str(CACHE_VERSION)


async def test_cache_context_manager_missing_uuid(tmp_path: pathlib.Path):
    """Test that context manager raises ValueError if UUID is not set."""
    c = Cache(tmp_path)
    # No UUID set, should raise ValueError
    with pytest.raises(ValueError, match="UUID not set"):
        async with c:
            pass


async def test_cache_validation_old_version(tmp_path: pathlib.Path):
    """Test that cache is recreated if version is old."""
    c = Cache(tmp_path)
    uuid = "test-uuid-2"
    await c.setUuid(uuid)

    # Manually create old version file
    # Ensure directory exists first
    tmp_path.mkdir(exist_ok=True)
    version_file = tmp_path / ".cachever"
    version_file.write_text("1")

    # Create some dummy data in cache to verify it gets wiped
    dummy_dir = tmp_path / uuid
    dummy_dir.mkdir(parents=True, exist_ok=True)
    (dummy_dir / "data.txt").write_text("old data")

    async with c as cache_dir:
        # Should have recreated cache because version was old
        assert await cache_dir.exists()

    # Verify version file is updated
    assert version_file.read_text() == str(CACHE_VERSION)

    # Verify old data is gone (the file should have been deleted when cache was wiped)
    assert not (tmp_path / uuid / "data.txt").exists()


async def test_cache_validation_invalid_version_file(tmp_path: pathlib.Path):
    """Test handling of invalid version file."""
    c = Cache(tmp_path)
    await c.setUuid("uuid")

    # Create invalid version file
    tmp_path.mkdir(exist_ok=True)
    version_file = tmp_path / ".cachever"
    version_file.write_text("invalid")

    async with c as cache_dir:
        assert await cache_dir.exists()

    # It should have reset to current version
    assert version_file.read_text() == str(CACHE_VERSION)


async def test_invalidate_cache(tmp_path: pathlib.Path):
    """Test cache invalidation (deletion)."""
    c = Cache(tmp_path)
    uuid = "test-uuid-3"
    await c.setUuid(uuid)

    # Create the cache entry
    async with c as cache_dir:
        assert await cache_dir.exists()
        # Create a file inside
        await (cache_dir / "some_file").touch()

    # Now invalidate
    await c.invalidateCache()

    # Check that the specific UUID folder is gone
    assert not (tmp_path / uuid).exists()
    # Check that the main cache folder still exists (and version file)
    assert (tmp_path / ".cachever").exists()


async def test_invalidate_cache_no_uuid(tmp_path: pathlib.Path):
    """Test invalidateCache raises ValueError if UUID is not set."""
    c = Cache(tmp_path)
    with pytest.raises(ValueError, match="UUID not set"):
        await c.invalidateCache()


async def test_cache_creates_missing_parents(tmp_path: pathlib.Path):
    """The cache can live below directories that don't exist yet."""
    cache = Cache(tmp_path / "missing" / "parents" / "cache")
    await cache.setUuid("uuid")
    async with cache as cache_path:
        assert await cache_path.exists()
