#!/usr/bin/env python3
"""Keep a repository's rust-toolchain.toml on the latest stable Rust.

Reads the channel pinned in rust-toolchain.toml and the latest stable version
from Rust's release manifest. If the pin is an older version number, rewrites
only its `channel` line and prints the new version for the workflow to open a
pull request with. Prints nothing if the pin is current, newer, or not a
plain version (such as "stable" or a nightly), because those are deliberate.

Dependabot does not update rust-toolchain.toml, which is why the family's pins
drifted three releases apart before this existed.
"""

from __future__ import annotations

import re
import sys
import tomllib
import urllib.request
from pathlib import Path

MANIFEST = "https://static.rust-lang.org/dist/channel-rust-stable.toml"
_CHANNEL = re.compile(r'^(\s*channel\s*=\s*")([^"]+)(")', re.MULTILINE)
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")


def latest_stable(manifest: str) -> str:
    """Returns the stable version, such as "1.99.1", from Rust's manifest."""
    full = tomllib.loads(manifest)["pkg"]["rust"]["version"]
    return full.split()[0]


def pinned(toolchain: str) -> str | None:
    match = _CHANNEL.search(toolchain)
    return match.group(2) if match else None


def as_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def needs_bump(pin: str | None, latest: str) -> bool:
    if not pin or not _VERSION.match(pin) or not _VERSION.match(latest):
        return False
    return as_tuple(pin) < as_tuple(latest)


def bumped(toolchain: str, latest: str) -> str:
    """Returns the file with only the channel's version changed."""
    return _CHANNEL.sub(lambda m: f"{m.group(1)}{latest}{m.group(3)}", toolchain, count=1)


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "rust-toolchain.toml")
    if not path.exists():
        print(f"::notice::no {path}; nothing to keep current.", file=sys.stderr)
        return 0
    toolchain = path.read_text()
    request = urllib.request.Request(MANIFEST, headers={"User-Agent": "198x-ci"})
    with urllib.request.urlopen(request, timeout=60) as response:
        latest = latest_stable(response.read().decode())
    pin = pinned(toolchain)
    if not needs_bump(pin, latest):
        print(f"::notice::Rust pin {pin} needs no change (latest stable {latest}).", file=sys.stderr)
        return 0
    path.write_text(bumped(toolchain, latest))
    print(latest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
