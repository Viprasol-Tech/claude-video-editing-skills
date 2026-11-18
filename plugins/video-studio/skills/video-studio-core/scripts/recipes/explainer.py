#!/usr/bin/env python3
"""Explainer scene recipe (editorial-cards skin): a designed editorial explainer on a cream paper page.

  sequence.py PLAN --recipe explainer          (self-check: python recipes/explainer.py)

One scene per phrase, cycling four treatments, with calm soft cuts between them:
  card-low   - small grey kicker ("01 / 04") and a big black headline at the top whose words write on as they are
               spoken, the key word in coral italic serif with a hand-drawn underline; the footage below in a tilted,
               white-framed rounded card.
  type       - no footage: kicker and bigger type mid-page; a coral hand-drawn circle draws round the key word as it
               is said.
  card-blank - the card top-right; below it the phrase in light grey that darkens as it is read, the key word a
               "_ _ _" blank that fills in coral when it is said.
  card-high  - headline at the top, a yellow highlighter swipes the key word; the card lower-left with a coral arrow
               pointing at it and a snap punch-in on the key word.
Phrase 1 always shows the footage; a phrase shorter than MIN_TYPE s never becomes a type scene (no time to read).
Key word = the longest of the phrase's last three words, skipping refrains (words heard in 2+ phrases, e.g. "बरगी").
The skin supplies the paper, fonts and the word effects (theme.css .ed-h / .ed-ul / .ed-circ / .ed-blank / .ed-hl);
this script writes the timed elements, speaker.layouts (the footage cards), softCuts, zooms and sfx. Everything it
writes carries "_seq": true and is replaced on a re-run; speaker.layouts and the skin's auto captions and key-word
marks (ed-key / ed-mark) are replaced too, so hand-made layouts must be redone after a re-run.
"""
import os, sys, unicodedata
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sequence import phrases, bare, esc   # noqa: E402
from vs_common import norm, log   # noqa: E402

LEAD = 0.12      # s: a scene starts this long before its first word
MIN_TYPE = 1.2   # s: a type-only scene needs time to be read
LH = 1.3         # headline line-height (room for Devanagari matras; theme.css .ed-h uses the same)
BOX = 0.8        # headline box width (fraction of W): left edge 0.08 W, clear of the right 12 % icon rail
# card = rectFrac [x, y, w, h] of the footage (None: type only), rot = tilt (deg), top / mid = where the headline block
# starts / is centred (fraction of H), fs = base font px at 1080 wide, lines = most lines before the font shrinks
SCENES = [
    {"kind": "card-low", "card": [0.17, 0.42, 0.62, 0.36], "rot": -3, "top": 0.155, "fs": 96, "lines": 3, "fx": "ed-ul", "sfx": "ui-tap"},
    {"kind": "type", "card": None, "mid": 0.46, "fs": 124, "lines": 4, "fx": "ed-circ", "sfx": "swish"},
    {"kind": "card-blank", "card": [0.30, 0.115, 0.56, 0.34], "rot": 3, "top": 0.545, "fs": 96, "lines": 3, "fx": "ed-blank", "sfx": "pop"},
    {"kind": "card-high", "card": [0.10, 0.44, 0.58, 0.36], "rot": -2, "top": 0.155, "fs": 96, "lines": 3, "fx": "ed-hl", "sfx": "swish"},
]
SKIN_AUTO = ("ed-key", "ed-mark")   # the skin's auto key-word text + scribble (make_plan): replaced by the scenes


def key_of(words, idx, refrain):
    cand = [i for i in idx if norm(bare(words[i]["w"])) not in refrain] or idx
    return max(cand[-3:], key=lambda i: (len(bare(words[i]["w"])), i))   # ties go to the later word


def fit(texts, key, fs, box_w, max_lines):
    """Biggest font (fs down to 58 %) whose estimated wrap of texts fits max_lines -> (font px, lines).
    Width estimate: ~0.58 em per visible character (combining marks take no width); the key word is set 1.12x in
    serif with ~0.7 em of padding for its mark."""
    for f in (fs, fs * 0.88, fs * 0.76, fs * 0.66, fs * 0.58):
        lines, cur = 1, 0.0
        for j, t in enumerate(texts):
            wd = sum(unicodedata.category(c) != "Mn" for c in t) * 0.58 * f
            if j == key:
                wd = wd * 1.12 + 0.7 * f
            if cur and cur + 0.24 * f + wd > box_w:
                lines, cur = lines + 1, wd
            else:
                cur += (0.24 * f if cur else 0) + wd
        if lines <= max_lines:
            break
    return f, lines


