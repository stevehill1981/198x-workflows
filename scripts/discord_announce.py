#!/usr/bin/env python3
"""Announce 198x releases in Discord.

Each release goes to two places:

- **The project channel** (DISCORD_RELEASE_WEBHOOK) gets the full release
  notes, without cargo-dist's install and download sections.
- **The family channel** (DISCORD_RELEASE_WEBHOOK_ALL) gets one line per
  release: its name, a count of changes, and a link straight to the full post in
  the project channel. If there is no project post to link to, the line links to
  the release on GitHub instead.

The webhooks come from the WEBHOOK and WEBHOOK_ALL environment variables, never
from arguments, so they cannot leak into a process list or an echoed command.
Either may be missing. If both name the same channel, it gets the full
post only, never the digest as well.

Two sources of releases:

- `release-plz`: release-plz's `releases` output. The notes come from each
  crate's CHANGELOG.md, which the release PR has already committed to main.
- `github-release`: one GitHub Release, by tag. Used after cargo-dist publishes
  binaries, where the release body holds the notes followed by install tables.

A failed post never stops the others. The script exits non-zero if any post
failed, so the step shows red, but a release that has already shipped is never
undone by a notification.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

USERNAME = "198x releases"
# Discord's embed description limit is 4096; leave room for the links line.
NOTES_LIMIT = 3600
# Discord's message content limit.
CONTENT_LIMIT = 2000
GREEN = 3066993
AMBER = 16215907
USER_AGENT = "198x-ci (https://github.com/stevehill1981/198x-workflows)"


@dataclass
class Announcement:
    title: str
    url: str
    notes: str
    repo: str
    links: list[str] = field(default_factory=list)
    prerelease: bool = False


# --- Notes -----------------------------------------------------------------

# cargo-dist appends install instructions and download tables after the notes:
# "## Install …", "## Download …", and for multi-binary workspaces a top-level
# "# <package> <version>" heading per binary.
_DIST_SECTION = re.compile(r"^(#\s+\S|##\s+(Install|Download)\b)", re.MULTILINE)
_LEADING_HEADING = re.compile(r"\A\s*##\s+Release Notes\s*\n")


def release_notes(body: str) -> str:
    """Returns the notes part of a GitHub Release body."""
    body = _LEADING_HEADING.sub("", body or "")
    cut = _DIST_SECTION.search(body)
    if cut:
        body = body[: cut.start()]
    return body.strip()


def crate_changelog(crate_dir: Path, package: str) -> Path:
    """Returns the CHANGELOG.md of the crate named `package` under `crate_dir`.

    A crate's folder is usually named after its package, but not always:
    lang198x-syntax lives in `crates/syntax`. So when no folder has the
    package's name, this finds the crate whose Cargo.toml declares it.
    """
    named = crate_dir / package
    if named.is_dir():
        return named / "CHANGELOG.md"
    for manifest in sorted(crate_dir.glob("*/Cargo.toml")):
        try:
            name = tomllib.loads(manifest.read_text()).get("package", {}).get("name")
        except (OSError, tomllib.TOMLDecodeError):
            continue
        if name == package:
            return manifest.parent / "CHANGELOG.md"
    return named / "CHANGELOG.md"


def changelog_section(path: Path, version: str) -> str:
    """Returns a version's section of a Keep a Changelog file."""
    if not path.exists():
        return ""
    text = path.read_text()
    # Matches "## [0.1.3](compare-url) - 2026-08-27", "## [0.1.3] - date" and a
    # bare "## 0.1.3". The lookahead stops 0.1.1 matching 0.1.10's heading.
    heading = re.compile(
        rf"^##\s+\[?{re.escape(version)}\]?(?![0-9.])[^\n]*$", re.MULTILINE
    )
    match = heading.search(text)
    if not match:
        return ""
    rest = text[match.end():]
    following = re.search(r"^##\s+", rest, re.MULTILINE)
    return (rest[: following.start()] if following else rest).strip()


def change_counts(notes: str) -> str:
    """Summarises notes as counts per section, such as "6 fixed, 1 added"."""
    counts: dict[str, int] = {}
    section = None
    for line in notes.splitlines():
        heading = re.match(r"^###\s+(.+?)\s*$", line)
        if heading:
            section = heading.group(1).lower()
            continue
        if section and re.match(r"^[-*]\s+\S", line):
            counts[section] = counts.get(section, 0) + 1
    return ", ".join(f"{n} {name}" for name, n in counts.items())


