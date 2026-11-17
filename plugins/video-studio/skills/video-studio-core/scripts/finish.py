#!/usr/bin/env python3
"""Finishing pass: colour grade, grain, vignette, letterbox, sound effects, ducked music,
loudness normalisation (-14 LUFS for social) and extra aspect-ratio exports.

usage: finish.py PLAN.json [--in work/composite.mp4] [--out final.mp4] [--formats 1:1,16:9]

Reads from the plan:
  "finish": {"grade": "warm", "grain": 8, "vignette": true, "letterbox": 0.1, "lut": "x.cube", "sharpen": true}
  "sfx":    [{"t": 1.2, "kind": "pop", "gain": 0.8}]     kinds: pop click ding boom whoosh swish riser type camera
  "music":  {"src": "music.mp3", "volume": 0.12, "duck": true, "start": 0}
"""
import argparse, os, tempfile
from vs_common import load_json, run, probe, log, parse_format

ap = argparse.ArgumentParser()
ap.add_argument("plan")
ap.add_argument("--in", dest="inp", default=None)
ap.add_argument("--out", default=None)
ap.add_argument("--formats", default="", help="extra exports, e.g. 1:1,16:9")
ap.add_argument("--lufs", type=float, default=-14)
a = ap.parse_args()

pp = os.path.abspath(a.plan); pdir = os.path.dirname(pp)
plan = load_json(pp)
work = os.path.abspath(os.path.join(pdir, plan.get("workDir", ".")))
inp = a.inp or os.path.join(work, "composite.mp4")
out = a.out or os.path.join(pdir, plan.get("outputFile", "final.mp4"))
P = lambda p: p if os.path.isabs(p) else os.path.abspath(os.path.join(pdir, p))
O = plan["output"]; W, H = O["width"], O["height"]
info = probe(inp); DUR = info["duration"]
fin = plan.get("finish", {})

GRADES = {
    "none": "",
    "warm": "colorbalance=rs=.05:bs=-.05:rm=.04:bm=-.04,eq=saturation=1.08",
    "cool": "colorbalance=rs=-.04:bs=.06:rm=-.02:bm=.04,eq=saturation=1.02",
    "teal-orange": "colorbalance=rs=-.08:gs=-.02:bs=.10:rh=.10:gh=.02:bh=-.08,eq=contrast=1.05:saturation=1.1",
    "punchy": "eq=contrast=1.12:saturation=1.25",
    "film": "curves=master='0/0.04 0.5/0.5 1/0.95',colorbalance=rm=.03:bm=-.03,eq=saturation=0.92",
    "bw": "hue=s=0,eq=contrast=1.18",
    "vintage": "curves=preset=vintage,eq=saturation=0.9",
    "faded": "curves=master='0/0.08 1/0.92',eq=saturation=0.85",
    "neon": "eq=contrast=1.1:saturation=1.35,colorbalance=rs=.03:bs=.06",
    "vhs": "rgbashift=rh=5:bh=-5,eq=saturation=1.35:contrast=1.08,scale=iw/2:-2,scale={W}:{H}:flags=bilinear",
    "pastel": "eq=saturation=0.8:brightness=0.04,curves=master='0/0.06 1/1'",
    "noir": "hue=s=0,curves=master='0/0 0.4/0.3 1/1',eq=contrast=1.3",
}
vf = []
g = fin.get("grade", "none")
if g not in GRADES:
    log(f"unknown grade '{g}', using none"); g = "none"
if GRADES[g]:
    vf.append(GRADES[g].format(W=W, H=H))
if fin.get("lut"):
    vf.append(f"lut3d='{P(fin['lut'])}'")
if fin.get("sharpen"):
    vf.append("unsharp=5:5:0.45")
if fin.get("vignette"):
    vf.append("vignette=PI/4.6")
if fin.get("grain"):
    vf.append(f"noise=alls={int(fin['grain'])}:allf=t")
if fin.get("letterbox"):
    bh = int(H * float(fin["letterbox"]))
    vf.append(f"drawbox=x=0:y=0:w=iw:h={bh}:color=black:t=fill,drawbox=x=0:y=ih-{bh}:w=iw:h={bh}:color=black:t=fill")
vf.append("format=yuv420p")

