#!/usr/bin/env python3
"""Create or refresh a QQ (OneBot v11) platform entry in AstrBot's config.

AstrBot hosts a reverse WebSocket server; the QQ protocol endpoint (NapCat,
LLOneBot and similar) connects to it. Running this script once means the
platform is already present in the dashboard when AstrBot starts, so no manual
form filling is needed.

Usage:
    uv run python scripts/personal/make_qq_config.py
    uv run python scripts/personal/make_qq_config.py --port 6199 --show
"""

from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path

from astrbot.core.utils.webhook_utils import ensure_platform_webhook_config

PLATFORM_TYPE = "aiocqhttp"


def find_config(explicit: str | None) -> Path:
    """Locate ``data/cmd_config.json``.

    Args:
        explicit: Path given on the command line, if any.

    Returns:
        Path to the config file.

    Raises:
        SystemExit: If no AstrBot config exists yet (start AstrBot once first).
    """
    if explicit:
        return Path(explicit)
    root = Path(__file__).resolve().parents[2]
    candidate = root / "data" / "cmd_config.json"
    if not candidate.exists():
        raise SystemExit(
            f"{candidate} not found. Start AstrBot once (start.bat) so the "
            "config is created, then run this script again."
        )
    return candidate


def describe(config: dict, platform: dict) -> None:
    """Print the values the QQ protocol endpoint must be pointed at."""
    host = platform.get("ws_reverse_host") or "127.0.0.1"
    port = platform.get("ws_reverse_port")
    token = platform.get("ws_reverse_token") or ""
    shown_host = "127.0.0.1" if host in ("0.0.0.0", "", "::") else host
    print("\n在 NapCat / LLOneBot 的网络设置里填：")
    print("  类型      : 反向 WebSocket (WS Client)")
    print(f"  连接地址  : ws://{shown_host}:{port}/ws")
    print(f"  Access Token : {token or '（未设置）'}")
    print(f"\n平台 ID    : {platform.get('id')}")
    print(f"配置文件   : {config.get('__path__')}")
    print("重启 AstrBot 后生效；网页端「机器人」页面可以看到这条平台。")


def main() -> int:
    """Entry point.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="Path to cmd_config.json")
    parser.add_argument("--id", default="qq_onebot", help="Platform id to upsert")
    parser.add_argument("--name", default="QQ (OneBot v11)", help="Display name")
    parser.add_argument("--host", default="0.0.0.0", help="Reverse WS listen host")
    parser.add_argument("--port", type=int, default=6199, help="Reverse WS listen port")
    parser.add_argument(
        "--token", default="", help="Reverse WS token, empty = generate"
    )
    parser.add_argument("--disable", action="store_true", help="Add it disabled")
    parser.add_argument(
        "--show", action="store_true", help="Only print current settings"
    )
    args = parser.parse_args()

    path = find_config(args.config)
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    # AstrBot stores bot entries under the singular "platform" key.
    platforms = raw.get("platform")
    if not isinstance(platforms, list):
        platforms = []

    existing = next(
        (item for item in platforms if item.get("id") == args.id),
        None,
    )
    if args.show:
        if existing is None:
            print(f"平台 {args.id} 尚未配置，先运行本脚本（不带 --show）。")
            return 1
        raw["__path__"] = str(path)
        describe(raw, existing)
        return 0

    token = (
        args.token or (existing or {}).get("ws_reverse_token") or secrets.token_hex(16)
    )
    entry = {
        "id": args.id,
        "type": PLATFORM_TYPE,
        "name": args.name,
        "enable": not args.disable,
        "ws_reverse_host": args.host,
        "ws_reverse_port": args.port,
        "ws_reverse_token": token,
    }
    ensure_platform_webhook_config(entry)
    if existing is None:
        platforms.append(entry)
    else:
        platforms[platforms.index(existing)] = {**existing, **entry}
    raw["platform"] = platforms
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=4), encoding="utf-8-sig")
    print(f"已写入平台配置：{args.id} ({PLATFORM_TYPE}) -> {path}")
    raw["__path__"] = str(path)
    describe(raw, entry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
