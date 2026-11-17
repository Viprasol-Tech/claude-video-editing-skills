#!/usr/bin/env python3
"""Automated QC of a finished video (+ its plan) against a platform spec. Writes JSON + Markdown.

usage: qc.py VIDEO [--plan PLAN.json] [--platform reels|youtube|...|none] [--out-dir DIR] [--kids] [--strict]

Checks: duration/resolution/fps vs plan, codec/pix_fmt, faststart, keyframe interval, audio present,
integrated LUFS / true peak / LRA vs platform target, silences > 2 s, black frames, flash frames,
photosensitivity (>= 3 flashes in any 1 s), illegal levels (signalstats BRNG), A/V sync heuristic,
caption rules (broadcast cues from words; creator captions; overlay min 0.6 s; 9:16 safe zone
10-85 % height and clear of the right 12 %; <= 2 overlays at once on vertical), size/length limits.
Exit code: 0, or 1 with --strict when any check FAILs.
"""
import argparse, json, os, re, shutil, struct, subprocess, sys, tempfile
from vs_common import load_json, save_json, log
import captions as C
from deliver import PRESETS, stream_info

TEXT_TYPES = {"text", "headline", "chip", "tile", "sticker", "card", "counter", "bars", "lowerthird", "titlecard",
              "captions", "ticker", "compare", "clip", "image", "stars"}
FLASH_DELTA = 0.10        # 10 % of the luma range between frames = a transition
GLITCH_DELTA = 0.20


def mp4_atoms(path):
    """Top-level MP4 boxes in file order, e.g. ['ftyp', 'moov', 'mdat'] (faststart = moov before mdat)."""
    out = []
    with open(path, "rb") as f:
        size_total = os.path.getsize(path); pos = 0
        while pos + 8 <= size_total:
            f.seek(pos)
            size, typ = struct.unpack(">I4s", f.read(8))
            if size == 1:
                size = struct.unpack(">Q", f.read(8))[0]
            elif size == 0:
                size = size_total - pos
            out.append(typ.decode("latin-1"))
            if size < 8:
                break
            pos += size
    return out


def keyframe_interval(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time,flags",
                          "-of", "csv=p=0", path], stdout=subprocess.PIPE, text=True).stdout
    ts = sorted(float(l.split(",")[0]) for l in out.splitlines() if "K" in l.split(",")[-1] and l.split(",")[0] not in ("", "N/A"))
    gaps = [round(b - a, 3) for a, b in zip(ts, ts[1:])]
    return {"keyframes": len(ts), "max_gap_s": max(gaps) if gaps else None, "min_gap_s": min(gaps) if gaps else None}