SFX = {
    "pop": "aevalsrc='0.6*sin(2*PI*(500+900*exp(-35*t))*t)*exp(-22*t)':d=0.18:s=48000",
    "click": "aevalsrc='0.6*sin(2*PI*2200*t)*exp(-140*t)':d=0.05:s=48000",
    "type": "aevalsrc='0.35*sin(2*PI*1800*t)*exp(-160*t)+0.2*(random(0)-0.5)*exp(-200*t)':d=0.04:s=48000",
    "ding": "aevalsrc='0.35*(sin(2*PI*1320*t)+0.5*sin(2*PI*2640*t))*exp(-5*t)':d=1.0:s=48000",
    "boom": "aevalsrc='0.9*sin(2*PI*(38+90*exp(-7*t))*t)*exp(-3.5*t)':d=1.1:s=48000",
    "riser": "aevalsrc='0.25*sin(2*PI*(180+1600*t*t)*t)*(t/1.2)':d=1.2:s=48000",
    "whoosh": "anoisesrc=d=0.5:c=pink:a=0.7:r=48000,bandpass=f=1400:w=1600,afade=t=in:d=0.22,afade=t=out:st=0.22:d=0.28",
    "swish": "anoisesrc=d=0.28:c=white:a=0.5:r=48000,highpass=f=2500,afade=t=in:d=0.1,afade=t=out:st=0.1:d=0.18",
    "camera": "aevalsrc='0.6*sin(2*PI*2500*t)*exp(-150*t)+0.5*sin(2*PI*1800*(t-0.08))*exp(-150*(t-0.08))*gte(t,0.08)':d=0.16:s=48000",
}
inputs = ["-i", inp]
af, mix = [], []
n_in = 1
if info["has_audio"]:
    af.append("[0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[voice][vkey]")
    mix.append("[voice]")
else:
    af.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={DUR}[voice]"); mix.append("[voice]")
    af.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={DUR}[vkey]")
for k, s in enumerate(plan.get("sfx", [])):
    kind = s.get("kind", "pop")
    if kind not in SFX and not s.get("file"):
        continue
    src = f"amovie='{P(s['file'])}'" if s.get("file") else SFX[kind]
    d = int(max(0, s["t"]) * 1000)
    af.append(f"{src},aformat=sample_rates=48000:channel_layouts=stereo,volume={s.get('gain', 0.7)},adelay={d}|{d}[s{k}]")
    mix.append(f"[s{k}]")
m = plan.get("music")
if m and m.get("src"):
    inputs += ["-stream_loop", "-1", "-i", P(m["src"])]; mi = n_in; n_in += 1
    fo = m.get("fadeOut", 1.5)
    af.append(f"[{mi}:a]atrim=start={m.get('start', 0)}:duration={DUR},asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,"
              f"volume={m.get('volume', 0.12)},afade=t=in:d=0.6,afade=t=out:st={max(0, DUR - fo)}:d={fo}[mus]")
    if m.get("duck", True) and info["has_audio"]:
        af.append("[mus][vkey]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=350[mduck]"); mix.append("[mduck]")
    else:
        af.append("[vkey]anullsink"); mix.append("[mus]")
else:
    af.append("[vkey]anullsink")
af.append("".join(mix) + f"amix=inputs={len(mix)}:duration=first:normalize=0,loudnorm=I={a.lufs}:TP=-1.5:LRA=11,aresample=48000[aout]")
graph = f"[0:v]{','.join(vf)}[vout];\n" + ";\n".join(af)
gf = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False); gf.write(graph); gf.close()
log("finishing: grade/grain/audio")
run(["ffmpeg", "-y", "-hide_banner"] + inputs + ["-filter_complex_script", gf.name, "-map", "[vout]", "-map", "[aout]",
     "-t", str(DUR), "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-profile:v", "high",
     "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out])
os.unlink(gf.name)
log(f"final -> {out}")

for f in [x.strip() for x in a.formats.split(",") if x.strip()]:
    fw, fh = parse_format(f)
    o2 = out.replace(".mp4", f"_{fw}x{fh}.mp4")
    run(["ffmpeg", "-y", "-hide_banner", "-i", out, "-filter_complex",
         f"[0:v]split=2[a][b];[a]scale={fw}:{fh}:force_original_aspect_ratio=increase,crop={fw}:{fh},scale=iw/8:-2,gblur=sigma=6,scale={fw}:{fh},eq=brightness=-0.08[bg];"
         f"[b]scale={fw}:{fh}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[v]",
         "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-crf", "19", "-c:a", "copy", o2])
    log(f"extra format -> {o2}")
