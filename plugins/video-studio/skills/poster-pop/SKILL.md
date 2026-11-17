---
name: poster-pop
description: "Poster Pop video-editing style for Claude: Retro collage edit: the background behind you swaps to a new bold poster pattern (stripes, checkerboard, grid, sunburst, colour field) on every sentence, with a chunky slab headline and warm film grain. Use for stories, opinions, fun explainers, music and nostalgic or playful personal-brand reels. Turns a raw talking clip into a finished 9:16 edit with the video-studio-core engine (transcribe, auto-cut, motion graphics, sound, grade)."
license: MIT
---

# Poster Pop

Retro collage edit: the background behind you swaps to a new bold poster pattern (stripes, checkerboard, grid, sunburst, colour field) on every sentence, with a chunky slab headline and warm film grain.

- **Best for:** stories, opinions, fun explainers, music and nostalgic or playful personal-brand reels
- **Category:** Talking-head reel
- **Default format:** 9:16 (change with `--format 9:16 | 1:1 | 4:5 | 16:9`)
- **Needs camera footage:** yes, a raw talking clip
- **Background replaced / cut-out:** yes (uses the person matte: `python CORE/scripts/matte.py --work WORK --input WORK/cut.mp4 --out WORK/matte.mp4` if `run.py` did not make it)

## Before you start

This style runs on the **video-studio-core** skill, which must be installed in the same skills folder.

- `CORE` = the `video-studio-core` folder next to this one (e.g. `~/.claude/skills/video-studio-core`).
- `STYLE` = this skill's folder (it holds `theme.json` and `theme.css`).
- First time on a machine: `python CORE/scripts/check_env.py`, and fix anything it reports.

## Make the edit

```bash
python CORE/scripts/run.py clip.mp4 --style STYLE --work edit-poster-pop --stop-after plan
# refine edit-poster-pop/plan.json (see below), then check stills:
python CORE/scripts/render.py edit-poster-pop/plan.json --frames 1,3,6,9
python CORE/scripts/render.py edit-poster-pop/plan.json
python CORE/scripts/finish.py edit-poster-pop/plan.json --platform reels
python CORE/scripts/qc.py edit-poster-pop/final.mp4 --plan edit-poster-pop/plan.json
```

Open `contact_sheet.png` and look at it before the full render. Pass `--title "..."` to `run.py` / `make_plan.py` for the title line.

## The look

- Your real background is removed; a new poster backdrop appears on every sentence (6 patterns, cycled).
- One or two words per sentence as a chunky slab-serif headline at the top, partly behind your head.
- Small uppercase condensed captions low in the frame. Warm film grade, heavy grain and vignette.

## Refine the plan

- Read `words.json`, fix mis-heard words (keep their times) and rewrite the hook.
- Replace weak auto-picked key words and headlines with the words that carry the meaning.
- Pick the headline word per sentence (`headline` elements); keep it 1-2 words.
- Re-order the backdrops by changing each `background` element's `className` (`pp-stripes pp-checker pp-grid pp-sun pp-red pp-blue`).
- A shot without you (a full-screen pattern + headline) works as a breather: add a `background` on the `front` layer with a `headline` for 0.6-1 s.
- Framing: a tight selfie (head touching the top, shoulders filling the width) works best with `speaker.personDrop` 0.1-0.14 (cut-out slides down, top edge fades); a shot with headroom and space at the sides can use `speaker.personScale` 0.8-0.9 instead. Check a still.
- Element types and fields: `CORE/references/plan-schema.md`, `CORE/references/motion.md`.

## Check before delivering

- Contact sheet: text readable, nothing cut off, nothing over the face, safe zones (10-85% of the height, clear of the right 12% in 9:16).
- Overlays land with the spoken word, not after it.
- `qc.py` with 0 FAIL. Tell the user what was cut, the look, and where the file is.

## Example requests

- "Retro poster edit, new background every line."
- "80s collage look with stripes and checkerboards behind me."
