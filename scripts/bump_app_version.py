#!/usr/bin/env python3
"""APP_VERSIONだけを更新する。引数なしでpatch +1、引数ありでvX.Y.Zを指定。"""

import argparse
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
DEFINITION_RE = re.compile(r"\b(?:const|let|var)\s+APP_VERSION\b")
ASSIGNMENT_RE = re.compile(r"\bAPP_VERSION\s*=(?!=)")
CONSTANT_RE = re.compile(
    r"^[ \t]*const[ \t]+APP_VERSION[ \t]*=[ \t]*"
    r"(?P<quote>[\"'])(?P<version>[^\"'\r\n]*)(?P=quote)[ \t]*;[ \t]*(?://[^\r\n]*)?\r?$",
    re.MULTILINE,
)


class VersionError(ValueError):
    pass


def parse_version(value):
    match = VERSION_RE.fullmatch(value)
    if match is None:
        raise VersionError(f"無効なアプリ版 {value!r}。先頭ゼロのない vX.Y.Z を指定してください。")
    return tuple(map(int, match.groups()))


def find_version(source):
    """既存の単独行const定義を厳密に検査し、置換する文字列の位置を返す。"""
    if len(DEFINITION_RE.findall(source)) != 1 or len(ASSIGNMENT_RE.findall(source)) != 1:
        raise VersionError("APP_VERSION の定義・代入は各1箇所だけ必要です（欠損・重複を確認）。")
    match = CONSTANT_RE.search(source)
    if match is None:
        raise VersionError('APP_VERSION は単独行の const APP_VERSION = "vX.Y.Z"; で定義してください。')
    parse_version(match["version"])
    return match


def bump_file(path, version=None):
    # bytes経由で読み書きし、改行・引用符・周辺のUI/ロジックをそのまま保つ。
    source = path.read_bytes().decode("utf-8")
    match = find_version(source)
    old = match["version"]
    major, minor, patch = parse_version(old)
    new = version if version is not None else f"v{major}.{minor}.{patch + 1}"
    if parse_version(new) <= (major, minor, patch):
        raise VersionError(f"更新先 {new} は現在の {old} より大きい版にしてください。")
    updated = source[:match.start("version")] + new + source[match.end("version"):]
    path.write_bytes(updated.encode("utf-8"))
    return old, new


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", nargs="?", help="明示する更新先（例: v1.8.0）。省略時はpatch +1。")
    args = parser.parse_args(argv)
    try:
        old, new = bump_file(ROOT / "index.html", args.version)
    except (OSError, UnicodeError, VersionError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"APP_VERSION: {old} → {new}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
