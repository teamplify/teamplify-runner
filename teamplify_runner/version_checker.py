from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from datetime import datetime
from json.decoder import JSONDecodeError
from pathlib import Path

import requests


PYPI_URL = 'https://pypi.org/pypi/teamplify/json'
PYPI_TIMEOUT_SECONDS = 5
VERSION_CACHE_FILE_NAME = 'teamplify-version-check.json'
VERSION_CACHE_TTL_SECONDS = 12 * 60 * 60  # 12 hours


@dataclass
class VersionCache:
    latest_version: str
    checked_at: datetime

    def dump(self):
        return json.dumps(
            {
                'latest_version': self.latest_version,
                'checked_at': self.checked_at.isoformat(),
            }
        )


def _read_version_cache(version_file: Path) -> VersionCache | None:
    try:
        with version_file.open() as f:
            file_data = f.read()
        try:
            cache = json.loads(file_data)
            latest, checked_at = cache['latest_version'], cache['checked_at']
            assert isinstance(latest, str)
            assert isinstance(checked_at, str)
            checked_at = datetime.fromisoformat(checked_at)
        except (JSONDecodeError, AssertionError, KeyError, ValueError):
            # The file is corrupted, remove it
            version_file.unlink()
        else:
            return VersionCache(latest_version=latest, checked_at=checked_at)
    except FileNotFoundError:
        pass


def _fetch_latest_version() -> str | None:
    try:
        response = requests.get(PYPI_URL, timeout=PYPI_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()['info']['version']
    except (requests.RequestException, ValueError, KeyError):
        pass


def _write_version_cache(version_file: Path, version_cache: VersionCache):
    try:
        version_file.write_text(version_cache.dump())
    except Exception:
        pass


def get_latest_version() -> str | None:
    temp_dir = tempfile.gettempdir()
    version_file = Path(temp_dir) / VERSION_CACHE_FILE_NAME

    version_cache = _read_version_cache(version_file)
    if (
        version_cache
        and (datetime.now() - version_cache.checked_at).total_seconds() < VERSION_CACHE_TTL_SECONDS
    ):
        return version_cache.latest_version

    latest = _fetch_latest_version()
    if latest:
        _write_version_cache(
            version_file,
            VersionCache(latest_version=latest, checked_at=datetime.now()),
        )

    return latest


def is_update_available(curr_version: str, new_version: str) -> bool:
    curr_version_tuple = [int(part) for part in curr_version.split('.')]
    new_version_tuple = [int(part) for part in new_version.split('.')]
    return new_version_tuple > curr_version_tuple
