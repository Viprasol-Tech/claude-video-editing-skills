#!/usr/bin/env python3
"""Jump-cut editor: removes silences, filler words and any ranges you list, using word timestamps.
Writes <work>/cut.mp4, <work>/words.json (words re-timed to the cut) and <work>/cutlist.json.

usage: autocut.py --work WORKDIR [--max-gap 0.35] [--pad 0.08] [--fillers um,uh,erm]
                  [--cut "12.3-15.8,40-41.2"]   # extra ranges (source seconds) e.g. retakes
                  [--keep-all]                  # no silence/filler cutting, just copy (still writes words.json)
"""
import argparse, os, re, subprocess, tempfile
from vs_common import load_json, save_json, run, probe, log

ap = argparse.ArgumentParser()
ap.add_argument("--work", default="work")
ap.add_argument("--max-gap", type=float, default=0.35, help="pauses longer than this are cut")
ap.add_argument("--pad", type=float, default=0.08, help="breathing room kept around words")
ap.add_argument("--fillers", default="um,uh,uhm,umm,erm,er,ah,hmm,mm,uhh")
ap.add_argument("--cut", default="", help="comma list of start-end ranges to remove (source time)")
ap.add_argument("--keep-all", action="store_true")
a = ap.parse_args()

src = os.path.join(a.work, "source.mp4")
tr = load_json(os.path.join(a.work, "transcript.json"))
dur = probe(src)["duration"]
words = tr["words"]
fill = {f.strip().lower() for f in a.fillers.split(",") if f.strip()}
norm = lambda s: re.sub(r"[^\w']", "", s.lower())

manual = []
for r in [x for x in a.cut.split(",") if x.strip()]:
    s, e = r.split("-")
    manual.append((float(s), float(e)))

if a.keep_all or not words:
    segs = [(0.0, dur)]
else:
    kept = [w for w in words if norm(w["w"]) not in fill]
    segs = []
    for w in kept:
        s, e = max(0.0, w["start"] - a.pad), min(dur, w["end"] + a.pad)
        if segs and s - segs[-1][1] <= a.max_gap:
            segs[-1] = (segs[-1][0], max(segs[-1][1], e))
        else:
            segs.append((s, e))

# subtract manual ranges
for cs, ce in manual:
    out = []
    for s, e in segs:
        if ce <= s or cs >= e:
            out.append((s, e)); continue
        if cs > s: out.append((s, cs))
        if ce < e: out.append((ce, e))
    segs = out
segs = [(round(s, 3), round(e, 3)) for s, e in segs if e - s > 0.12]
if not segs:
    segs = [(0.0, dur)]

# build ffmpeg graph
parts, labels = [], []
for i, (s, e) in enumerate(segs):
    d = e - s
    f = min(0.012, d / 4)
    parts.append(f"[0:v]trim=start={s}:end={e},setpts=PTS-STARTPTS[v{i}]")
    parts.append(f"[0:a]atrim=start={s}:end={e},asetpts=PTS-STARTPTS,afade=t=in:d={f},afade=t=out:st={d - f:.4f}:d={f}[a{i}]")
    labels.append(f"[v{i}][a{i}]")
parts.append("".join(labels) + f"concat=n={len(segs)}:v=1:a=1[v][a]")
graph = ";\n".join(parts)
gf = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
gf.write(graph); gf.close()
out = os.path.join(a.work, "cut.mp4")
log(f"cutting into {len(segs)} segments")
run(["ffmpeg", "-y", "-hide_banner", "-i", src, "-filter_complex_script", gf.name, "-map", "[v]", "-map", "[a]",
     "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", out])
os.unlink(gf.name)

# retime words
new_words, t0, mapping = [], 0.0, []
for s, e in segs:
    mapping.append({"src_start": s, "src_end": e, "out_start": round(t0, 3)})
    for w in words:
        if norm(w["w"]) in fill and not a.keep_all:
            continue
        if w["start"] >= s - 1e-3 and w["end"] <= e + 1e-3:
            nw = dict(w); nw["start"] = round(t0 + w["start"] - s, 3); nw["end"] = round(t0 + w["end"] - s, 3)
            new_words.append(nw)
    t0 += e - s
save_json(os.path.join(a.work, "words.json"), {"language": tr.get("language"), "words": new_words, "duration": round(t0, 3)})
save_json(os.path.join(a.work, "cutlist.json"), {"segments": mapping, "removed_seconds": round(dur - t0, 2)})
log(f"{dur:.1f}s -> {t0:.1f}s (removed {dur - t0:.1f}s). words.json has {len(new_words)} words")
