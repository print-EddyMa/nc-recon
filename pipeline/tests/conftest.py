import json
import os
import sys

import pytest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))
FIXTURES = os.path.join(HERE, "fixtures")


def pytest_configure(config):
    config.addinivalue_line("markers", "live: hits a real upstream service (run with -m live)")
    # Runtime state goes to a throwaway directory for the whole session, set
    # before anything imports the package. The suite reads the committed config
    # and any local assessment outputs, but it must never write to (or prune)
    # the live operational registry, the job list or the audit log: a test run
    # beside a working server once deleted an assessment that was in progress.
    import tempfile

    state = tempfile.mkdtemp(prefix="ncr-test-state-")
    os.environ["NCR_OPS_REGISTRY"] = os.path.join(state, "ops_registry.yaml")
    os.environ["NCR_JOBS_FILE"] = os.path.join(state, "jobs.json")
    os.environ["NCR_AUDIT_LOG"] = os.path.join(state, "audit.log")
    os.environ["NCR_TRUTH_DIR"] = os.path.join(state, "truth")
    os.environ["NCR_LABELS_DIR"] = os.path.join(state, "labels")
    # one TestClient is every "client" at once; keep the per-client limiter out of the way
    os.environ.setdefault("NCR_RATE_READ_PER_MIN", "100000")
    os.environ.setdefault("NCR_RATE_WRITE_PER_MIN", "100000")
    os.environ.setdefault("NCR_RATE_FEED_PER_MIN", "100000")


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
