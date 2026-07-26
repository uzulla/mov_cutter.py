#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from mov_cutter import build_output_path, cut_video

CHUNK_SIZE = 1024 * 1024
RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")

HTML_PAGE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>mov-cutter</title>
<style>
  body { font-family: sans-serif; margin: 2rem; max-width: 900px; }
  video { width: 100%; max-height: 60vh; background: #000; }
  .controls { display: flex; gap: 1rem; align-items: center; margin-top: 1rem; flex-wrap: wrap; }
  .marks { margin-top: 0.5rem; font-size: 1.1rem; }
  button { padding: 0.5rem 1rem; font-size: 1rem; cursor: pointer; }
  #cutBtn { background: #2563eb; color: white; border: none; border-radius: 4px; }
  #status { margin-top: 1rem; white-space: pre-wrap; }
</style>
</head>
<body>
<h1>mov-cutter</h1>
<video id="video" src="/video" controls></video>
<div class="controls">
  <button id="markStart">ここを開始にする</button>
  <button id="markEnd">ここを終了にする</button>
  <button id="clear">クリア</button>
  <button id="cutBtn">切り出す</button>
</div>
<div class="marks">
  開始: <span id="startLabel">(先頭)</span> / 終了: <span id="endLabel">(末尾)</span>
</div>
<div id="status"></div>
<script>
const video = document.getElementById("video");
const startLabel = document.getElementById("startLabel");
const endLabel = document.getElementById("endLabel");
const status = document.getElementById("status");
let startTime = null;
let endTime = null;

function fmt(t) {
  if (t === null) return null;
  const m = Math.floor(t / 60);
  const s = (t - m * 60).toFixed(2);
  return m + ":" + s.padStart(5, "0");
}

document.getElementById("markStart").onclick = () => {
  startTime = video.currentTime;
  startLabel.textContent = fmt(startTime);
};
document.getElementById("markEnd").onclick = () => {
  endTime = video.currentTime;
  endLabel.textContent = fmt(endTime);
};
document.getElementById("clear").onclick = () => {
  startTime = null;
  endTime = null;
  startLabel.textContent = "(先頭)";
  endLabel.textContent = "(末尾)";
  status.textContent = "";
};
document.getElementById("cutBtn").onclick = async () => {
  if (startTime !== null && endTime !== null && startTime >= endTime) {
    status.textContent = "エラー: 開始時刻は終了時刻より前にしてください。";
    return;
  }
  status.textContent = "処理中...";
  try {
    const res = await fetch("/cut", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ start: startTime, end: endTime }),
    });
    const data = await res.json();
    status.textContent = data.ok ? ("作成しました: " + data.output) : ("エラー: " + data.error);
  } catch (e) {
    status.textContent = "エラー: " + e;
  }
};
</script>
</body>
</html>
"""


def seconds_to_mmss(seconds: float) -> str:
    minutes = int(seconds // 60)
    secs = seconds - minutes * 60
    return f"{minutes}:{secs:05.2f}"


class Handler(BaseHTTPRequestHandler):
    input_path: Path

    def log_message(self, format: str, *args) -> None:
        pass

    def do_GET(self) -> None:
        if self.path == "/":
            self.serve_html()
        elif self.path == "/video":
            self.serve_video()
        else:
            self.send_error(404)

    def serve_html(self) -> None:
        body = HTML_PAGE.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_video(self) -> None:
        file_size = self.input_path.stat().st_size
        range_header = self.headers.get("Range")
        start, end = 0, file_size - 1

        if range_header:
            match = RANGE_RE.match(range_header)
            if not match:
                self.send_error(416)
                return
            if match.group(1):
                start = int(match.group(1))
            if match.group(2):
                end = int(match.group(2))
            elif match.group(1):
                end = file_size - 1

        length = end - start + 1
        self.send_response(206 if range_header else 200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if range_header:
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.end_headers()

        try:
            with open(self.input_path, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self) -> None:
        if self.path != "/cut":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length))
            start = payload.get("start")
            end = payload.get("end")

            start_label = seconds_to_mmss(start) if start is not None else None
            end_label = seconds_to_mmss(end) if end is not None else None
            output_path = build_output_path(self.input_path, start_label, end_label)

            result = cut_video(self.input_path, start, end, output_path)
            if result.returncode != 0:
                response = {"ok": False, "error": result.stderr}
            else:
                response = {"ok": True, "output": str(output_path)}
        except Exception as e:
            response = {"ok": False, "error": str(e)}

        body = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="動画をブラウザで再生しながら開始/終了を指定して切り出すUI"
    )
    parser.add_argument("-i", "--input", required=True, help="入力MP4ファイルパス")
    parser.add_argument("--port", type=int, default=8642, help="ローカルサーバーのポート番号")
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None:
        print("エラー: ffmpeg が見つかりません。インストールしてPATHを通してください。", file=sys.stderr)
        return 1

    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"エラー: 入力ファイルが見つかりません: {input_path}", file=sys.stderr)
        return 1

    if input_path.suffix.lower() != ".mp4":
        print("エラー: 現在はMP4のみサポートしています。", file=sys.stderr)
        return 1

    Handler.input_path = input_path
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"サーバーを起動しました: {url}")
    print("終了するには Ctrl+C を押してください。")
    webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
