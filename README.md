# Claude Video Editing Skills (Video Studio)

40 free Claude skills that turn a raw clip into a finished, styled video edit, all on your own computer.
Every skill is one look (captions, jump cuts, text behind the speaker, cards, charts, sound, grade).
They all share one engine: **video-studio-core**.

Free and open source (MIT). No account, no watermark, no credits.

## What you need

- Claude Code (or Cowork on desktop) with skills enabled
- Python 3.10+, FFmpeg
- `pip install faster-whisper playwright numpy pillow mediapipe` then `python -m playwright install chromium`

## Install

**Option A: download and run the installer** (copies the skills to `~/.claude/skills`)

```bash
git clone https://github.com/Viprasol-Tech/claude-video-editing-skills
cd claude-video-editing-skills
```

```bash
bash install.sh                                          # macOS / Linux
powershell -ExecutionPolicy Bypass -File install.ps1     # Windows
```

**Option B: Claude Code plugin marketplace**

```
/plugin marketplace add Viprasol-Tech/claude-video-editing-skills
/plugin install video-studio@claude-video-editing-skills
```

**Option C: by hand.** Copy any skill folders from `plugins/video-studio/skills/` into `~/.claude/skills/`.
Always copy `video-studio-core` too: every style needs it.

Then check your setup: `python ~/.claude/skills/video-studio-core/scripts/check_env.py`

## Use

Put a clip in a folder, open Claude there and ask, naming a style:

> Edit `clip.mp4` with **halo-cut**. Cut every pause, hook should be "I quit my job for this".

> Find the 6 best moments in `podcast.mp4` with **clip-miner** and make shorts.

> Make a 12-second **device-fly** promo from `screen.mp4`, tagline "Trade smarter".

Claude transcribes, cuts, drafts a plan, checks stills, renders and finishes. You get `final.mp4`.

## The 10 priority skills

| Skill | Type | Look | Format |
| --- | --- | --- | --- |
| `halo-cut` | Talking-head reel | Clean premium reel: tight jump cuts, word-by-word captions, zoom punches on key words. | 9:16 |
| `depth-type` | Talking-head reel | A giant one-word headline sits behind the speaker's head and changes with every sentence. | 9:16 |
| `split-proof` | Talking-head reel | Speaker in the bottom half, proof in the top half: a new card, number, image or clip for every claim. | 9:16 |
| `essay-mode` | YouTube explainer | Video-essay explainer: paper textures, highlighter marks, serif headings, a chart or card every 8-10 s. | 16:9 |
| `device-fly` | Product / app promo | Your screen recording on a 3D phone (or laptop) that flies in over a moving gradient, with kinetic titles. | 9:16 |
| `clip-miner` | Podcast / repurposing | Finds the best 20-60 s moments in a long video and turns each into a captioned vertical short. | 9:16 |
| `neon-orbit` | Talking-head reel | A glowing cyan ring and orbiting lights behind the speaker's head, neon captions, night-time grade. | 9:16 |
| `data-story` | Explainer | Analyst look: every number becomes an animated counter or bar chart beside the speaker on a dark grid. | 16:9 |
| `pod-frame` | Podcast / repurposing | Podcast edit: auto camera switching by who is talking, name cards, quote pulls and a live audio bar. | 16:9 |
| `kinetic-launch` | Product / app promo | Type-only motion piece: bold words slam in one after another in sync with the beat or voiceover. | 9:16 |

## 30 more styles

