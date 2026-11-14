#!/usr/bin/env python3
"""PRのアプリ変更に、最新mainより大きいAPP_VERSIONが含まれることを検査する。"""

import argparse
from pathlib import PurePosixPath
import subprocess
import sys

from bump_app_version import ROOT, VersionError, find_version, parse_version


def git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.decode("utf-8")


def is_app_path(path):
    # 現在の配信物。追加のJS/CSS等を分離・配信するときはここも更新する。
    # .gitkeepは配信物ではなく、空ディレクトリを保持する開発用ファイル。
    return path == "index.html" or (
        path.startswith(("assets/", "runner/")) and PurePosixPath(path).name != ".gitkeep"
    )


def check_versions(base, head):
    # baseは実行時点の最新main。変更ファイルだけは共通祖先から求め、
    # mainのみに入った別PRの変更を当該PRの変更と誤認しない。
    base = git("rev-parse", "--verify", "--end-of-options", f"{base}^{{commit}}").strip()
    head = git("rev-parse", "--verify", "--end-of-options", f"{head}^{{commit}}").strip()
    ancestor = git("merge-base", base, head).strip()
    paths = git("diff", "--name-only", "--no-renames", "-z", ancestor, head, "--").split("\0")
    changed = [path for path in paths if is_app_path(path)]
    if not changed:
        return "OK: アプリ配信物の変更なし。文書・テスト・開発ツールのみなら版更新は不要です。"

    base_version = find_version(git("show", f"{base}:index.html"))["version"]
    head_version = find_version(git("show", f"{head}:index.html"))["version"]
    if parse_version(head_version) <= parse_version(base_version):
        raise VersionError(
            f"アプリ変更がありますが、PRの {head_version} は最新mainの {base_version} より大きくありません。"
        )
    return f"OK: APP_VERSION {base_version} → {head_version}（アプリ変更 {len(changed)} ファイル）"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main", help="取得済みの最新main参照（既定: origin/main）")
    parser.add_argument("--head", default="HEAD", help="PR先端の参照（既定: HEAD）")
    args = parser.parse_args(argv)
    try:
        message = check_versions(args.base, args.head)
    except (VersionError, subprocess.CalledProcessError, UnicodeError) as error:
        detail = error.stderr.decode("utf-8", errors="replace") if isinstance(error, subprocess.CalledProcessError) else str(error)
        print(f"ERROR: {detail}", file=sys.stderr)
        print(
            "修正方法: git fetch origin main で最新mainを取得して取り込み、"
            "python3 scripts/bump_app_version.py（または最新mainより大きい vX.Y.Z を引数指定）を実行。"
            "APP_VERSION の欠損・重複・形式も確認し、変更をコミットしてpushしてください。",
            file=sys.stderr,
        )
        return 1
    print(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
