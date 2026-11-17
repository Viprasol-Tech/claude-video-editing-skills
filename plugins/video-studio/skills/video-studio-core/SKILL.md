---
name: video-studio-core
description: Shared engine for the Video Studio editing skills. It transcribes a raw clip, cuts silences and filler words, cuts out the speaker for text-behind-head effects, renders HTML motion-graphics overlays frame by frame, and finishes the video (grade, grain, sound effects, music ducking, loudness). Use it directly for a plain clean edit, or through any Video Studio style skill (halo-cut, depth-type and others).
license: MIT
---

# Video Studio Core

The engine every Video Studio style skill runs on. Raw clip in, finished edit out, all on the user's own computer, free.

## Setup (once)

```bash
pip install faster-whisper playwright numpy pillow mediapipe
python -m playwright install chromium
# plus FFmpeg on PATH: brew install ffmpeg | winget install ffmpeg | sudo apt install ffmpeg
python scripts/check_env.py
```

Run `scripts/check_env.py` first whenever you are unsure. If something is missing, tell the user the exact fix it prints.

## Paths

- `CORE` = this skill's folder (it contains `scripts/` and `runtime/`).
- A style skill sits next to it, e.g. `~/.claude/skills/halo-cut`. Its folder holds `theme.json` and `theme.css`.
- Put each job in its own work folder next to the user's clip, e.g. `./edit-myclip/`. Never write inside the skill folders.

## The pipeline

```bash
python CORE/scripts/run.py clip.mp4 --style STYLE_DIR --work edit-myclip --stop-after plan
#   prep -> transcribe -> autocut -> matte (if the style needs it) -> make_plan
# now refine edit-myclip/plan.json (see "Refine the plan"), preview, then:
python CORE/scripts/render.py edit-myclip/plan.json --frames 1,4,8,12   # contact sheet, look at it
python CORE/scripts/render.py edit-myclip/plan.json                       # full overlay render + composite
python CORE/scripts/finish.py edit-myclip/plan.json --formats 1:1         # grade, audio, extra sizes
```

The individual steps (all accept `--help`):

| script | does |
| --- | --- |
| `prep.py INPUT --work W` | constant 30 fps, upright, long side ≤ 1920. `--start/--end` to trim |
| `transcribe.py --work W` | faster-whisper word timestamps. `--model small` (default) / `medium` / `large-v3`, `--language hi`, `--prompt "Viprasol, MT5"` for names. `--from-srt` imports subtitles |
| `autocut.py --work W` | removes pauses > `--max-gap` (0.35 s), filler words, and `--cut "12-14.5"` ranges (retakes). `--keep-all` keeps everything |
| `matte.py --work W` | person mask for depth effects. `--backend mediapipe` (default), `rembg`, `chroma` (green screen) |
| `make_plan.py --work W --style S` | draft plan from transcript + theme |
| `render.py PLAN` | overlays + composite. `--frames` for stills, `--preview t` for one still |
| `finish.py PLAN` | grade, grain, sfx, music ducking, -14 LUFS, `--formats 1:1,16:9` |
| `clip_candidates.py --work W` | best 20–60 s moments in a long video |
| `multicam.py camA camB --out` | auto-switch cameras by who is talking |

## Refine the plan (this is where the edit gets good)

`make_plan.py` is a heuristic first draft. Before rendering, read `words.json` (the transcript) and improve `plan.json`:

1. **Hook.** The first 2 seconds decide retention. Rewrite the hook text so it is short (≤ 7 words) and punchy.
2. **Key words.** Replace weak auto-picked key words with the words that carry meaning: numbers, results, contrasts, names.
3. **Headlines and cards.** One idea per element. Max 3 words for behind-head headlines.
4. **Numbers.** Every important number becomes a counter or a chart.
5. **Lists.** If the speaker lists things, add a card whose items appear at the moment each is said (`items[].at`).
6. **Timing.** Elements start 0.05–0.1 s before the word is spoken. Nothing on screen for less than 0.6 s.
7. **Safe zones (9:16).** Keep text between 10% and 85% of the height and away from the right edge buttons.
8. **Density.** Something changes every 1.5–3 s in reels, every 4–8 s in long-form. Don't stack more than 2 overlays at once.

Element reference: `references/plan-schema.md`. Theme reference: `references/theme-schema.md`.

## QA before you hand it over

- Render a contact sheet (`--frames`) and look at it: text readable, nothing cut off, nothing over the face unless intended.
- Check the final: `ffprobe final.mp4`, duration matches, audio present.
- Report to the user: what was cut (seconds removed), the look applied, and the file path.

## Troubleshooting

- `ERR_TUNNEL`/font errors: Google Fonts need internet. Without it the fallback fonts are used.
- Matte looks jumpy: `matte.py --smooth 0.7`. Hair edges harsh: `--feather 5`. Wrong person picked: use `--backend rembg`.
- Too slow: `transcribe.py --model base`, `render.py --workers 4` on a strong machine.
- Captions wrong: fix the words in `words.json` (keep times) and re-run `make_plan.py`, or edit the `words` array in the plan.
