import json
from pathlib import Path

import pytest

from kicad2cad import load

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
BADGE = ROOT / "Archive 2" / "badge.kicad_pcb"


@pytest.fixture(scope="session")
def badge():
    return load(BADGE)


@pytest.fixture(scope="session")
def testboard():
    return load(FIXTURES / "testboard.kicad_pcb")


@pytest.fixture(scope="session")
def expected():
    return json.loads((FIXTURES / "testboard.expected.json").read_text())
