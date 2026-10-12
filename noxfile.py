"""Nox sessions."""

import os
import shutil
import tempfile
from pathlib import Path

import nox
from nox.sessions import Session


package = "pybuild_deps"
python_versions = ["3.13", "3.12", "3.11", "3.10"]
nox.options.sessions = (
    "pre-commit",
    "tests",
    "docs-build",
)
nox.options.reuse_venv = "always"
nox.options.default_venv_backend = "uv"
test_requirements = ["pytest", "pytest-cov", "pytest-mock", "pytest-xdist"]


@nox.session(name="pre-commit", python=python_versions[0])
def precommit(session: Session) -> None:
    """Lint using pre-commit."""
    args = session.posargs or [
        "run",
        "--all-files",
        "--hook-stage=manual",
        "--show-diff-on-failure",
    ]
    session.install(
        "ruff",
        "pre-commit",
        "pre-commit-hooks",
        "pydoclint",
    )
    session.run("pre-commit", *args)


@nox.session(python=python_versions)
def tests(session: Session) -> None:
    """Run unit tests (excludes e2e tests that require network access)."""
    session.install(".")
    session.install(*test_requirements)
    args = ["-m", "not e2e"]
    if not session.posargs:
        args += [
            "--cov=pybuild_deps",
            "--cov-report=term",
            "--cov-report=xml",
            "--no-cov-on-fail",
        ]
    session.run("pytest", *args, *session.posargs)


@nox.session(name="dist-check", python=python_versions[0])
def dist_check(session: Session) -> None:
    """Build the wheel and sdist, check them, and smoke-test each install.

    The single source of the dist build and validation: CI runs it on every push
    and PR, and the release workflow runs the same session before publishing, so
    the two paths can't drift.
    """
    dist_dir = Path("dist")
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    # NO_COLOR: CI sets FORCE_COLOR, which would otherwise wrap the output in ANSI
    # codes and break the version comparison below. NO_COLOR overrides FORCE_COLOR.
    version = session.run(
        "uv",
        "version",
        "--short",
        env={"NO_COLOR": "1"},
        external=True,
        silent=True,
    ).strip()
    session.install("twine")
    session.run("uv", "build", external=True)
    dists = [*dist_dir.glob("*.whl"), *dist_dir.glob("*.tar.gz")]
    session.run("twine", "check", *(str(dist) for dist in dists))

    for dist in dists:
        venv = Path(tempfile.mkdtemp(), "venv")
        session.run("uv", "venv", str(venv), external=True)
        python = venv / "bin" / "python"
        session.run(
            "uv", "pip", "install", "--python", str(python), str(dist), external=True
        )
        session.run(str(venv / "bin" / "pybuild-deps"), "--help", external=True)
        check = (
            "import importlib.metadata as m; "
            f"assert m.version('pybuild-deps') == {version!r}, "
            "m.version('pybuild-deps')"
        )
        session.run(str(python), "-c", check, external=True)


@nox.session(name="e2e-tests", python=python_versions[0])
def e2e_tests(session: Session) -> None:
    """Run e2e tests that require network access (single Python version, parallel)."""
    session.install(".")
    session.install(*test_requirements)
    session.run("pytest", "-m", "e2e", "-n", "auto", *session.posargs)


@nox.session(name="docs-build", python=python_versions[0])
def docs_build(session: Session) -> None:
    """Build the documentation."""
    args = session.posargs or ["docs", "docs/_build"]
    if not session.posargs and "FORCE_COLOR" in os.environ:
        args.insert(0, "--color")

    session.install(".")
    session.install("sphinx", "sphinx-click", "furo", "myst-parser")

    build_dir = Path("docs", "_build")
    if build_dir.exists():
        shutil.rmtree(build_dir)

    session.run("sphinx-build", *args)


@nox.session(python=python_versions[0])
def docs(session: Session) -> None:
    """Build and serve the documentation with live reloading on file changes."""
    args = session.posargs or ["--open-browser", "docs", "docs/_build"]
    session.install(".")
    session.install("sphinx", "sphinx-autobuild", "sphinx-click", "furo", "myst-parser")

    build_dir = Path("docs", "_build")
    if build_dir.exists():
        shutil.rmtree(build_dir)

    session.run("sphinx-autobuild", *args)
