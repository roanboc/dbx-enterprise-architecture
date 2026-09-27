# The tutorial film

A four-minute film for a newcomer: **why a new EA platform**, **what's new**, **a tour of
the screens** and **where to start**. The screens are the application itself, captured from
the sample model of a fictional university, and the whole film is made from code, the same
way as the films it follows: change a line of narration or a screen, and the film re-times
and redraws itself.

| Chapter | What it shows |
| ------- | ------------- |
| Why a new EA platform | A question about how the enterprise works takes a week; the answers are spread across diagrams, spreadsheets, a service desk, an asset register and people's memory; knowledge locked in pictures, copied by hand, out of reach, in the tool's vocabulary |
| What's new | The architecture as governed data: answers that cite their elements, facts fed by their owners, one model on the data platform, a metamodel you change, governed change, agents that draft and people who approve |
| A tour of the screens | Home and its welcome, the help on every screen, Browse and an element's page, Ask and Impact, Propose to a branch, the review and the merge, Target state, Feeds, the Metamodel, Organisations, Users and roles, Health |
| Start here | The Guide and the `?` key |

The video itself is not committed: it is made by `make tutorial` and lands in `dist/`. The
captions are committed in `captions/` (`en.srt`, `en.vtt`), one per line of narration.

## How it is made

| File | What it holds |
| ---- | ------------- |
| `src/narration.json` | The narration, a line at a time, by scene and chapter, and the voice. The captions come from it too |
| `src/vodur.json` | How long each line is when voiced, written by `tools/tts.py`: the film times itself to it |
| `src/scenes.js` | What each scene shows: the drawn chapters, and for the tour, the beats — which screen, where the camera looks, what is marked and what is pressed |
| `src/engine.js` | The engine: the timeline, the camera, the window a screen is shown in, the captions, the kit the drawn chapters use. Every frame is a function of time |
| `fonts/` | Manrope and IBM Plex Mono, under the SIL Open Font License (`OFL-*.txt`), so a render needs no network |
| `tools/capture.py` | Seeds a store of its own with the sample model, a reviewer and a branch in review, starts the application on it, and screenshots each screen of the tour at twice the size with where every named control stands |
| `tools/tts.py` | Voices each line locally with the Kokoro model; nothing is sent anywhere |
| `tools/build.py` | Builds `build/render.html`, the page the film is drawn on |
| `tools/audio.py` | Mixes the voice, a quiet synthesised bed of music, a click on each press and a chime at each chapter |
| `tools/check.py` | Draws every tenth of a second and lists any moment that fails; `--stills` writes a still into every line, to look at |
| `tools/render.py` | Renders 1080p at 30 frames a second in resumable chunks, then lays the soundtrack under it |
| `tools/captions.py` | Writes `captions/en.srt` and `en.vtt` |

## Setup (once)

1. The application's own setup: `make install`.
2. The voice model, about 350 MB, into `docs/tutorial/models/` (not committed), or anywhere
   `EA_TUTORIAL_MODELS` names:

   ```bash
   mkdir -p docs/tutorial/models
   curl -L -o docs/tutorial/models/kokoro-v1.0.onnx https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
   curl -L -o docs/tutorial/models/voices-v1.0.bin https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
   ```

If `tools/tts.py` stops with espeak-ng unable to find `phontab` under a path that does not
exist, the speech library is looking where it was built rather than where it was installed.
Install espeak-ng on the machine and set `PHONEMIZER_ESPEAK_LIBRARY` to its library, or link
the path the error names to the `espeak-ng-data` folder inside the installed
`espeakng_loader` package.

## Make it

```bash
make tutorial                                   # every step below, in order
```

Or a step at a time, from the repository's root, with
`FILM="uv run --group gui --with-requirements docs/tutorial/requirements.txt python"`:

```bash
$FILM docs/tutorial/tools/capture.py            # the screens, from the application (about 2 minutes)
$FILM docs/tutorial/tools/tts.py                # the voice (about 2 minutes the first time)
$FILM docs/tutorial/tools/build.py
$FILM docs/tutorial/tools/check.py --stills     # every moment drawn; stills in build/stills/
$FILM docs/tutorial/tools/audio.py
$FILM docs/tutorial/tools/render.py --workers 3 # dist/ea-repository-tour.mp4 (about 10 minutes)
$FILM docs/tutorial/tools/captions.py
```

## Change it

- **A word of the narration:** edit `src/narration.json`, delete that line's file in
  `build/vo/`, then voice, build, mix and render again. The film re-times itself.
- **A screen changed in the application:** capture again. A control the tour names that has
  moved is found again by its selector; one that has gone stops the capture and says which.
- **What the tour shows or where it looks:** the beats in `src/scenes.js`; `check.py --stills`
  shows the result without a render.

Keep it free of anything the repository keeps free: the screens show the fictional sample
model only, and no institution, person, tool or model name is said or shown.
