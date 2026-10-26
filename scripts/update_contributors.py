#!/usr/bin/env python3
"""Update the contributors section in README.md from the GitHub API.

The workflow in ``.github/workflows/contributors.yml`` runs this script on
pushes to ``main`` (and manually). It is intentionally dependency-free so the
job does not need to install the project's requirements.

Usage::

    GITHUB_TOKEN=... GITHUB_REPOSITORY=owner/repo python scripts/update_contributors.py

Only human contributors are listed; bots such as ``dependabot[bot]`` and
``github-actions[bot]`` are skipped.
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
START_MARKER = "<!-- readme: contributors -start -->"
END_MARKER = "<!-- readme: contributors -end -->"
API_ROOT = "https://api.github.com"
REPOSITORY = os.getenv("GITHUB_REPOSITORY", "Wilooper/Lyrica")
TOKEN = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or ""
COLUMNS_PER_ROW = 6
IMAGE_SIZE = 100


def _api_get(path: str):
    """Fetch a GitHub API resource, returning decoded JSON."""
    url = path if path.startswith("https://") else f"{API_ROOT}{path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Lyrica-Contributors-Bot",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def _fetch_contributors() -> list[dict]:
    """Return all contributors, following pagination."""
    contributors: list[dict] = []
    page = 1
    while True:
        # GitHub may return 202 while the contributor statistics are being
        # computed. Retry briefly instead of failing the workflow.
        for attempt in range(3):
            try:
                batch = _api_get(
                    f"/repos/{REPOSITORY}/contributors?per_page=100&page={page}"
                )
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 202 and attempt < 2:
                    time.sleep(3)
                    continue
                raise
        else:  # pragma: no cover - defensive
            return contributors

        if not batch:
            break
        contributors.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    return [
        contributor
        for contributor in contributors
        if contributor.get("type") != "Bot"
        and not str(contributor.get("login", "")).endswith("[bot]")
    ]


def _display_name(login: str, cache: dict[str, str]) -> str:
    """Resolve a contributor's display name, falling back to their login."""
    if login in cache:
        return cache[login]
    try:
        profile = _api_get(f"/users/{login}")
        name = profile.get("name") or login
    except Exception:
        name = login
    cache[login] = name
    return name


def _render_table(contributors: list[dict]) -> str:
    if not contributors:
        return "<p>No contributors yet — be the first!</p>"

    names: dict[str, str] = {}
    resolved: list[tuple[str, str, str]] = []
    for contributor in contributors:
        login = str(contributor.get("login", "")).strip()
        if not login:
            continue
        name = str(_display_name(login, names)).strip() or login
        avatar = str(contributor.get("avatar_url", ""))
        resolved.append((login, name, avatar))

    # Some GitHub accounts share the same display name. Add the login in
    # parentheses so readers can tell them apart.
    name_counts: dict[str, int] = {}
    for _, name, _ in resolved:
        key = name.casefold()
        name_counts[key] = name_counts.get(key, 0) + 1

    cells: list[str] = []
    for login, name, avatar in resolved:
        display_name = name
        if name_counts[name.casefold()] > 1 and name.casefold() != login.casefold():
            display_name = f"{name} (@{login})"
        safe_login = html.escape(login, quote=True)
        safe_name = html.escape(display_name, quote=True)
        safe_avatar = html.escape(avatar, quote=True)
        cells.append(
            f"""            <td align="center">
                <a href="https://github.com/{safe_login}">
                    <img src="{safe_avatar}" width="{IMAGE_SIZE};" alt="{safe_login}"/>
                    <br />
                    <sub><b>{safe_name}</b></sub>
                </a>
            </td>"""
        )

    rows: list[str] = []
    for index in range(0, len(cells), COLUMNS_PER_ROW):
        rows.append(
            "        <tr>\n"
            + "\n".join(cells[index:index + COLUMNS_PER_ROW])
            + "\n        </tr>"
        )

    return "<table>\n    <tbody>\n" + "\n".join(rows) + "\n    </tbody>\n</table>"


def _replace_section(readme: str, table: str) -> str:
    """Replace the content between the markers, or create the section."""
    pattern = re.compile(
        re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER),
        re.DOTALL,
    )
    block = f"{START_MARKER}\n{table}\n{END_MARKER}"

    if pattern.search(readme):
        return pattern.sub(block, readme, count=1)

    section = f"## 👥 Contributors\n\n{block}\n\n"
    license_heading = "## 📝 License"
    if license_heading in readme:
        return readme.replace(license_heading, section + license_heading, 1)
    return readme.rstrip() + "\n\n" + section


def main() -> int:
    if not README.exists():
        print(f"README not found: {README}", file=sys.stderr)
        return 1

    try:
        contributors = _fetch_contributors()
    except Exception as exc:
        print(f"Unable to fetch contributors from GitHub: {exc}", file=sys.stderr)
        return 1

    contributors.sort(
        key=lambda item: (
            -int(item.get("contributions", 0)),
            str(item.get("login", "")).lower(),
        )
    )

    original = README.read_text(encoding="utf-8")
    updated = _replace_section(original, _render_table(contributors))

    if updated == original:
        print(f"README.md is already up to date ({len(contributors)} contributors).")
        return 0

    README.write_text(updated, encoding="utf-8")
    print(f"Updated README.md with {len(contributors)} contributors.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
