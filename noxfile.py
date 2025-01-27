# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or
# https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2023 Maxwell G <maxwell@gtmx.me>

import os

import nox

IN_CI = "GITHUB_ACTIONS" in os.environ
ALLOW_EDITABLE = os.environ.get("ALLOW_EDITABLE", str(not IN_CI)).lower() in (
    "1",
    "true",
)

# Always install latest pip version
os.environ["VIRTUALENV_DOWNLOAD"] = "1"
nox.options.sessions = "lint", "test"


def install(session: nox.Session, *args, editable=False, **kwargs):
    # nox --no-venv
    if isinstance(session.virtualenv, nox.virtualenv.PassthroughEnv):
        session.warn(f"No venv. Skipping installation of {args}")
        return
    # Don't install in editable mode in CI or if it's explicitly disabled.
    # This ensures that the wheel contains all of the correct files.
    if editable and ALLOW_EDITABLE:
        args = ("-e", *args)
    session.install(*args, "-U", **kwargs)


@nox.session(python=["3.6", "3.7", "3.8", "3.9", "3.10", "3.11"])
def test(session: nox.Session):
    install(session, ".", "pytest", "pytest-cov", "pyyaml", editable=True)
    session.run(
        "pytest",
        "--cov-branch",
        "--cov=antsibull_docs_parser",
    )


@nox.session
def lint(session: nox.Session):
    session.notify("formatters")
    session.notify("codeqa")
    session.notify("typing")


@nox.session
def formatters(session: nox.Session):
    install(session, "isort", "black")
    posargs = list(session.posargs)
    if IN_CI:
        posargs.append("--check")
    session.run("isort", *posargs, "src", "tests", "noxfile.py")
    session.run("black", *posargs, "src", "tests", "noxfile.py")


@nox.session
def codeqa(session: nox.Session):
    install(session, ".", "flake8", "pylint", "reuse", editable=True)
    session.run("flake8", "src/antsibull_docs_parser", *session.posargs)
    session.run(
        "pylint", "--rcfile", ".pylintrc.automated", "src/antsibull_docs_parser"
    )
    session.run("reuse", "lint")


@nox.session
def typing(session: nox.Session):
    install(session, ".", "mypy", "pyre-check", editable=True)
    session.run("mypy", "src/antsibull_docs_parser")
    session.run("pyre", "--source-directory", "src")


def _repl_version(session: nox.Session, new_version: str):
    with open("pyproject.toml", "r+") as fp:
        lines = tuple(fp)
        fp.seek(0)
        for line in lines:
            if line.startswith("version = "):
                line = f'version = "{new_version}"\n'
            fp.write(line)


def check_no_modifications(session: nox.Session) -> None:
    modified = session.run(
        "git",
        "status",
        "--porcelain=v1",
        "--untracked=normal",
        external=True,
        silent=True,
    )
    if modified:
        session.error(
            "There are modified or untracked files. Commit, restore, or remove them before running this"
        )


@nox.session
def bump(session: nox.Session):
    check_no_modifications(session)
    if len(session.posargs) not in (1, 2):
        session.error(
            "Must specify 1-2 positional arguments: nox -e bump -- <version> [ <release_summary_message> ]."
            "If release_summary_message has not been specified, a file changelogs/fragments/<version>.yml must exist"
        )
    version = session.posargs[0]
    fragment_file = f"changelogs/fragments/{version}.yml"
    if len(session.posargs) == 1:
        if not os.path.isfile(fragment_file):
            session.error(
                f"Either {fragment_file} must already exist, or two positional arguments must be provided."
            )
    install(session, "antsibull-changelog", "tomli ; python_version < '3.11'")
    _repl_version(session, version)
    if len(session.posargs) > 1:
        fragment = session.run(
            "python",
            "-c",
            f"import yaml ; print(yaml.dump(dict(release_summary={repr(session.posargs[1])})))",
            silent=True,
        )
        with open(fragment_file, "w") as fp:
            print(fragment, file=fp)
        session.run("git", "add", "pyproject.toml", fragment_file, external=True)
        session.run("git", "commit", "-m", f"Prepare {version}.", external=True)
    session.run("antsibull-changelog", "release")
    session.run(
        "git",
        "add",
        "CHANGELOG.rst",
        "changelogs/changelog.yaml",
        "changelogs/fragments/",
        external=True,
    )
    install(session, ".")  # Smoke test
    session.run("git", "commit", "-m", f"Release {version}.", external=True)
    session.run(
        "git",
        "tag",
        "-a",
        "-m",
        f"antsibull-docs-parser {version}",
        "--edit",
        version,
        external=True,
    )


@nox.session
def publish(session: nox.Session):
    check_no_modifications(session)
    install(session, "hatch")
    session.run("hatch", "publish", *session.posargs)
    session.run("git", "push", "--follow-tags")
    version = session.run("hatch", "version", silent=True).strip()
    _repl_version(session, f"{version}.post0")
    session.run("git", "add", "pyproject.toml")
    session.run("git", "commit", "-m", "Post-release version bump.", external=True)
