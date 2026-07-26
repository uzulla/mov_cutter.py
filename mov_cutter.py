#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def parse_time(value: str) -> float:
    parts = value.split(":")
    if len(parts) > 3:
        raise ValueError(f"時刻フォーマットが不正です: {value!r}")
    try:
        numbers = [float(p) for p in parts]
    except ValueError:
        raise ValueError(f"時刻フォーマットが不正です: {value!r}")
    if any(n < 0 for n in numbers):
        raise ValueError(f"時刻は正の値である必要があります: {value!r}")

    if len(numbers) == 1:
        seconds = numbers[0]
    elif len(numbers) == 2:
        minutes, seconds = numbers
        seconds = minutes * 60 + seconds
    else:
        hours, minutes, seconds = numbers
        seconds = hours * 3600 + minutes * 60 + seconds
    return seconds


def build_output_path(input_path: Path, start: str | None, end: str | None) -> Path:
    start_label = start.replace(":", ".") if start is not None else "start"
    end_label = end.replace(":", ".") if end is not None else "end"
    stem = input_path.stem
    return input_path.with_name(f"{stem}-cut-{start_label}-to-{end_label}.mp4")


def cut_video(
    input_path: Path,
    start_seconds: float | None,
    end_seconds: float | None,
    output_path: Path,
) -> subprocess.CompletedProcess:
    duration = None
    if end_seconds is not None:
        duration = end_seconds - (start_seconds if start_seconds is not None else 0.0)

    cmd = ["ffmpeg"]
    if start_seconds is not None:
        cmd += ["-ss", str(start_seconds)]
    if duration is not None:
        cmd += ["-t", str(duration)]
    cmd += ["-i", str(input_path), "-c", "copy", "-y", str(output_path)]
    return subprocess.run(cmd, capture_output=True, text=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="MP4動画を再エンコードせずに指定区間で切り出す"
    )
    parser.add_argument("-i", "--input", required=True, help="入力MP4ファイルパス")
    parser.add_argument("-s", "--start", help="開始時刻 (例: 3:30)。省略時は動画の先頭から")
    parser.add_argument("-e", "--end", help="終了時刻 (例: 4:59)。省略時は動画の末尾まで")
    parser.add_argument("-o", "--output", help="出力ファイルパス（省略時は自動生成）")
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None:
        print("エラー: ffmpeg が見つかりません。インストールしてPATHを通してください。", file=sys.stderr)
        return 1

    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"エラー: 入力ファイルが見つかりません: {input_path}", file=sys.stderr)
        return 1

    try:
        start_seconds = parse_time(args.start) if args.start is not None else None
        end_seconds = parse_time(args.end) if args.end is not None else None
    except ValueError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1

    if start_seconds is not None and end_seconds is not None:
        if start_seconds >= end_seconds:
            print("エラー: 開始時刻は終了時刻より前である必要があります。", file=sys.stderr)
            return 1
    elif end_seconds is not None:
        if end_seconds <= 0:
            print("エラー: 終了時刻は0より大きい必要があります。", file=sys.stderr)
            return 1

    output_path = Path(args.output) if args.output else build_output_path(input_path, args.start, args.end)

    print("注意: -c copy のため開始位置はキーフレーム境界にスナップされます")

    result = cut_video(input_path, start_seconds, end_seconds, output_path)

    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return result.returncode

    print(f"作成しました: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
