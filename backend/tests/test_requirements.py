"""The backend's runtime libraries are listed in three places, and the lists must agree.

Vercel installs from pyproject.toml, local setup and CI install from backend/requirements.txt, and
requirements.txt at the repository root lists them for anyone starting from the top folder.
"""

import tomllib
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _requirements(path: Path) -> list[str]:
    lines = (line.strip() for line in path.read_text().splitlines())
    return sorted(line for line in lines if line and not line.startswith("#"))


def test_pyproject_lists_the_same_libraries_as_requirements_txt():
    project = tomllib.loads((BACKEND / "pyproject.toml").read_text())["project"]
    assert sorted(project["dependencies"]) == _requirements(BACKEND / "requirements.txt")


def test_root_requirements_txt_matches_the_backend_list():
    root = _requirements(BACKEND.parent / "requirements.txt")
    assert root == _requirements(BACKEND / "requirements.txt")
