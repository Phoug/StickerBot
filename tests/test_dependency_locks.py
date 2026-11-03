"""Catch changed requirements that were not reflected in the checked-in locks."""
from importlib.metadata import distribution
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]


def requirements(path):
    return [Requirement(line) for value in path.read_text().splitlines()
            if (line := value.split("#", 1)[0].strip()) and not line.startswith("-")]


def test_lock_files_cover_inputs_and_runtime_transitive_dependencies():
    runtime = requirements(ROOT / "requirements.lock")
    testing = requirements(ROOT / "tests/requirements.lock")
    locked = {canonicalize_name(req.name): req for req in runtime + testing}
    extras = {}
    for source in ("app/requirements.txt", "backend/requirements.txt", "tests/requirements.txt"):
        for req in requirements(ROOT / source):
            pinned = locked[canonicalize_name(req.name)]
            version = next(iter(pinned.specifier)).version
            assert req.specifier.contains(version), (source, req, version)
            extras.setdefault(canonicalize_name(req.name), set()).update(req.extras)
    runtime_names = {canonicalize_name(req.name) for req in runtime}
    for req in runtime:
        version = distribution(req.name).version
        assert req.specifier.contains(version), (req.name, version)
        for value in distribution(req.name).requires or []:
            dependency = Requirement(value)
            if dependency.marker is None or any(dependency.marker.evaluate({"extra": extra}) for extra in ["", *req.extras, *extras.get(canonicalize_name(req.name), set())]):
                assert canonicalize_name(dependency.name) in runtime_names, (req.name, dependency)
