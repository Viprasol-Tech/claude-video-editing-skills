# plan.json reference

`make_plan.py` writes a first draft. Claude edits it, then runs `render.py` and `finish.py`.
All times are in seconds on the **cut** timeline (after autocut). All positions are output pixels:
`x`,`y` is the anchor point (default centre of frame); `anchor` can be `center`, `top`, `bottom`,
`left`, `right`, `top-left` and so on.

```json
{
  "output": {"width": 1080, "height": 1920, "fps": 30, "duration": 18.4, "background": "black"},
  "source": "cut.mp4",              // speaker video, relative to the plan file. null for no speaker
  "matte": "matte.mp4",             // person mask from matte.py, needed for layer "behind"
  "speaker": {
    "mode": "full",                 // full | panel | none
    "rect": [60, 980, 960, 860],    // panel only: x, y, w, h
    "radius": 48,                   // rounded corners (panel)
    "focusX": 0.5, "focusY": 0.35,  // which part of a wider source to keep when cropping
    "push": 0.04,                   // slow push-in over the whole video (0.04 = +4%)
    "mirror": false,
    "zooms": [{"start": 2.1, "end": 3.4, "scale": 1.15, "snap": false}]
  },
  "theme": {"vars": {"--c-accent": "#FFE14D"}, "fontsUrl": "https://fonts.googleapis.com/...", "cssFiles": ["/abs/theme.css"], "css": ""},
  "words": [{"w": "Hello", "start": 0.2, "end": 0.5}],
  "clips": [{"id": "rec", "src": "screen.mp4", "start": 0, "end": 12, "loop": false}],
  "cutaways": [{"src": "broll.mp4", "start": 4.0, "end": 6.5, "srcStart": 10}],
  "elements": [ ... ],
  "sfx": [{"t": 1.2, "kind": "pop", "gain": 0.5}],
  "music": {"src": "music.mp3", "volume": 0.12, "duck": true, "start": 0, "fadeOut": 1.5},
  "finish": {"grade": "warm", "grain": 6, "vignette": true, "letterbox": 0, "sharpen": false, "lut": null},
  "outputFile": "final.mp4"
}
```

## Layers (stacking order, back to front)

1. `bg`: opaque HTML background (only when an element uses it)
2. speaker video (full frame or panel)
3. `behind`: HTML drawn **behind the person** (needs `matte`)
4. person cut-out (from `matte`)
5. `cutaways`: full-frame B-roll video
6. `front`: captions, cards, everything on top

## Shared element fields

| field | meaning |
| --- | --- |
| `type` | component name (below) |
| `layer` | `bg`, `behind` or `front` |
| `start`, `end` | visible window |
| `x`, `y`, `w`, `h`, `anchor`, `rotate`, `z` | placement |
| `in`, `out` | `fade` `pop` `bounce` `rise` `drop` `slideLeft` `slideRight` `scale` `zoomIn` `blur` `spin` `wipe` `wipeUp` `stamp` `flip` `glitch` `none` |
| `inDur`, `outDur` | seconds (default 0.35 / 0.25) |
| `float`, `drift`, `wobble` | idle motion: bob in px, scale growth per second, rotation wobble in degrees |
| `className` | extra CSS classes (themes style them) |
| `style` | inline CSS object, e.g. `{"fontSize": "120px", "color": "#fff"}` |

## Components

| type | key fields |
| --- | --- |
| `captions` | `mode` (`karaoke` all words shown, active highlighted · `reveal` words appear as spoken · `single` one word at a time), `maxWords`, `maxChars`, `y`, `w`, `uppercase`, `lowercase`, `wordIn`, `activeScale`, `keywords` (list of words coloured with accent 2), `hold`. Class presets: `cap-pill`, `cap-box`, `cap-outline`, `cap-soft`, `cap-dim` |
| `text` / `headline` / `chip` / `tile` / `sticker` | `text`, `split` (`words`/`chars` for kinetic type) with `stagger`, `unitIn`, `unitDur`; `fit: true` shrinks to fit `w` (default on for `headline`); `wrap` |
| `card` | `kicker`, `title`, `body`, `items` (strings or `{text, at}`), `numbered`, `marker`, `image`, `clip`, `itemStagger`. Classes `glass`, `paper` |
| `clip` | `clip` (id from `clips`), `device` (`phone` `laptop` `browser`), `motion` (`flyIn` `tilt` `float` `kenburns` `orbit`), `clipOffset`, `image` (a still instead of a clip) |
| `image` | `image`, same motions as clip |
| `counter` | `from`, `to`, `prefix`, `suffix`, `decimals`, `label`, `countDur` |
| `bars` | `title`, `items` `[{label, value, highlight}]`, `max`, `prefix`, `suffix` |
| `lowerthird` | `name`, `role` |
| `titlecard` | `kicker`, `title`, `subtitle` (full frame) |
| `shape` | `kind`: `ring` `glow` `orbit` `ribbon` `rays` `burst` `grid` `blob` `sparkles` `bubbles` `confetti` `halftone` `spotlight` `frame` `bar`; `color`, `color2`, `speed`, `count`, `thickness`, `pulseOn` (times to pulse) |
| `scribble` | `kind`: `circle` `underline` `arrow` `box` `cross` `check` `highlight` `zigzag`; `color`, `strokeWidth`, `drawDur` |
| `progress` | `position` (`top`/`bottom`) |
| `background` | `kind`: `solid` `gradient` `mesh` `paper` `grid` `dots`; `image` |
| `burst` | `chars` (emoji), `count`, `radius` |
| `ticker` | `label`, `text`, `y`, `speed` |
| `rec` | camcorder REC dot + timecode, `date` |
| `flash` | `times` list, `color`, `opacity`, `dur` |
| `compare` | `before`, `after` images, labels, `wipeDelay`, `wipeDur`, `wipeTo` |
| `equalizer` | fake audio bars that move while someone speaks |
| `stars` | rating stars (only for real reviews the user supplies) |

## Tips

- Check the look before a full render: `render.py plan.json --frames 1,4,8,12` writes `contact_sheet.png`. Look at it.
- Keep text out of the bottom 15% and top 10% of a 9:16 frame (platform buttons cover them).
- Change one thing, preview, repeat. A full render of 30 s at 1080x1920 takes about 1–3 minutes.