def truncate(notes: str, url: str) -> str:
    if len(notes) <= NOTES_LIMIT:
        return notes
    return notes[:NOTES_LIMIT].rstrip() + f"\n\n…truncated. [Full notes]({url})"


# --- Payloads --------------------------------------------------------------


def full_payload(item: Announcement) -> dict:
    notes = truncate(item.notes, item.url) if item.notes else (
        "_No release notes recorded for this version._"
    )
    if item.links:
        notes = f"{notes}\n\n{' · '.join(item.links)}"
    return {
        "username": USERNAME,
        "embeds": [
            {
                "title": item.title,
                "url": item.url,
                "description": notes,
                "color": AMBER if item.prerelease else GREEN,
                "footer": {"text": item.repo},
            }
        ],
        "allowed_mentions": {"parse": []},
    }


def digest_line(item: Announcement, jump: str | None) -> str:
    parts = [f"**[{item.title}](<{item.url}>)**"]
    counts = change_counts(item.notes)
    if counts:
        parts.append(counts)
    if item.prerelease:
        parts.append("prerelease")
    parts.append(f"[full notes](<{jump}>)" if jump else f"[release](<{item.url}>)")
    return " · ".join(parts)


def digest_payloads(lines: list[str]) -> list[dict]:
    """Packs digest lines into as few messages as Discord's limit allows."""
    messages: list[str] = []
    current = ""
    for line in lines:
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > CONTENT_LIMIT and current:
            messages.append(current)
            current = line
        else:
            current = candidate
    if current:
        messages.append(current)
    return [
        {"username": USERNAME, "content": m[:CONTENT_LIMIT], "allowed_mentions": {"parse": []}}
        for m in messages
    ]


# --- Discord ---------------------------------------------------------------

Http = Callable[[str, str, dict | None], dict | None]


def discord_http(method: str, url: str, body: dict | None) -> dict | None:
    """Sends one request to Discord, retrying rate limits and server errors."""
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(4):
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                text = response.read().decode()
                return json.loads(text) if text else None
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")
            if error.code == 429 and attempt < 3:
                try:
                    wait = float(json.loads(detail).get("retry_after", 2))
                except (ValueError, AttributeError):
                    wait = 2.0
                time.sleep(min(wait, 30))
                continue
            if error.code >= 500 and attempt < 3:
                time.sleep(5)
                continue
            raise RuntimeError(f"Discord answered {error.code}: {detail[:300]}") from None
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt < 3:
                time.sleep(5)
                continue
            raise RuntimeError(f"could not reach Discord: {error}") from None
    raise RuntimeError("Discord kept rate-limiting the request")


def _without_query(webhook: str) -> str:
    return webhook.split("?", 1)[0]


def post(http: Http, webhook: str, payload: dict, wait: bool) -> dict | None:
    base = _without_query(webhook)
    return http("POST", f"{base}?wait=true" if wait else base, payload)


def message_link(http: Http, webhook: str, message: dict | None) -> str | None:
    """Builds a link to a message a webhook just posted, or returns None."""
    if not message or not message.get("id") or not message.get("channel_id"):
        return None
    guild = message.get("guild_id")
    if not guild:
        info = http("GET", _without_query(webhook), None) or {}
        guild = info.get("guild_id")
    if not guild:
        return None
    return f"https://discord.com/channels/{guild}/{message['channel_id']}/{message['id']}"


def announce(items: list[Announcement], webhook: str, webhook_all: str, http: Http) -> int:
    """Posts every announcement. Returns the number of failed posts."""
    if webhook_all and webhook_all == webhook:
        webhook_all = ""
    if not webhook and not webhook_all:
        print("::notice::no Discord webhook secret set; nothing posted.")
        return 0

    failures = 0
    lines = []
    for item in items:
        jump = None
        if webhook:
            try:
                message = post(http, webhook, full_payload(item), wait=bool(webhook_all))
                if webhook_all:
                    jump = message_link(http, webhook, message)
                print(f"Posted {item.title} to the project channel.")
            except RuntimeError as error:
                failures += 1
                print(f"::error::project post for {item.title} failed: {error}")
        lines.append(digest_line(item, jump))

    if webhook_all:
        for payload in digest_payloads(lines):
            try:
                post(http, webhook_all, payload, wait=False)
                print("Posted the digest to the family channel.")
            except RuntimeError as error:
                failures += 1
                print(f"::error::family digest failed: {error}")
    return failures


