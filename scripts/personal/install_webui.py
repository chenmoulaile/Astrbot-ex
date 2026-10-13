#!/usr/bin/env python3
"""Install a locally built dashboard where the core will actually serve it.

Two details make this script necessary:

1. The core resolves ``<data>/dist`` before the bundled ``astrbot/dashboard/dist``,
   and it downloads an official WebUI into ``<data>/dist`` on first start. A
   locally built dashboard therefore has to replace that directory, not just the
   package one, or the roleplay pages stay invisible.
2. The official release zip ships ``assets/version``; a plain ``pnpm build``
   does not, and a dist without a matching version marker is refused.

Usage:
    uv run python scripts/personal/install_webui.py
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE = "RPPage"


def _install(source: Path, target: Path, version: str) -> int:
    """Replace ``target`` with the built dashboard and stamp its version.

    Args:
        source: Directory produced by ``pnpm build``.
        target: Directory the core serves.
        version: Core version to write into ``assets/version``.

    Returns:
        Number of installed files.
    """
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    assets = target / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "version").write_text(f"v{version}", encoding="utf-8")
    return len(list(target.rglob("*")))


def main() -> int:
    """Copy the dashboard build into both served locations.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default=str(ROOT / "dashboard" / "dist"),
        help="Built dashboard directory",
    )
    parser.add_argument(
        "--skip-managed",
        action="store_true",
        help="Do not touch data/dist (the location the core prefers)",
    )
    args = parser.parse_args()

    source = Path(args.source)
    if not (source / "index.html").exists():
        print(f"[!] {source} has no index.html. Run `pnpm build` in dashboard/ first.")
        return 1
    if not any(PROBE in path.name for path in (source / "assets").glob("*.js")):
        print(
            f"[!] {source} does not contain a {PROBE} chunk: this build is "
            "outdated or was made from a tree without the roleplay pages."
        )
        return 1

    sys.path.insert(0, str(ROOT))
    from astrbot import __version__  # local import: needs the repo on sys.path

    targets = []
    if not args.skip_managed:
        targets.append(ROOT / "data" / "dist")
    targets.append(ROOT / "astrbot" / "dashboard" / "dist")

    for target in targets:
        count = _install(source, target, __version__)
        print(f"installed {count} files -> {target} (v{__version__})")
    print("重启 AstrBot 后，网页端侧边栏会出现「角色扮演」。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