def build(plan, a):
    W, H = plan["output"]["width"], plan["output"]["height"]
    if W > H:
        sys.exit("explainer: the card layouts are designed for portrait or square frames (9:16, 4:5, 1:1)")
    if not plan.get("source"):
        sys.exit("explainer: the plan has no speaker video (source) - the cards show that footage")
    dur = plan["output"]["duration"]
    u = W / 1080
    words = [w for w in plan["words"] if w.get("w", "").strip()]
    P = phrases(words)
    seen = Counter(key for idx in P for key in {norm(bare(words[i]["w"])) for i in idx})
    refrain = {key for key, c in seen.items() if c > 1}
    els, layouts, cuts, sfx, zooms = [], [], [], [], []
    for n, idx in enumerate(P):
        s = 0.0 if n == 0 else round(words[idx[0]]["start"] - LEAD, 3)
        last = n + 1 == len(P)
        e = dur if last else round(words[P[n + 1][0]]["start"] - LEAD, 3)
        sc = SCENES[n % len(SCENES)]
        if sc["card"] is None and e - s < MIN_TYPE:
            sc = SCENES[2]
        k = key_of(words, idx, refrain)
        tk = round(words[k]["start"], 3)
        fs, lines = fit([bare(words[i]["w"]) for i in idx], idx.index(k), sc["fs"] * u, BOX * W, sc["lines"])
        block = lines * fs * LH
        top = sc["mid"] * H - block / 2 if sc["card"] is None else sc["top"] * H
        if n:   # scene change: soft blur + a quiet whoosh
            cuts.append(s)
            sfx.append({"t": round(s - 0.1, 3), "kind": "whoosh-short", "gain": 0.16})
        if not sc["card"]:   # type only: a front paper page covers the footage. The previous card runs on under it,
            layouts[-1]["end"] = e   # because a gap in speaker.layouts breaks render.py's single-frame stills
            els.append({"type": "background", "layer": "front", "kind": "paper", "className": "ed-bg", "decor": True,
                        "start": s, "end": e})
        els.append({"type": "text", "className": "ed-kick", "text": f"{n + 1:02d} / {len(P):02d}", "anchor": "left",
                    "x": round(W * 0.08), "y": round(top - 0.024 * H), "start": round(s + 0.05, 3), "end": e,
                    "in": {"name": "maskUp", "dur": 0.45}, "out": "none"})
        # the headline: one caption group for the whole phrase, held to the scene end; mode "fill" writes each word on
        # as it is spoken (the skin hides the base word), so the block never reflows
        els.append({"type": "captions", "className": f"ed-h {sc['fx']}", "mode": "fill", "words": [words[i] for i in idx],
                    "keywords": [bare(words[k]["w"])], "maxWords": 12, "maxChars": 60, "breakGap": 9, "breakOnPunct": False,
                    "cpsMax": 0, "hold": round(e - words[idx[-1]]["end"], 3),   # group ends exactly at the cut
                    "x": round(W * (0.08 + BOX / 2)), "y": round(top + block / 2), "w": round(W * BOX),
                    "style": {"fontSize": f"{fs:.0f}px"}, "start": s, "end": e})
        sfx.append({"t": tk, "kind": sc["sfx"], "gain": 0.2})
        if not sc["card"]:
            continue
        # the footage card (render.py speaker.layouts) on a white print frame with a soft shadow (bg layer, under it)
        x, y, w, h = sc["card"]
        r = [int(x * W), int(y * H), int(w * W) // 2 * 2, int(h * H) // 2 * 2]
        ce = round(dur + 1, 3) if last else e   # the last card holds past the end: never a bare page in the final frame
        layouts.append({"start": s, "end": ce, "rect": r, "radius": round(34 * u), "rot": sc["rot"]})
        b = round(14 * u)
        els.append({"type": "text", "layer": "bg", "decor": True, "className": "ed-frame", "text": "",
                    "x": r[0] + r[2] // 2, "y": r[1] + r[3] // 2, "w": r[2] + 2 * b, "h": r[3] + 2 * b,
                    "start": s, "end": ce, "in": "none", "out": "none", "keys": {"r": [[0, sc["rot"]]]}})
        if sc["kind"] == "card-high":   # a coral arrow points at the card; the card punches in on the key word
            els.append({"type": "scribble", "kind": "arrow", "decor": True, "className": "ed-arrow", "color": "#E4572E",
                        "strokeWidth": 7, "x": round(W * (x + w + 0.11)), "y": round(H * (y + 0.07)), "w": round(W * 0.15),
                        "h": round(W * 0.15), "start": tk, "end": e, "drawDur": 0.5, "keys": {"r": [[0, 196]]}})
            zooms.append({"start": tk, "end": ce, "scale": 1.1, "snap": True})

    for x in els:
        x["_seq"] = True
    keep = [x for x in plan.get("elements", []) if not x.get("_seq") and x.get("type") != "captions"
            and not any(c in str(x.get("className", "")).split() for c in SKIN_AUTO)]
    plan["elements"] = keep + els
    spk = plan.setdefault("speaker", {})
    spk["layouts"] = [dict(lo, _seq=True) for lo in layouts]
    spk["zooms"] = [z for z in spk.get("zooms", []) if not z.get("_seq")] + [dict(z, _seq=True) for z in zooms]
    plan["softCuts"] = [{"at": c, "dur": 0.3, "sigma": 12} for c in cuts]
    plan["sfx"] = [x for x in plan.get("sfx", []) if not x.get("_seq")] + [dict(x, _seq=True) for x in sfx]
    log(f"explainer sequence: {len(P)} phrases, {len(layouts)} card scenes, {len(P) - len(layouts)} type scenes, "
        f"{len(cuts)} scene changes, {len(els)} elements")
    return plan


if __name__ == "__main__":   # self-check on the skin-test shayari timings (refrain "बरगी" must not become the key word)
    T = [("हर", 0.0, .28), ("बात", .3, .72), ("तीरा", .76, 1.31), ("बरगी,", 1.36, 2.06), ("राशि", 2.7, 3.19), ("है", 3.23, 3.47),
         ("फकीरा", 3.5, 4.11), ("बरगी,", 4.16, 4.77), ("एक", 5.14, 5.35), ("ए", 5.37, 5.47), ("छोरी", 5.48, 5.9), ("लाइफ", 5.93, 6.35),
         ("में", 6.39, 6.7), ("भाई,", 6.73, 7.14), ("वा", 7.5, 7.66), ("भी", 7.68, 7.84), ("जमा", 7.86, 8.1), ("हीरा", 8.12, 8.45),
         ("बरगी,", 8.48, 8.88)]
    base = {"output": {"width": 1080, "height": 1920, "duration": 9.7}, "source": "cut.mp4",
            "speaker": {"mode": "panel", "layouts": [{"start": 0, "end": 9.7, "rect": [0, 0, 10, 10]}], "zooms": [{"start": 1, "end": 2, "scale": 1.2}]},
            "words": [{"w": w, "start": s, "end": e} for w, s, e in T],
            "elements": [{"type": "background", "className": "ed-bg"}, {"type": "captions"},
                         {"type": "text", "className": "ed-key"}, {"type": "scribble", "className": "ed-mark"}]}
    import copy
    plan = build(copy.deepcopy(base), None)
    caps = [x for x in plan["elements"] if x["type"] == "captions"]
    assert [c["className"].split()[1] for c in caps] == ["ed-ul", "ed-circ", "ed-blank", "ed-hl"], caps
    assert [c["keywords"][0] for c in caps] == ["तीरा", "फकीरा", "लाइफ", "हीरा"]        # never the refrain "बरगी"
    assert [round(c["words"][-1]["end"] + c["hold"], 3) for c in caps] == [2.58, 5.02, 7.38, 9.7]   # held to the cut
    lo = plan["speaker"]["layouts"]
    assert [(x["start"], x["end"]) for x in lo] == [(0.0, 5.02), (5.02, 7.38), (7.38, 10.7)]   # card 1 runs on under the type page
    assert [(x["start"], x["end"]) for x in plan["elements"] if x["type"] == "background" and x.get("_seq")] == [(2.58, 5.02)]
    assert [c["at"] for c in plan["softCuts"]] == [2.58, 5.02, 7.38]
    assert [z["scale"] for z in plan["speaker"]["zooms"]] == [1.2, 1.1]                 # user zoom kept, one punch-in added
    assert plan["elements"][0]["className"] == "ed-bg" and len(plan["elements"]) == 1 + 4 + 4 + 3 + 1 + 1
    assert all(x.get("_seq") for x in plan["elements"][1:])
    n1, s1 = len(plan["elements"]), len(plan["sfx"])
    plan = build(plan, None)                                                            # re-run replaces, never stacks
    assert len(plan["elements"]) == n1 and len(plan["sfx"]) == s1 and len(plan["speaker"]["layouts"]) == 3
    assert len(plan["speaker"]["zooms"]) == 2
    # a phrase too short to read as type-only stays on a card
    short = copy.deepcopy(base)
    short["words"] = short["words"][:4] + [{"w": "हाँ.", "start": 2.7, "end": 3.0}, {"w": "फकीरा", "start": 3.5, "end": 4.1}]
    short["output"]["duration"] = 4.6
    p2 = build(short, None)
    assert [c["className"].split()[1] for c in p2["elements"] if c["type"] == "captions"] == ["ed-ul", "ed-blank", "ed-blank"]
    # long phrases shrink the type instead of overflowing
    assert fit(["word"] * 3, 0, 96, 864, 3)[0] == 96 and fit(["longerword"] * 14, 0, 96, 864, 3)[0] < 96
    print("explainer self-check ok")
