"""Mix the soundtrack: the voice on its lines, a quiet bed of music under it that lifts a little
in the pauses, a soft click on every press and a chime at every chapter. Written to
`build/mix.wav`. The music is synthesised here, so there is nothing to license.

    python docs/tutorial/tools/audio.py
"""

from __future__ import annotations

import numpy as np
import soundfile as sf
from common import BUILD
from page import info, served
from playwright.sync_api import sync_playwright
from scipy.signal import resample_poly

RATE = 44100
MUSIC_UNDER_VOICE = 18  # dB: the music where nobody speaks, against the speech
DUCK = 4.5  # dB: and how much further it steps back under a line


def tone_time(seconds: float) -> np.ndarray:
    return np.arange(int(seconds * RATE), dtype=np.float32) / RATE


def envelope(seconds: float, attack: float, release: float) -> np.ndarray:
    n = int(seconds * RATE)
    e = np.ones(n, np.float32)
    a, r = max(1, int(attack * RATE)), max(1, int(release * RATE))
    e[:a] = np.linspace(0, 1, a)
    e[n - r :] *= np.linspace(1, 0, r)
    return e


def midi(m: float) -> float:
    return 440 * 2 ** ((m - 69) / 12)


def main() -> None:
    with served() as url, sync_playwright() as p:
        browser = p.chromium.launch()
        film = info(browser, url)
        browser.close()
    total = film["total"]
    n = int((total + 1) * RATE)
    left, right, voice = (np.zeros(n, np.float32) for _ in range(3))

    def put(sig: np.ndarray, start: float, gain: float, pan: float = 0.0) -> None:
        i = int(start * RATE)
        j = min(n, i + len(sig))
        if j <= i or i < 0:
            return
        s = sig[: j - i] * gain
        left[i:j] += s * np.float32(np.sqrt(0.5 * (1 - pan)))
        right[i:j] += s * np.float32(np.sqrt(0.5 * (1 + pan)))

    for c in film["caps"]:
        x, sr = sf.read(str(BUILD / "vo" / f"{c['sid']}__{c['id']}.wav"), dtype="float32")
        if sr != RATE:
            x = resample_poly(x, RATE, sr).astype(np.float32)
        i = int(c["s"] * RATE)
        voice[i : i + len(x)] += x[: n - i]

    # A warm, slow bed: open chords of D major and its neighbours, a chord every eight seconds,
    # soft and wide, with a felt-piano note now and then.
    chords = [[50, 57, 61, 64, 66], [47, 54, 57, 61, 62], [43, 50, 54, 57, 61], [45, 52, 57, 59, 61]]
    step = 8.0
    k = 0
    t = 0.0
    rng = np.random.default_rng(7)
    while t < total + step:
        chord, x = chords[k % len(chords)], tone_time(step + 3)
        e = envelope(step + 3, 2.5, 3.0) * (1 + 0.06 * np.sin(2 * np.pi * 0.08 * x))
        for pan, detune in ((-0.7, 0.997), (0.7, 1.003), (0.0, 1.0)):
            s = sum(
                np.sin(2 * np.pi * midi(m) * detune * x + m) + 0.15 * np.sin(4 * np.pi * midi(m) * detune * x)
                for m in chord
            )
            put((s * e / len(chord)).astype(np.float32), t - 1.5, 0.035 if pan else 0.025, pan)
        put((np.sin(2 * np.pi * midi(chord[0] - 12) * x) * e).astype(np.float32), t - 1.5, 0.02)
        u = t + 0.6
        while u < t + step - 0.5:  # a note from the chord, an octave up, placed sparsely
            m = chord[int(rng.integers(1, len(chord)))] + 12
            y = tone_time(3.0)
            f = midi(m)
            note = sum(
                np.sin(2 * np.pi * f * h * y) * np.exp(-y * (1.2 + 0.9 * h)) * w
                for h, w in ((1, 1), (2, 0.3), (3, 0.1))
            )
            put((note * np.minimum(1, y / 0.01)).astype(np.float32), u, 0.035, float(rng.uniform(-0.5, 0.5)))
            u += 2.2 * (0.75 + 0.5 * rng.random())
        t += step
        k += 1

    effects_l, effects_r = np.zeros(n, np.float32), np.zeros(n, np.float32)

    def fx(sig: np.ndarray, start: float, gain: float, pan: float = 0.0) -> None:
        i = int(start * RATE)
        j = min(n, i + len(sig))
        if j > i >= 0:
            effects_l[i:j] += sig[: j - i] * gain * np.float32(np.sqrt(0.5 * (1 - pan)))
            effects_r[i:j] += sig[: j - i] * gain * np.float32(np.sqrt(0.5 * (1 + pan)))

    for at in film["clicks"]:  # a mouse's click: a short tick with a little body
        x = tone_time(0.06)
        tick = rng.standard_normal(len(x)).astype(np.float32) * np.exp(-x * 160) * 0.5 + np.sin(
            2 * np.pi * 2100 * x
        ) * np.exp(-x * 90)
        fx(tick.astype(np.float32), at, 0.15, 0.2)
    for ch in film["chapters"][1:]:  # a soft chime as a chapter begins
        x = tone_time(2.5)
        bell = sum(
            np.sin(2 * np.pi * 880 * r * x) * np.exp(-x / d) * a
            for r, d, a in ((1, 1.6, 1), (2.76, 0.9, 0.4), (5.4, 0.5, 0.2))
        )
        fx(bell.astype(np.float32), ch["start"] + 0.1, 0.09)

    # The music is set by the voice, not by hand: 18 dB under the speech where nobody speaks,
    # and 4.5 dB lower again under a line, stepping back slowly so it never pumps. It fades in
    # at the start and out at the end.
    speaking = np.zeros(n, bool)
    for c in film["caps"]:
        speaking[int(c["s"] * RATE) : int(c["e"] * RATE)] = True
    rms = lambda x: float(np.sqrt(np.mean(np.square(x)))) + 1e-9  # noqa: E731
    level = rms(voice[speaking]) * 10 ** (-MUSIC_UNDER_VOICE / 20) / rms(np.concatenate([left, right]))
    duck = np.where(speaking, np.float32(10 ** (-DUCK / 20)), np.float32(1))
    w = int(0.4 * RATE)
    duck = np.convolve(duck.astype(np.float32), np.ones(w, np.float32) / w, "same")
    tt = np.arange(n, dtype=np.float32) / RATE
    fade = np.clip((total - tt) / 4.0, 0, 1) * np.clip(tt / 2.0, 0, 1)
    fx_level = rms(voice[speaking]) / 0.08  # the clicks and chimes were written against a voice this loud
    out_l = voice + left * level * duck * fade + effects_l * fx_level
    out_r = voice + right * level * duck * fade + effects_r * fx_level
    peak = max(np.abs(out_l).max(), np.abs(out_r).max())
    out_l, out_r = out_l / peak * 0.9, out_r / peak * 0.9
    quiet = ~speaking & (tt > 2) & (tt < total - 4)
    said = 20 * np.log10(rms(out_l[speaking]) / rms(out_l[quiet]))
    print(f"the voice stands {said:.1f} dB above the pauses")
    sf.write(str(BUILD / "mix.wav"), np.stack([out_l, out_r], 1), RATE, subtype="PCM_16")
    print(
        f"mixed {total:.1f}s: {len(film['caps'])} lines, {len(film['clicks'])} presses, {len(film['chapters'])} chapters"
    )


if __name__ == "__main__":
    main()
