"""Voice every line of the narration into `build/vo/`, and write how long each is to
`src/vodur.json`: the film times itself to the voice.

The voice is Kokoro, run locally from `models/` (or `EA_TUTORIAL_MODELS`); nothing is sent
anywhere. A line already voiced is kept; delete its file to voice it again.

    python docs/tutorial/tools/tts.py [--keep-timings]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time

import numpy as np
import soundfile as sf
from common import BUILD, MODELS, VODUR, narration

ESPEAK_HINT = (
    "The speech library could not find its espeak-ng data. Install espeak-ng on the machine and set "
    "PHONEMIZER_ESPEAK_LIBRARY to its library, or link the data the error names to the copy inside "
    "the espeakng_loader package (see docs/tutorial/README.md)."
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--keep-timings",
        action="store_true",
        help="fail if a line is more than 0.05 s off the committed timings",
    )
    args = ap.parse_args()
    model, voices = MODELS / "kokoro-v1.0.onnx", MODELS / "voices-v1.0.bin"
    if not (model.exists() and voices.exists()):
        sys.exit(f"the voice model is not in {MODELS}: see docs/tutorial/README.md, Setup")
    from kokoro_onnx import Kokoro

    story = narration()
    v = story["voice"]
    k = Kokoro(str(model), str(voices))
    durations, t0 = {}, time.time()
    for scene in story["scenes"]:
        for line in scene["lines"]:
            key = f"{scene['id']}/{line['id']}"
            path = BUILD / "vo" / f"{scene['id']}__{line['id']}.wav"
            if path.exists():
                info = sf.info(str(path))
                durations[key] = round(info.frames / info.samplerate, 3)
                continue
            said = line["text"]
            for pattern, spoken in v.get("say", []):
                said = re.sub(pattern, spoken, said)
            try:
                samples, rate = k.create(said, voice=v["voice"], speed=v["speed"], lang=v["lang"])
            except Exception as e:  # noqa: BLE001 — the one failure worth explaining is espeak's
                sys.exit(f"{key}: {e}\n{ESPEAK_HINT}")
            loud = np.where(np.abs(samples) > 0.01)[0]
            if len(loud):  # trimmed to the voice, with a breath of room either side
                samples = samples[max(0, loud[0] - 240) : loud[-1] + 480]
            sf.write(str(path), samples, rate)
            durations[key] = round(len(samples) / rate, 3)
            print(f"{key:24} {durations[key]:6.2f}s  ({time.time() - t0:.0f}s)", flush=True)
    if args.keep_timings:
        old = json.loads(VODUR.read_text()) if VODUR.exists() else {}
        off = [
            k for k in sorted(set(old) | set(durations)) if abs(old.get(k, -9) - durations.get(k, 9)) > 0.05
        ]
        if off:
            sys.exit(f"{len(off)} lines differ from src/vodur.json: run tools/tts.py and commit the timings")
    else:
        VODUR.write_text(json.dumps(durations, indent=1) + "\n", encoding="utf-8")
    print(f"{sum(durations.values()):.1f}s of speech in {len(durations)} lines")


if __name__ == "__main__":
    main()