| Skill | Type | Look | Format |
| --- | --- | --- | --- |
| `paper-cut` | Talking-head reel | Handmade scrapbook look: taped paper captions, tilted stickers on key words, marker arrows. | 9:16 |
| `chaos-stack` | Talking-head reel | Sensory-overload 'brainrot' edit: one huge word at a time, snap zooms every second, flashes and emoji bursts. | 9:16 |
| `whiteboard-host` | YouTube explainer | Teacher layout: speaker in a panel on the left, notes appear in marker handwriting on a paper board on the right. | 16:9 |
| `chapter-pro` | YouTube explainer | Long-form YouTube polish: chapter title cards, lower thirds, subtle captions, list cards and an end screen. | 16:9 |
| `ugc-ad-kit` | Product / app promo | Native-looking ad: selfie footage, TikTok-style text hook, product callout cards and a strong end card. | 9:16 |
| `logo-sting` | Product / app promo | A 3-6 second logo reveal with light rays, a ring burst and the brand name typing in underneath. | 16:9 |
| `quote-card-reel` | Podcast / repurposing | Calm pull-quote reel: the speaker darkened behind, each sentence set as large serif typography. | 4:5 |
| `dual-subs` | Talking-head reel | Two-language captions: the original word-by-word on top, a translated line underneath, both readable. | 9:16 |
| `bold-bounce` | Talking-head reel | High-energy business captions: two huge words at a time bouncing in, green and yellow highlights, emoji hits. | 9:16 |
| `minimal-mono` | Talking-head reel | Quiet and premium: small lowercase captions, slow push-in, faded film tone. Nothing else. | 9:16 |
| `frame-studio` | Talking-head reel | Magazine layout: the speaker framed in a rounded panel on a cream page with an editorial headline and serif captions. | 9:16 |
| `vhs-tape` | Talking-head reel | 1990s camcorder: REC dot and timecode, colour bleed, tape noise, chunky yellow subtitles. | 9:16 |
| `y2k-chrome` | Talking-head reel | Glossy Y2K: chrome bubble words behind the speaker, sparkles, pastel pill captions. | 9:16 |
| `news-desk` | Talking-head reel | Broadcast news look: breaking-news lower third, scrolling ticker, LIVE chip and boxed captions. | 9:16 |
| `doc-real` | Talking-head reel | Documentary realism: letterboxed frame, film grade, small lowercase subtitles and a location tag. | 9:16 |
| `cinematic-phone` | Talking-head reel | Phone footage graded like film: wide letterbox, teal-orange tone, a serif title card and quiet subtitles. | 9:16 |
| `sticker-pop` | Talking-head reel | Playful: key words stamp in as die-cut stickers around the speaker with emoji bursts and pops. | 9:16 |
| `terminal-tech` | Talking-head reel | Developer look: captions typed into a terminal window, code-comment key words, green-on-black. | 9:16 |
| `comic-panel` | Talking-head reel | Comic-book edit: speech-bubble captions, halftone dots, POW/BAM stamps on punchlines. | 9:16 |
| `swiss-poster` | Talking-head reel | International typographic style: huge left-aligned black/red type behind the speaker on a strict grid, red bar accent. | 9:16 |
| `soft-gradient` | Talking-head reel | Airy wellness look: speaker in a big rounded frame on a slowly moving pastel gradient, glassy word chips. | 9:16 |
| `highlighter-study` | YouTube explainer | Study-notes look: key words in the captions get a yellow highlighter swipe, notes cards pop up for definitions and lists. | 9:16 |
| `countdown-list` | Talking-head reel | Top-N countdown: a big rank number stamps in for each item with its name in a banner beside it. | 9:16 |
| `before-after` | Talking-head reel | Transformation edit: a wipe slider reveals the 'after' over the 'before', with labels and a ding on the reveal. | 9:16 |
| `tutorial-steps` | YouTube explainer | Screen tutorial: your screen recording fills the frame, your face in a round bubble, numbered step banners. | 16:9 |
| `testimonial-card` | Product / app promo | A real customer quote shown as a clean card: avatar, stars, the quote typing in word by word, name and role. | 4:5 |
| `event-promo` | Product / app promo | Announcement promo: event name in kinetic type, date and place chips, countdown-style energy, ticket CTA. | 9:16 |
| `product-spotlight` | Product / app promo | Studio product shot: your product image floats on a spotlight, feature callouts draw in with arrows. | 9:16 |
| `loop-ambient` | Product / app promo | Seamless looping visual: drifting gradient, morphing blob and moving bars behind a short quote or track title. | 1:1 |
| `hook-lab` | Talking-head reel | Makes the first 3 seconds impossible to scroll past: freeze-flash, snap zoom, red circle, 'wait for it' tag, then a clean edit. | 9:16 |

## How it works

1. `prep` normalises the clip (30 fps, upright).
2. `transcribe` gets word timestamps with faster-whisper (local, free).
3. `autocut` removes pauses, filler words and retakes.
4. `matte` cuts out the speaker (for text behind the head).
5. `make_plan` drafts a `plan.json` from the transcript and the style; Claude refines it.
6. `render` draws the HTML overlays frame by frame in headless Chromium and composites with FFmpeg.
7. `finish` adds grade, grain, sound effects, ducked music and -14 LUFS loudness.

Make your own style: copy any style folder, rename it (folder name = `name:` in SKILL.md), and change `theme.json` and `theme.css`.
References: `video-studio-core/references/plan-schema.md` and `theme-schema.md`.

## Notes

- First transcription downloads the Whisper model (~460 MB for `small`). The person-cut-out model (~16 MB) downloads on first use.
- Google Fonts load from the internet; offline, fallback fonts are used.
- Only use music, footage and reviews you have the rights to. `testimonial-card` is for real reviews only.

License: MIT. See `LICENSE`.
