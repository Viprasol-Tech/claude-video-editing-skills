---
name: neon-marquee
description: "Neon Marquee video-editing style for Claude: A huge glowing electric-blue headline scrolls sideways behind your head on every sentence; compact caption chips with the key word in a blue italic box, lime labels and punch-ins. Use for podcast clips, interviews, tech, news and bold opinion reels. Turns a raw talking clip into a finished 9:16 edit with the video-studio-core engine (transcribe, auto-cut, motion graphics, sound, grade)."
license: MIT
---

# Neon Marquee

A huge glowing electric-blue headline scrolls sideways behind your head on every sentence; compact caption chips with the key word in a blue italic box, lime labels and punch-ins.

- **Best for:** podcast clips, interviews, tech, news and bold opinion reels
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
python CORE/scripts/run.py clip.mp4 --style STYLE --work edit-neon-marquee --stop-after plan
# refine edit-neon-marquee/plan.json (see below), then check stills:
python CORE/scripts/render.py edit-neon-marquee/plan.json --frames 1,3,6,9
python CORE/scripts/render.py edit-neon-marquee/plan.json
python CORE/scripts/finish.py edit-neon-marquee/plan.json --platform reels
python CORE/scripts/qc.py edit-neon-marquee/final.mp4 --plan edit-neon-marquee/plan.json
```

Open `contact_sheet.png` and look at it before the full render. Pass `--title "..."` to `run.py` / `make_plan.py` for the title line.

## The look

- Your real shot stays; a giant neon-blue headline (the sentence's key words, repeated) slides sideways behind your head.
- Captions: 2-3 words in a black chip; the key word sits in a blue box in italic serif.
- Key words also flash a lime label and a snap punch-in. Dark film grade.

## Refine the plan

- Read `words.json`, fix mis-heard words (keep their times) and rewrite the hook.
- Replace weak auto-picked key words and headlines with the words that carry the meaning.
- Keep the marquee at forehead height (`y`); check a still - the head should cover part of it.
- Marquee speed: the `keys.tx` pair on each `headline` (px moved over the sentence).
- Use real names/claims for the lime labels only when they are said in the clip.
- Element types and fields: `CORE/references/plan-schema.md`, `CORE/references/motion.md`.

## Check before delivering

- Contact sheet: text readable, nothing cut off, nothing over the face, safe zones (10-85% of the height, clear of the right 12% in 9:16).
- Overlays land with the spoken word, not after it.
- `qc.py` with 0 FAIL. Tell the user what was cut, the look, and where the file is.

## Example requests

- "Podcast clip with big blue scrolling text behind the guest."
- "Neon headline behind my head, punchy captions."
