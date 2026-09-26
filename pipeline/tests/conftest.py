import json
import os
import sys

import pytest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))
FIXTURES = os.path.join(HERE, "fixtures")


def pytest_configure(config):
    config.addinivalue_line("markers", "live: hits a real upstream service (run with -m live)")


def pytest_collection_modifyitems(config, items):
    if config.getoption("-m"):
        return
    skip = pytest.mark.skip(reason="live network test; run `pytest -m live`")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def fixture_json():
    def _load(name):
        with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
            return json.load(fh)
    return _load
