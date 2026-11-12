from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_ROOM = REPO_ROOT / "sample-dataroom"


@pytest.fixture
def sample_room() -> Path:
    return SAMPLE_ROOM
