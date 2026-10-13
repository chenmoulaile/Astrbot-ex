#!/usr/bin/env python3
"""Install or update the "我会永远陪着你" companion plugin from a local E-drive cache.

Everything this script writes stays on the target drive: the git clone lives in
``vendor-cache`` next to this repository, plugin dependencies go into the target
root's ``data/site-packages``, and caches are pinned under ``.cache`` so nothing
lands on the system drive.

The plugin ships without a license file, so it is installed at runtime instead of
being vendored into this repository. See README-PERSONAL.md ("陪伴插件").

Usage:
    uv run python scripts/personal/install_companion.py                 # into this fork
    uv run python scripts/personal/install_companion.py --root "D:\\AstrbotDesktop"
    uv run python scripts/personal/install_companion.py --update        # git pull first
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PLUGIN = "astrbot_plugin_private_companion"
UPSTREAM = f"https://github.com/menglimi/{PLUGIN}.git"
DEPS = ["chinese-calendar", "lunarcalendar", "markdown-it-py"]
EXCLUDE = {".git", "tests", "__pycache__", ".github"}


def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> None:
    """Run a command, streaming output and aborting on failure.

    Args:
        cmd: argv list.
        cwd: Working directory.
        env: Extra environment variables.

    Raises:
        SystemExit: If the command exits non-zero.
    """
    merged = {**os.environ, **(env or {})}
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=merged)
    if proc.returncode != 0:
        raise SystemExit(f"[!] 命令失败：{' '.join(cmd)}")


def sync_cache(cache: Path, update: bool) -> Path:
    """Clone or refresh the plugin checkout in the local cache.

    Args:
        cache: Target cache directory.
        update: Pull the latest upstream commit when the clone already exists.

    Returns:
        Path of the usable checkout.
    """
    if (cache / ".git").is_dir():
        if update:
            print(f"更新 {cache.name} ...")
            run(
                ["git", "-C", str(cache), "pull", "--ff-only"],
                env={"GIT_TERMINAL_PROMPT": "0"},
            )
        return cache
    cache.parent.mkdir(parents=True, exist_ok=True)
    print(f"克隆 {UPSTREAM} -> {cache}")
    run(
        ["git", "clone", "--depth", "1", UPSTREAM, str(cache)],
        env={"GIT_TERMINAL_PROMPT": "0"},
    )
    return cache


def copy_plugin(source: Path, target: Path) -> int:
    """Replace the installed plugin directory with the cached checkout.

    Args:
        source: Cached plugin checkout.
        target: ``<root>/data/plugins/<plugin>``.

    Returns:
        Number of files copied.
    """
    if target.exists():
        shutil.rmtree(target)
    count = 0
    for item in source.iterdir():
        if item.name in EXCLUDE:
            continue
        dest = target / item.name
        if item.is_dir():
            shutil.copytree(
                item,
                dest,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest)
        count += 1
    (target / ".gitignore").write_text("*\n", encoding="utf-8")
    return count


def install_deps(root: Path, python_exe: Path | None) -> None:
    """Install plugin requirements into the root's own site-packages.

    Args:
        root: AstrBot root that will load the plugin.
        python_exe: Interpreter to run pip with; defaults to this script's.
    """
    site = root / "data" / "site-packages"
    site.mkdir(parents=True, exist_ok=True)
    cache = REPO / ".cache"
    (cache / "uv").mkdir(parents=True, exist_ok=True)
    (cache / "tmp").mkdir(parents=True, exist_ok=True)
    env = {
        "UV_CACHE_DIR": str(cache / "uv"),
        "PIP_CACHE_DIR": str(cache / "pip"),
        "TMPDIR": str(cache / "tmp"),
        "TMP": str(cache / "tmp"),
        "TEMP": str(cache / "tmp"),
    }
    pip = [str(python_exe) if python_exe else sys.executable, "-m", "pip"]
    probe = subprocess.run([*pip, "--version"], capture_output=True)
    if probe.returncode != 0:
        pip = ["uv", "pip", "--python", str(python_exe or sys.executable)]
    print(f"安装插件依赖 -> {site}")
    run([*pip, "install", "--target", str(site), "--upgrade", *DEPS], env=env)


def main() -> int:
    """Entry point.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=str(REPO),
        help="AstrBot 根目录（源码安装填仓库目录；桌面端填 ASTRBOT_ROOT，例如 ~/.astrbot）",
    )
    parser.add_argument(
        "--update", action="store_true", help="先 git pull 拉取最新版本"
    )
    parser.add_argument("--skip-deps", action="store_true", help="只复制插件，不装依赖")
    parser.add_argument(
        "--python",
        default=str(REPO / ".venv" / "Scripts" / "python.exe"),
        help="用于 pip 安装的 Python 解释器",
    )
    args = parser.parse_args()

    root = Path(str(args.root)).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"[!] 目录不存在：{root}")
    source = sync_cache(REPO / "vendor-cache" / PLUGIN, args.update)
    if not (source / "metadata.yaml").exists():
        raise SystemExit(f"[!] 缓存里找不到插件：{source}")

    target = root / "data" / "plugins" / PLUGIN
    entries = copy_plugin(source, target)
    print(f"已安装 {entries} 个顶层条目 -> {target}")
    if not args.skip_deps:
        install_deps(root, Path(args.python) if Path(args.python).exists() else None)

    version = ""
    for line in (target / "metadata.yaml").read_text(encoding="utf-8").splitlines():
        if line.startswith("version:"):
            version = line.split(":", 1)[1].strip()
    print(
        f"\n完成：我会永远陪着你 {version or '(版本未知)'} 已装入 {root}\n"
        "重启 AstrBot 后生效；桌面端需要把 ASTRBOT_ROOT 指向同一个目录。\n"
        "首次使用请在面板「插件配置 → 我会永远陪着你」里设置角色身份与目标用户，"
        "私聊发送「陪伴 状态」可自检。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
