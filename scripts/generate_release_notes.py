#!/usr/bin/env python3
"""Generate release metadata and notes for a manual GitHub release.

The workflow in ``.github/workflows/release.yml`` runs this script from
``workflow_dispatch`` only. It finds the latest published release, collects
the commits since that release, groups the meaningful ones, and writes notes
that include the Docker image tags for the release.

Usage::

    python scripts/generate_release_notes.py \
        --notes-file /tmp/release-notes.md \
        --tag v1.5.0

If ``--tag`` is omitted, the next version is derived from the higher
of the highest ``vX.Y.Z`` tag reachable from ``HEAD`` and the version in
``pyproject.toml``. An explicit ``--base`` overrides the latest-release lookup.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPOSITORY = "Wilooper/Lyrica"
SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
DOCKER_TAG_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
CONVENTIONAL_RE = re.compile(
    r"^(?P<type>[A-Za-z]+)(?:\((?P<scope>[^)]+)\))?!?:\s*(?P<subject>.+)$"
)
GENERATED_SUBJECTS = (
    re.compile(r"^docs(?:\([^)]+\))?:\s*update auto-generated openapi\.json\b", re.I),
    re.compile(r"^docs(?:\(contributors\))?:\s*update contributors?\b", re.I),
    re.compile(r"^chore\(release\):", re.I),
    re.compile(r"^merge\s", re.I),
)

CATEGORY_ORDER = (
    "features",
    "fixes",
    "performance",
    "security",
    "dependencies",
    "documentation",
    "maintenance",
    "other",
)
CATEGORY_TITLES = {
    "features": "✨ Features",
    "fixes": "🐛 Fixes",
    "performance": "⚡ Performance",
    "security": "🔒 Security",
    "dependencies": "📦 Dependencies",
    "documentation": "📚 Documentation",
    "maintenance": "🔧 Maintenance",
    "other": "📝 Other Changes",
}


@dataclass(frozen=True)
class Commit:
    sha: str
    short_sha: str
    author: str
    subject: str


def _run(*args: str) -> str:
    result = subprocess.run(
        args,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _github_request(path: str, token: str) -> object:
    url = path if path.startswith("https://") else f"https://api.github.com{path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Lyrica-Release-Bot",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def _latest_release_tag(repository: str, token: str) -> str | None:
    try:
        releases = _github_request(
            f"/repos/{repository}/releases?per_page=100",
            token,
        )
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"GitHub API returned HTTP {exc.code} while finding the last release"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Unable to reach the GitHub API: {exc.reason}") from exc

    if not isinstance(releases, list):
        raise RuntimeError("Unexpected response while finding the last release")

    for release in releases:
        if isinstance(release, dict) and not release.get("draft"):
            tag = release.get("tag_name")
            if tag:
                return str(tag)
    return None


def _tag_exists(tag: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"refs/tags/{tag}"],
        cwd=ROOT,
        capture_output=True,
    )
    return result.returncode == 0


def _valid_tag(tag: str) -> bool:
    result = subprocess.run(
        ["git", "check-ref-format", f"refs/tags/{tag}"],
        cwd=ROOT,
        capture_output=True,
    )
    return result.returncode == 0


def _pyproject_version() -> str:
    try:
        import tomllib
    except ImportError:  # pragma: no cover - Python < 3.11
        return "0.0.0"

    with (ROOT / "pyproject.toml").open("rb") as handle:
        data = tomllib.load(handle)
    return str(data.get("project", {}).get("version", "0.0.0"))


def _semver_tags() -> list[tuple[tuple[int, int, int], str]]:
    tags = _run("git", "tag", "--merged", "HEAD", "--list", "v[0-9]*").splitlines()
    parsed: list[tuple[tuple[int, int, int], str]] = []
    for tag in tags:
        match = SEMVER_RE.match(tag)
        if match:
            parsed.append(
                (
                    (int(match.group(1)), int(match.group(2)), int(match.group(3))),
                    tag,
                )
            )
    return parsed


def _parse_version(value: str) -> tuple[int, int, int] | None:
    match = SEMVER_RE.match(value.strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _resolve_tag(requested: str) -> str:
    tag = requested.strip()
    if tag:
        if not _valid_tag(tag):
            raise RuntimeError(f"Invalid git tag: {tag!r}")
        if not DOCKER_TAG_RE.match(tag):
            raise RuntimeError(
                f"Tag {tag!r} is not a valid Docker tag. "
                "Use letters, numbers, dots, underscores, or hyphens."
            )
        if _tag_exists(tag):
            raise RuntimeError(
                f"Tag {tag!r} already exists. Choose a new tag or delete the old one."
            )
        return tag

    semantic_tags = _semver_tags()
    latest_tag = max(semantic_tags, key=lambda item: item[0]) if semantic_tags else None
    project_version = _parse_version(_pyproject_version())

    if latest_tag is None:
        candidate = project_version or (0, 0, 0)
    elif project_version is not None and project_version > latest_tag[0]:
        candidate = project_version
    else:
        major, minor, patch = latest_tag[0]
        candidate = (major, minor, patch + 1)

    tag = "v{}.{}.{}".format(*candidate)
    while _tag_exists(tag):
        major, minor, patch = candidate
        candidate = (major, minor, patch + 1)
        tag = "v{}.{}.{}".format(*candidate)

    if not _valid_tag(tag) or not DOCKER_TAG_RE.match(tag):
        raise RuntimeError(f"Unable to derive a valid tag: {tag!r}")
    return tag


def _is_generated(subject: str) -> bool:
    return any(pattern.search(subject) for pattern in GENERATED_SUBJECTS)


def _commits(base: str | None, head: str) -> list[Commit]:
    revision = f"{base}..{head}" if base else head
    output = _run(
        "git",
        "log",
        "--no-merges",
        "--pretty=format:%H%x1f%h%x1f%an%x1f%s",
        revision,
    )
    commits: list[Commit] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        sha, short_sha, author, subject = line.split("\x1f", 3)
        if not subject.strip() or _is_generated(subject):
            continue
        commits.append(Commit(sha, short_sha, author, subject.strip()))
    return commits


def _classify(subject: str) -> str:
    match = CONVENTIONAL_RE.match(subject)
    if match:
        kind = match.group("type").lower()
        if kind in {"feat", "feature"}:
            return "features"
        if kind in {"fix", "bugfix", "hotfix"}:
            return "fixes"
        if kind == "perf":
            return "performance"
        if kind in {"security", "sec"}:
            return "security"
        if kind in {"build", "deps", "dependencies"}:
            return "dependencies"
        if kind in {"docs", "doc"}:
            return "documentation"
        if kind in {"refactor", "style", "test", "tests", "ci", "chore"}:
            return "maintenance"
        return "other"

    lowered = subject.lower()
    if lowered.startswith(("fix", "fixed", "bug", "hotfix", "resolve", "repair")):
        return "fixes"
    if lowered.startswith(("add", "added", "feat", "feature", "implement", "support")):
        return "features"
    if any(word in lowered for word in ("performance", "optimi", "speed", "faster")):
        return "performance"
    if any(word in lowered for word in ("security", "vulnerab", "cve-")):
        return "security"
    if lowered.startswith(("bump", "deps", "dependency", "update depend")):
        return "dependencies"
    if lowered.startswith(("doc", "readme")):
        return "documentation"
    return "other"


def _clean_subject(subject: str) -> str:
    subject = re.sub(r"\s*\[skip ci\]\s*$", "", subject, flags=re.I).strip()
    match = CONVENTIONAL_RE.match(subject)
    if match:
        subject = match.group("subject").strip()
    if subject:
        subject = subject[0].upper() + subject[1:]
    return subject


def _group_commits(repository: str, commits: list[Commit]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {category: [] for category in CATEGORY_ORDER}
    seen: set[str] = set()
    for commit in commits:
        subject = _clean_subject(commit.subject)
        key = subject.casefold()
        if not subject or key in seen:
            continue
        seen.add(key)
        commit_url = f"https://github.com/{repository}/commit/{commit.sha}"
        link = f"[`{commit.short_sha}`]({commit_url})"
        grouped[_classify(commit.subject)].append(f"{subject} ({link})")
    return {category: items for category, items in grouped.items() if items}


def repository_from_env() -> str:
    return os.getenv("GITHUB_REPOSITORY", DEFAULT_REPOSITORY)


def _image_name(repository: str) -> str:
    return f"ghcr.io/{repository.lower()}"


def _package_url(repository: str) -> str:
    package = repository.split("/")[-1].lower()
    return f"https://github.com/{repository}/pkgs/container/{package}"


def _render_notes(
    *,
    repository: str,
    base: str | None,
    tag: str,
    prerelease: bool,
    commits: list[Commit],
) -> str:
    grouped = _group_commits(repository, commits)
    total = sum(len(items) for items in grouped.values())
    image = _image_name(repository)

    lines = ["## What's Changed", ""]
    if base:
        lines.append(
            f"This release contains **{total}** change{'s' if total != 1 else ''} "
            f"since [`{base}`](https://github.com/{repository}/compare/{base}...{tag})."
        )
    else:
        lines.append(
            f"This release contains **{total}** change{'s' if total != 1 else ''}."
        )
    lines.append("")

    for category in CATEGORY_ORDER:
        items = grouped.get(category, [])
        if not items:
            continue
        lines.extend((f"### {CATEGORY_TITLES[category]}", ""))
        lines.extend(f"- {item}" for item in items)
        lines.append("")

    lines.extend(("## 🐳 Docker Image", "", "```bash"))
    lines.append(f"docker pull {image}:{tag}")
    if not prerelease:
        lines.append(f"docker pull {image}:latest")
    lines.extend(
        (
            "```",
            "",
            "Multi-architecture image for `linux/amd64` and `linux/arm64`:",
            f"[GitHub Container Registry]({_package_url(repository)})",
            "",
            "## 📜 Full Changelog",
            "",
        )
    )
    if base:
        lines.append(f"https://github.com/{repository}/compare/{base}...{tag}")
    else:
        lines.append(f"https://github.com/{repository}/commits/{tag}")
    return "\n".join(lines).rstrip() + "\n"


def _write_outputs(values: dict[str, str]) -> None:
    output_path = os.getenv("GITHUB_OUTPUT")
    if not output_path:
        for key, value in values.items():
            print(f"{key}={value}")
        return
    with open(output_path, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="", help="Release tag. Empty = next patch.")
    parser.add_argument("--title", default="", help="Release title. Empty = tag.")
    parser.add_argument("--base", default="", help="Previous release tag or commit.")
    parser.add_argument("--head", default="HEAD", help="Commit to release.")
    parser.add_argument(
        "--prerelease",
        action="store_true",
        help="Do not update the Docker :latest tag.",
    )
    parser.add_argument("--notes-file", required=True, help="Write notes here.")
    parser.add_argument(
        "--repo",
        default=repository_from_env(),
        help="GitHub repository (owner/name).",
    )
    args = parser.parse_args()

    repository = args.repo.strip()
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or ""

    try:
        base = args.base.strip() or _latest_release_tag(repository, token)
        tag = _resolve_tag(args.tag)
        title = args.title.strip() or tag
        if "\n" in title or "\r" in title:
            raise RuntimeError("Release title must be a single line")
        commits = _commits(base, args.head)
    except (RuntimeError, urllib.error.URLError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not commits:
        print(
            "error: no release-worthy commits found in the selected range",
            file=sys.stderr,
        )
        return 1

    notes = _render_notes(
        repository=repository,
        base=base,
        tag=tag,
        prerelease=args.prerelease,
        commits=commits,
    )
    notes_path = Path(args.notes_file)
    notes_path.parent.mkdir(parents=True, exist_ok=True)
    notes_path.write_text(notes, encoding="utf-8")

    is_semver = bool(SEMVER_RE.match(tag)) and not args.prerelease
    _write_outputs(
        {
            "tag": tag,
            "title": title,
            "base": base or "",
            "image": _image_name(repository),
            "is_semver": str(is_semver).lower(),
            "prerelease": str(args.prerelease).lower(),
        }
    )
    since = base or "the beginning"
    print(f"Prepared {tag} with {len(commits)} commits since {since}.")
    print(f"Notes written to {notes_path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
