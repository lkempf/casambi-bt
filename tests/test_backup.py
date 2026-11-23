"""Offline backups of a network."""

import json
import pathlib
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from bleak.backends.device import BLEDevice

from CasambiBt import BACKUP_FORMAT, Casambi, OfflineBackupError

from .test_offline import (
    ADDRESS,
    UNIT_TYPE,
    UUID,
    FakeCloud,
    make_cache,
)


@pytest.fixture(autouse=True)
def no_bluetooth():
    with patch.object(Casambi, "_connectClient", AsyncMock()) as connect:
        yield connect


async def _export(tmp_path: pathlib.Path) -> dict[str, Any]:
    cloud = FakeCloud()
    cloud.offline = True
    casa = Casambi(cloud.client(), make_cache(tmp_path / "source"))
    await casa.connect(BLEDevice(ADDRESS, "C", None), "pw")
    return await casa.exportOfflineBackup()


async def test_backup_roundtrip_without_cloud(tmp_path: pathlib.Path) -> None:
    """A restored backup connects without any cloud access."""
    backup = await _export(tmp_path)

    # The backup survives a trip through a password manager as text.
    backup = json.loads(json.dumps(backup))
    assert backup["format"] == BACKUP_FORMAT
    assert backup["address"] == ADDRESS
    assert backup["network"]["network"]["keyStore"]["keys"]

    cloud = FakeCloud()
    cloud.offline = True
    target = tmp_path / "target"
    casa = Casambi(cloud.client(), target)
    assert await casa.importOfflineBackup(backup) == ADDRESS

    await casa.connect(BLEDevice(ADDRESS, "C", None), "", preferCache=True)
    assert [u.name for u in casa.units] == ["Lamp 1"]
    assert casa.units[0].unitType == UNIT_TYPE
    assert casa.networkName == "Home"
    assert cloud.requests == []
    assert (target / UUID).stat().st_mode & 0o077 == 0


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b.update(format="something else"),
        lambda b: b.update(version=99),
        lambda b: b.update(address="nope"),
        lambda b: b.update(networkId="../../etc"),
        lambda b: b["network"]["network"].pop("units"),
        lambda b: b["unitTypes"][0]["controls"][0].update(type="NO_SUCH_TYPE"),
        lambda b: b.pop("unitTypes"),
    ],
)
async def test_invalid_backups_are_rejected(
    tmp_path: pathlib.Path, mutate: Any
) -> None:
    backup = await _export(tmp_path)
    mutate(backup)

    casa = Casambi(None, tmp_path / "target")
    with pytest.raises(OfflineBackupError):
        await casa.importOfflineBackup(backup)


async def test_non_mapping_backup_is_rejected(tmp_path: pathlib.Path) -> None:
    casa = Casambi(None, tmp_path)
    with pytest.raises(OfflineBackupError):
        await casa.importOfflineBackup(["not", "a", "backup"])  # type: ignore[arg-type]


async def test_restore_drops_old_session(tmp_path: pathlib.Path) -> None:
    """A restored backup must not reuse a session of an old cache."""
    backup = await _export(tmp_path)
    target = make_cache(tmp_path / "target")

    await Casambi(None, target).importOfflineBackup(backup)

    assert not (target / UUID / "session.pck").exists()