def analyse(path, has_audio):
    """One decode pass: blackdetect + signalstats (per-frame YAVG/BRNG) + silencedetect + ebur128."""
    d = tempfile.mkdtemp()
    g = "[0:v]blackdetect=d=0.1:pix_th=0.10,signalstats=stat=brng,metadata=mode=print:file=stats.txt[vo]"
    maps = ["-map", "[vo]"]
    if has_audio:
        g += ";[0:a]silencedetect=n=-45dB:d=2,ebur128=peak=true:framelog=quiet[ao]"
        maps += ["-map", "[ao]"]
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", os.path.abspath(path), "-filter_complex", g] + maps + ["-f", "null", "-"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=d, encoding="utf-8", errors="replace")
    err = p.stderr
    yavg, brng = [], []
    if os.path.exists(os.path.join(d, "stats.txt")):
        for line in open(os.path.join(d, "stats.txt"), encoding="utf-8"):
            if "signalstats.YAVG=" in line:
                yavg.append(float(line.split("=")[1]))
            elif "signalstats.BRNG=" in line:
                brng.append(float(line.split("=")[1]))
    shutil.rmtree(d, ignore_errors=True)
    blacks = [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", err)]
    sil = [(float(a), float(b)) for a, b in re.findall(r"silence_start: ([\d.]+)[\s\S]*?silence_end: ([\d.]+)", err)]
    loud = {}
    summ = err[err.rfind("Summary:"):] if "Summary:" in err else ""
    for k, pat in (("I", r"I:\s+(-?[\d.]+|-inf) LUFS"), ("LRA", r"LRA:\s+(-?[\d.]+) LU"), ("TP", r"Peak:\s+(-?[\d.]+|-inf) dBFS")):
        m = re.search(pat, summ)
        if m:
            loud[k] = float(m[1].replace("-inf", "-99"))
    return {"yavg": yavg, "brng": brng, "black": blacks, "silence": sil, "loudness": loud, "ok": p.returncode == 0}


def flash_analysis(yavg, fps, maxval=255.0):
    """Flash frames (single-frame luma spikes) and Harding-style flash rate (pairs of opposing
    >= 10 % luma transitions). ponytail: frame-average luma only; misses small-area / red flashes."""
    y = [v / maxval for v in yavg]
    glitches = [i for i in range(1, len(y) - 1)
                if abs(y[i] - y[i - 1]) > GLITCH_DELTA and abs(y[i] - y[i + 1]) > GLITCH_DELTA and (y[i] - y[i - 1]) * (y[i + 1] - y[i]) < 0]
    trans, last_sign = [], 0
    for i in range(1, len(y)):
        dlt = y[i] - y[i - 1]
        if abs(dlt) >= FLASH_DELTA:
            s = 1 if dlt > 0 else -1
            if s != last_sign:
                trans.append(i); last_sign = s
    win = int(round(fps))
    worst, at = 0, None
    for k, i in enumerate(trans):
        n = sum(1 for j in trans[k:] if j - i < win) // 2     # a flash = an opposing pair
        if n > worst:
            worst, at = n, i / fps
    return {"flash_frames": [round(i / fps, 3) for i in glitches], "max_flashes_per_s": worst, "at": at}


# ------------------------------------------------------------------ plan / caption checks
def creator_caption_chunks(el, words):
    """Mirror runtime/engine.js C.captions grouping exactly (maxWords/maxChars/breakGap/punctuation, hold,
    cpsMax splitting) so QC judges what is actually on screen."""
    import re
    ws = [w for w in words if str(w.get("w", "")).strip()]
    max_words, max_chars = int(el.get("maxWords") or 3), int(el.get("maxChars") or 22)
    gap, hold = float(el.get("breakGap") or 0.45), float(el.get("hold", 0.5))
    punct = re.compile(r"[.!?]$" if el.get("breakOnPunct") == "sentence" else r"[.!?,;:]$")
    groups, cur = [], []
    for i, w in enumerate(ws):
        chars = sum(len(b["w"]) + 1 for b in cur) + len(w["w"])
        if cur and (len(cur) >= max_words or chars > max_chars or (i and w["start"] - ws[i - 1]["end"] > gap)):
            groups.append(cur); cur = []
        cur.append(w)
        if el.get("breakOnPunct", True) is not False and punct.search(w["w"].strip()):
            groups.append(cur); cur = []
    if cur:
        groups.append(cur)

    def timed(gs):
        return [(g, g[0]["start"], min(g[-1]["end"] + hold, gs[k + 1][0]["start"] if k + 1 < len(gs) else 1e9))
                for k, g in enumerate(gs)]
    cps_max, min_dur = float(el.get("cpsMax", 20) or 0), float(el.get("minDur", 0.3))
    for _ in range(4 if cps_max > 0 else 0):
        out, changed = [], False
        for g, s, e in timed(groups):
            chars = sum(len(w["w"].strip()) for w in g) + len(g) - 1
            m = (len(g) + 1) // 2
            if len(g) > 1 and chars / max(0.05, e - s) > cps_max and g[m]["start"] - s >= min_dur and e - g[m]["start"] >= min_dur:
                out += [g[:m], g[m:]]; changed = True
            else:
                out.append(g)
        groups = out
        if not changed:
            break
    res = []
    for g, s, e in timed(groups):
        text = " ".join(w["w"].strip() for w in g)
        res.append({"start": s, "dur": max(1e-3, e - s), "text": text.upper() if el.get("uppercase") else text})
    return res


def overlay_checks(plan, W, H, dur):
    res, els = [], [e for e in plan.get("elements", []) if e.get("type") in TEXT_TYPES and not e.get("decor")]   # decor = scene scenery
    vertical = H > W
    spans = []
    for e in els:
        s, en = float(e.get("start", 0)), float(e.get("end", dur))
        spans.append((s, en, e["type"]))
        name = f"{e['type']}@{s:.2f}"
        if e["type"] != "captions" and en - s < 0.6:
            res.append(("overlay_min_duration", "fail", round(en - s, 3), ">= 0.6 s", name))
        if vertical:
            y = float(e.get("y", H / 2))
            half = float(e.get("h", H * (0.06 if e["type"] in ("text", "headline", "chip", "captions") else 0.15))) / 2
            top, bot = (y - half) / H, (y + half) / H
            if top < 0.10 or bot > 0.85:
                res.append(("safe_zone_vertical", "fail", f"{top:.2f}-{bot:.2f} of height", "inside 0.10-0.85", name))
            if "w" in e or "x" in e:                         # box edge; centred text may be narrower -> warn
                x, w = float(e.get("x", W / 2)), float(e.get("w", 0))
                if (x + w / 2) / W > 0.88:
                    res.append(("safe_zone_right", "warn", f"box right edge at {(x + w / 2) / W:.2f} W", "<= 0.88 W (clear of buttons)",
                                name + " (box width; check the glyphs on a still)"))
    if vertical and spans:
        pts = sorted({s for s, _, _ in spans} | {e for _, e, _ in spans})
        worst = max((sum(1 for s, e, _ in spans if s <= t + 1e-6 < e), t) for t in pts)
        res.append(("max_overlays_at_once", "fail" if worst[0] > 2 else "pass", worst[0], "<= 2 (reels)", f"at {worst[1]:.2f}s"))
    return res


def caption_checks(plan, words, fps, cps):
    res = []
    if words:
        cues = C.build_cues(words, cps=cps, fps=fps)
        bad = C.validate_cues(cues, cps=cps, fps=fps)
        res.append(("broadcast_cues", "warn" if bad else "pass", f"{len(cues)} cues, {len(bad)} issues",
                    f"42 chars x 2 lines, {cps:g} cps, 0.833-7 s, 2-frame gap", "; ".join(f"#{b['cue']} {b['rule']}={b['value']}" for b in bad[:5])))
    for el in (plan or {}).get("elements", []):
        if el.get("type") != "captions" or not words:
            continue
        chunks = creator_caption_chunks(el, words)
        maxc = int(el.get("maxChars", C.MAX_CHARS))
        fast = [c for c in chunks if " " in c["text"] and len(c["text"]) / c["dur"] > cps]  # one word on screen cannot be split further
        short = [c for c in chunks if c["dur"] < 0.3]
        long_ = [c for c in chunks if len(c["text"]) > maxc]
        res.append(("creator_captions_cps", "warn" if fast else "pass", f"{len(fast)}/{len(chunks)} chunks over {cps:g} cps",
                    f"<= {cps:g} cps", "; ".join(f"'{c['text']}' {len(c['text']) / c['dur']:.0f}cps" for c in fast[:4])))
        res.append(("creator_captions_flash", "warn" if short else "pass", f"{len(short)} chunks < 0.3 s", ">= 0.3 s per chunk", ""))
        res.append(("creator_captions_chars", "warn" if long_ else "pass", f"{len(long_)} chunks > {maxc} chars", f"<= {maxc}", ""))
    return res


# ------------------------------------------------------------------ main QC
def _add(rows, check, status, value, expected="", detail=""):
    rows.append({"check": check, "status": status, "value": value, "expected": expected, "detail": detail})


def _reframed(st, O):
    """A delivery in a different aspect ratio than its plan (e.g. 9:16 cut of a 16:9 master)."""
    if not (O.get("width") and st.get("width")):
        return False
    return abs(st["width"] / st["height"] - O["width"] / O["height"]) > 0.02


def _tech_checks(rows, st, pr, plan, path):
    if not st.get("width"):  # audio-only delivery (podcast mp3/wav): only audio checks apply
        _add(rows, "audio_present", "pass" if st["acodec"] else "fail", f"{st['acodec']} {st['sample_rate']} Hz x{st['channels']}", "audio stream")
        return
    O = (plan or {}).get("output", {})
    if O.get("duration"):
        dd = abs(st["duration"] - float(O["duration"]))
        _add(rows, "duration_vs_plan", "pass" if dd <= 1.5 / (st["fps"] or 30) else "warn" if dd <= 0.5 else "fail",
             round(st["duration"], 3), f"{O['duration']} s (+-1 frame)")
    if O.get("width"):
        ok = (st["width"], st["height"]) == (O["width"], O["height"])
        reframed = _reframed(st, O)
        _add(rows, "resolution_vs_plan", "pass" if ok else ("info" if reframed else "fail"), f"{st['width']}x{st['height']}",
             f"{O['width']}x{O['height']}", "platform reframe of the master: plan geometry checks skipped" if reframed else "")
    if O.get("fps") and st["fps"]:
        _add(rows, "fps_vs_plan", "pass" if abs(st["fps"] - O["fps"]) < 0.01 else "warn", st["fps"], O["fps"])
    if pr and pr["w"]:
        ok = (st["width"], st["height"]) == (pr["w"], pr["h"])
        _add(rows, "resolution_vs_platform", "pass" if ok else "warn", f"{st['width']}x{st['height']}", f"{pr['w']}x{pr['h']}")
    if pr and pr["vcodec"] == "h264":
        _add(rows, "codec", "pass" if st["vcodec"] == "h264" else "fail", st["vcodec"], "h264")
        _add(rows, "pix_fmt", "pass" if st["pix_fmt"] == "yuv420p" else "fail", st["pix_fmt"], "yuv420p (4:2:0 8-bit)")
        _add(rows, "colour_tags", "pass" if st["color"][0] == "bt709" else "warn", st["color"], "bt709 x3")
    else:
        _add(rows, "codec", "info", f"{st['vcodec']} {st['pix_fmt']}")
    if path.lower().endswith((".mp4", ".mov", ".m4v")):
        atoms = mp4_atoms(path)
        fs = "moov" in atoms and "mdat" in atoms and atoms.index("moov") < atoms.index("mdat")
        _add(rows, "faststart", "pass" if fs else "warn", " ".join(atoms[:4]), "moov before mdat")
    ki = keyframe_interval(path)
    _add(rows, "keyframe_interval", "info", ki, "YouTube: closed GOP = fps/2")
    _add(rows, "audio_present", "pass" if st["acodec"] else "fail", f"{st['acodec']} {st['sample_rate']} Hz x{st['channels']}", "audio stream")
    if pr and pr["max_bytes"]:
        _add(rows, "file_size", "pass" if st["bytes"] <= pr["max_bytes"] else "fail", f"{st['bytes'] / 2 ** 20:.1f} MB", f"<= {pr['max_bytes'] / 2 ** 20:.0f} MB")
    if pr and pr["max_dur"]:
        _add(rows, "max_length", "pass" if st["duration"] <= pr["max_dur"] else "fail", round(st["duration"], 2), f"<= {pr['max_dur']} s")


def _signal_checks(rows, an, st, pr, fps):
    lo = an["loudness"]
    if lo and pr and pr["lufs"] is not None:
        di = abs(lo.get("I", -99) - pr["lufs"])
        _add(rows, "integrated_loudness", "pass" if di <= 1 else "warn" if di <= 2 else "fail", lo.get("I"), f"{pr['lufs']} LUFS +-1")
        tp = lo.get("TP", 0)
        _add(rows, "true_peak", "pass" if tp <= pr["tp"] + 0.1 else "warn" if tp <= pr["tp"] + 0.5 else "fail", tp, f"<= {pr['tp']} dBTP")
        _add(rows, "loudness_range", "pass" if lo.get("LRA", 0) <= pr["lra"] else "warn", lo.get("LRA"), f"<= {pr['lra']} LU")
    elif lo:
        _add(rows, "loudness", "info", lo)
    gaps = [s for s in an["silence"] if s[1] - s[0] > 2]
    _add(rows, "silence_gaps_gt_2s", "warn" if gaps else "pass", len(gaps), "none", "; ".join(f"{a:.1f}-{b:.1f}s" for a, b in gaps[:5]))
    _add(rows, "black_frames", "warn" if an["black"] else "pass", len(an["black"]), "none",
         "; ".join(f"{a:.2f}-{b:.2f}s" for a, b in an["black"][:5]))
    bits = 1023.0 if st["pix_fmt"] and "10" in st["pix_fmt"] else 255.0
    fl = flash_analysis(an["yavg"], fps, bits)
    _add(rows, "flash_frames", "warn" if fl["flash_frames"] else "pass", len(fl["flash_frames"]), "no 1-frame luma spikes",
         ", ".join(map(str, fl["flash_frames"][:8])))
    _add(rows, "photosensitivity", "fail" if fl["max_flashes_per_s"] >= 3 else "pass", fl["max_flashes_per_s"],
         "< 3 flashes in any 1 s (Netflix/Harding)", f"worst at {fl['at']:.2f}s" if fl["at"] is not None else "")
    if an["brng"]:
        badf = sum(1 for b in an["brng"] if b > 0.01) / len(an["brng"])
        strict = pr is not None and pr["vcodec"] == "mpeg2_50"
        _add(rows, "illegal_levels_brng", "pass" if badf <= 0.01 else ("fail" if strict else "warn"), f"{badf * 100:.1f}% frames > 1% out-of-range px",
             "<= 1% of frames", f"max BRNG {max(an['brng']):.4f}")


def av_sync(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,start_time,duration", "-of", "json", path],
                         stdout=subprocess.PIPE, text=True).stdout
    ss = {s["codec_type"]: s for s in json.loads(out or "{}").get("streams", [])}
    if "video" not in ss or "audio" not in ss:
        return None
    f = lambda s, k: float(s.get(k) or 0)
    return {"start_offset_ms": round((f(ss["audio"], "start_time") - f(ss["video"], "start_time")) * 1000, 1),
            "duration_diff_ms": round((f(ss["audio"], "duration") - f(ss["video"], "duration")) * 1000, 1)}


def qc(video, plan_path=None, platform="auto", cps=C.CPS_ADULT):
    plan = load_json(plan_path) if plan_path else None
    st = stream_info(video)
    if platform == "auto":
        platform = ("podcast-mp3" if not st.get("width") else
                    "reels" if st["height"] and st["width"] and st["height"] > st["width"] else "youtube")
    platform = {"podcast": "podcast-mp3", "audio": "audio-wav"}.get(platform, platform)
    pr = PRESETS.get(platform) if platform != "none" else None
    fps = st["fps"] or 30
    rows = []
    _tech_checks(rows, st, pr, plan, video)
    an = analyse(video, bool(st["acodec"]))
    _signal_checks(rows, an, st, pr, fps)
    sync = av_sync(video)
    if sync:
        bad = abs(sync["start_offset_ms"]) > 1000 / fps or abs(sync["duration_diff_ms"]) > 100
        _add(rows, "av_sync_heuristic", "warn" if bad else "pass", sync, "start offset <= 1 frame, durations within 100 ms",
             "stream timing only; lip-sync itself is not measured")
    if plan:
        words = plan.get("words") or []
        for check, status, value, expected, detail in caption_checks(plan, words, fps, cps) + \
                overlay_checks(plan, st["width"], st["height"], st["duration"]):
            _add(rows, check, status, value, expected, detail)
    summary = {s: sum(1 for r in rows if r["status"] == s) for s in ("pass", "warn", "fail", "info")}
    return {"video": os.path.abspath(video), "plan": plan_path, "platform": platform, "stream": st,
            "measured_loudness": an["loudness"], "summary": summary, "checks": rows}


def write_md(rep, path):
    L = [f"# QC report: {os.path.basename(rep['video'])}", "", f"Platform spec: **{rep['platform']}**. "
         f"Result: {rep['summary']['fail']} FAIL, {rep['summary']['warn']} WARN, {rep['summary']['pass']} pass.", "",
         "| status | check | value | expected | detail |", "|---|---|---|---|---|"]
    order = {"fail": 0, "warn": 1, "pass": 2, "info": 3}
    for r in sorted(rep["checks"], key=lambda r: order[r["status"]]):
        L.append(f"| {r['status'].upper()} | {r['check']} | {r['value']} | {r['expected']} | {str(r['detail'])[:120]} |")
    open(path, "w", encoding="utf-8").write("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--plan")
    ap.add_argument("--platform", default="auto", help="preset name from deliver.py, 'auto' or 'none'")
    ap.add_argument("--out-dir")
    ap.add_argument("--kids", action="store_true")
    ap.add_argument("--strict", action="store_true", help="exit 1 if any check fails")
    a = ap.parse_args()
    if a.platform not in ("auto", "none", "podcast", "audio") and a.platform not in PRESETS:
        sys.exit(f"unknown platform {a.platform}")
    rep = qc(a.video, a.plan, a.platform, C.CPS_KIDS if a.kids else C.CPS_ADULT)
    od = a.out_dir or os.path.dirname(os.path.abspath(a.video))
    stem = os.path.splitext(os.path.basename(a.video))[0]
    save_json(os.path.join(od, f"qc_{stem}.json"), rep)
    write_md(rep, os.path.join(od, f"qc_{stem}.md"))
    s = rep["summary"]
    log(f"QC {stem} ({rep['platform']}): {s['fail']} fail, {s['warn']} warn, {s['pass']} pass -> {od}")
    for r in rep["checks"]:
        if r["status"] in ("fail", "warn"):
            log(f"  {r['status'].upper():4} {r['check']}: {r['value']} (expected {r['expected']}) {r['detail']}")
    sys.exit(1 if a.strict and s["fail"] else 0)


if __name__ == "__main__":
    main()
