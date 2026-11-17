---
name: editorial-cards
description: "Editorial Cards video-editing style for Claude: Editorial explainer on a warm paper page: your footage sits in a tilted rounded card that moves to a new spot every sentence, big black words land as you say them, and key words get hand-drawn circles and underlines. Use for explainers, essays, interviews, education, opinions and thought-leadership clips. Turns a raw talking clip into a finished 9:16 edit with the video-studio-core engine (transcribe, auto-cut, motion graphics, sound, grade)."
license: MIT
---

# Editorial Cards

Editorial explainer on a warm paper page: your footage sits in a tilted rounded card that moves to a new spot every sentence, big black words land as you say them, and key words get hand-drawn circles and underlines.

- **Best for:** explainers, essays, interviews, education, opinions and thought-leadership clips
- **Category:** Explainer
- **Default format:** 9:16 (change with `--format 9:16 | 1:1 | 4:5 | 16:9`)
- **Needs camera footage:** yes, a raw talking clip
- **Person cut-out:** not needed

## Before you start

This style runs on the **video-studio-core** skill, which must be installed in the same skills folder.

- `CORE` = the `video-studio-core` folder next to this one (e.g. `~/.claude/skills/video-studio-core`).
- `STYLE` = this skill's folder (it holds `theme.json` and `theme.css`).
- First time on a machine: `python CORE/scripts/check_env.py`, and fix anything it reports.

## Make the edit

```bash
python CORE/scripts/run.py clip.mp4 --style STYLE --work edit-editorial-cards --stop-after plan
# refine edit-editorial-cards/plan.json (see below), then check stills:
python CORE/scripts/render.py edit-editorial-cards/plan.json --frames 1,3,6,9
python CORE/scripts/render.py edit-editorial-cards/plan.json
python CORE/scripts/finish.py edit-editorial-cards/plan.json --platform reels
python CORE/scripts/qc.py edit-editorial-cards/final.mp4 --plan edit-editorial-cards/plan.json
```

Open `contact_sheet.png` and look at it before the full render. Pass `--title "..."` to `run.py` / `make_plan.py` for the title line.

## The look

- Cream paper page; your footage is a rounded card with a slight tilt that jumps to a new position each sentence.
- The spoken words appear as big black editorial type at the top, word by word.
- Key words appear under the card in coral italic serif with a hand-drawn circle or underline.
- No colour look, light grain.

## Refine the plan

- Read `words.json`, fix mis-heard words (keep their times) and rewrite the hook.
- Replace weak auto-picked key words and headlines with the words that carry the meaning.
- Card positions live in `speaker.layouts` (`rect` px, `radius`, `rot` degrees, `start`/`end`). Keep cards between 34% and 80% of the height so the type stays clear.
- Hand-drawn marks are `scribble` elements (`kind` circle, underline, arrow, box, check, highlight); move them to the word they mark.
- For long clips, also cut a few full-page type moments (remove the card for a sentence by giving that layout a zero-size rect, or end it early).
- Element types and fields: `CORE/references/plan-schema.md`, `CORE/references/motion.md`.

## Check before delivering

- Contact sheet: text readable, nothing cut off, nothing over the face, safe zones (10-85% of the height, clear of the right 12% in 9:16).
- Overlays land with the spoken word, not after it.
- `qc.py` with 0 FAIL. Tell the user what was cut, the look, and where the file is.

## Example requests

- "Editorial explainer with my clip in cards and big words."
- "Make it look like a magazine page with hand-drawn circles."
