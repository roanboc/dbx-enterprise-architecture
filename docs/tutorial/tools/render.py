"""Render the film to `dist/ea-repository-tour.mp4`: 1080p at 30 frames a second, in chunks a
browser each draws, so a stopped render resumes from the chunks it finished; then the
soundtrack is laid under it, its loudness set for the web.

    python docs/tutorial/tools/render.py --workers 3
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import subprocess
import time
from multiprocessing import Process

import imageio_ffmpeg
from common import BUILD, DIST, FILM
from page import info, open_film, served
from playwright.sync_api import sync_playwright

FPS, CHUNK = 30, 450  # 15 seconds a chunk
FF = imageio_ffmpeg.get_ffmpeg_exe()
CHUNKS = BUILD / "chunks"


def work(url: str, starts: list[int], frames: int, t0: float) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = open_film(browser, url, 1.0)
        for c0 in starts:
            out = CHUNKS / f"c{c0:06d}.mp4"
            enc = subprocess.Popen(
                [
                    FF,
                    "-y",
                    "-loglevel",
                    "error",
                    "-f",
                    "image2pipe",
                    "-framerate",
                    str(FPS),
                    "-c:v",
                    "mjpeg",
                    "-i",
                    "-",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-crf",
                    "18",
                    "-pix_fmt",
                    "yuv420p",
                    str(out),
                ],
                stdin=subprocess.PIPE,
            )
            for i in range(c0, min(frames, c0 + CHUNK)):
                data = page.evaluate(f"renderAt({i / FPS}, 0.93)")
                enc.stdin.write(base64.b64decode(data.split(",", 1)[1]))
            enc.stdin.close()
            enc.wait()
            (CHUNKS / f"c{c0:06d}.ok").write_text("1")
            print(f"chunk {c0} of {frames} ({time.time() - t0:.0f}s)", flush=True)
        browser.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=2, help="browsers drawing at once; about one per core")
    args = ap.parse_args()
    t0 = time.time()
    CHUNKS.mkdir(exist_ok=True)
    stamp = hashlib.sha1((BUILD / "render.html").read_bytes()).hexdigest()
    if not (CHUNKS / "stamp").exists() or (CHUNKS / "stamp").read_text() != stamp:
        for old in CHUNKS.glob("c*"):
            old.unlink()
        (CHUNKS / "stamp").write_text(stamp)
    with served() as url:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            frames = int(info(browser, url)["total"] * FPS)
            browser.close()
        starts = list(range(0, frames, CHUNK))
        todo = [c for c in starts if not (CHUNKS / f"c{c:06d}.ok").exists()]
        procs = [
            Process(target=work, args=(url, todo[k :: args.workers], frames, t0))
            for k in range(min(args.workers, len(todo)))
        ]
        for proc in procs:
            proc.start()
        for proc in procs:
            proc.join()
    if any(proc.exitcode for proc in procs):
        raise SystemExit("a render worker failed: run again to resume from the finished chunks")
    (CHUNKS / "list.txt").write_text("".join(f"file '{CHUNKS / f'c{c:06d}.mp4'}'\n" for c in starts))
    video = BUILD / "video.mp4"
    subprocess.run(
        [
            FF,
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(CHUNKS / "list.txt"),
            "-c",
            "copy",
            str(video),
        ],
        check=True,
    )
    out = DIST / f"{FILM}.mp4"
    mix = BUILD / "mix.wav"
    if mix.exists():
        subprocess.run(
            [
                FF,
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(video),
                "-i",
                str(mix),
                "-map",
                "0:v",
                "-map",
                "1:a",
                "-c:v",
                "copy",
                "-af",
                "loudnorm=I=-16:TP=-1.5:LRA=11",
                "-ar",
                "48000",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-shortest",
                "-movflags",
                "+faststart",
                str(out),
            ],
            check=True,
        )
    else:
        os.replace(video, out)
        print("no soundtrack yet (tools/audio.py): the video is silent")
    print(
        f"done: {out.relative_to(BUILD.parent)}, {out.stat().st_size / 1e6:.1f} MB, {time.time() - t0:.0f}s"
    )


if __name__ == "__main__":
    main()