# --- Sources ---------------------------------------------------------------


def on_crates_io(package: str, version: str) -> bool:
    request = urllib.request.Request(
        f"https://crates.io/api/v1/crates/{package}/{version}",
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return False


def from_release_plz(
    releases: list[dict],
    repo: str,
    server_url: str,
    crate_dir: Path,
    skip: set[str],
    published: Callable[[str, str], bool] = on_crates_io,
) -> list[Announcement]:
    items = []
    for release in releases:
        package = release.get("package_name")
        version = release.get("version")
        if not package or not version:
            continue
        if package in skip:
            print(f"{package} {version} is announced by its binary release; skipping.")
            continue
        on_registry = published(package, version)
        tag = release.get("tag") or ""
        if tag:
            url = f"{server_url}/{repo}/releases/tag/{tag}"
        elif on_registry:
            url = f"https://crates.io/crates/{package}/{version}"
        else:
            url = f"{server_url}/{repo}"
        notes = changelog_section(crate_changelog(crate_dir, package), version)
        if not notes:
            print(f"::notice::no changelog section for {package} {version}")
        links = []
        if tag:
            links.append(f"[release notes]({url})")
        if on_registry:
            links.append(f"[crates.io](https://crates.io/crates/{package}/{version})")
            links.append(f"[docs.rs](https://docs.rs/{package}/{version})")
        items.append(Announcement(f"{package} v{version}", url, notes, repo, links))
    return items


def release_title(name: str, tag: str, repo: str) -> str:
    """Names the project in a release title, which cargo-dist leaves out.

    cargo-dist names a release "0.44.1 - 2026-10-22". That reads fine on the
    project's own release page, but not in a channel shared by every project.
    """
    project = repo.split("/")[-1]
    title = name or tag
    if project.lower() in title.lower():
        return title
    return f"{project} {title}"


def from_github_release(tag: str, repo: str, server_url: str) -> list[Announcement]:
    result = subprocess.run(
        ["gh", "release", "view", tag, "--repo", repo, "--json", "name,body,isPrerelease"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"::warning::could not read release {tag}: {result.stderr.strip()}")
        return []
    release = json.loads(result.stdout)
    url = f"{server_url}/{repo}/releases/tag/{tag}"
    return [
        Announcement(
            title=release_title(release.get("name") or "", tag, repo),
            url=url,
            notes=release_notes(release.get("body") or ""),
            repo=repo,
            links=[f"[download and install]({url})"],
            prerelease=bool(release.get("isPrerelease")),
        )
    ]


# --- Command line ----------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--server-url", default="https://github.com")
    parser.add_argument(
        "--dry-run", action="store_true", help="print the payloads instead of posting"
    )
    sources = parser.add_subparsers(dest="source", required=True)
    plz = sources.add_parser("release-plz")
    plz.add_argument("--releases", required=True, help="release-plz `releases` JSON")
    plz.add_argument("--crate-dir", default="crates")
    plz.add_argument(
        "--skip", default="", help="space- or comma-separated packages announced elsewhere"
    )
    gh = sources.add_parser("github-release")
    gh.add_argument("--tag", required=True)
    args = parser.parse_args(argv)

    if args.source == "release-plz":
        skip = set(re.split(r"[\s,]+", args.skip.strip())) - {""}
        items = from_release_plz(
            json.loads(args.releases), args.repo, args.server_url, Path(args.crate_dir), skip
        )
    else:
        items = from_github_release(args.tag, args.repo, args.server_url)

    if not items:
        print("Nothing to announce.")
        return 0

    webhook = os.environ.get("WEBHOOK", "")
    webhook_all = os.environ.get("WEBHOOK_ALL", "")

    if args.dry_run:
        def http(method: str, url: str, body: dict | None) -> dict | None:
            channel = "project" if webhook and url.startswith(_without_query(webhook)) else "family"
            print(f"{method} to the {channel} channel")
            if body is not None:
                print(json.dumps(body, indent=2))
            return {"id": "MESSAGE", "channel_id": "CHANNEL", "guild_id": "SERVER"}
    else:
        http = discord_http

    failures = announce(items, webhook, webhook_all, http)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
