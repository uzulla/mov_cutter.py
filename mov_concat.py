#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def build_output_path(first_input: Path) -> Path:
    return first_input.with_name(f"{first_input.stem}-concat.mp4")


def build_concat_list(input_paths: list[Path]) -> str:
    lines = []
    for p in input_paths:
        # concat demuxerのリスト形式。シングルクォートは '\'' でエスケープする
        escaped = str(p.resolve()).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    return "\n".join(lines) + "\n"


def concat_videos(input_paths: list[Path], output_path: Path) -> subprocess.CompletedProcess:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(build_concat_list(input_paths))
        list_path = Path(f.name)
    try:
        cmd = [
            "ffmpeg",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_path),
            "-c", "copy",
            "-y", str(output_path),
        ]
        return subprocess.run(cmd, capture_output=True, text=True)
    finally:
        list_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="複数のMP4動画を再エンコードせずに順番に連結する"
    )
    parser.add_argument("inputs", nargs="+", metavar="INPUT", help="入力MP4ファイルパス（指定順に連結）")
    parser.add_argument("-o", "--output", help="出力ファイルパス（省略時は自動生成）")
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None:
        print("エラー: ffmpeg が見つかりません。インストールしてPATHを通してください。", file=sys.stderr)
        return 1

    if len(args.inputs) < 2:
        print("エラー: 入力ファイルは2つ以上指定してください。", file=sys.stderr)
        return 1

    input_paths = [Path(p) for p in args.inputs]
    for p in input_paths:
        if not p.is_file():
            print(f"エラー: 入力ファイルが見つかりません: {p}", file=sys.stderr)
            return 1

    output_path = Path(args.output) if args.output else build_output_path(input_paths[0])

    resolved_inputs = {p.resolve() for p in input_paths}
    if output_path.resolve() in resolved_inputs:
        print(f"エラー: 出力ファイルが入力ファイルと同じです: {output_path}", file=sys.stderr)
        return 1

    print("注意: -c copy のため全入力のコーデック・解像度等のパラメータが一致している必要があります")

    result = concat_videos(input_paths, output_path)

    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return result.returncode

    print(f"作成しました: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
