#!/usr/bin/env python3
"""Render a plan.json into a finished composite video.

  1. extracts any clips the plan uses into image sequences
  2. renders the HTML overlay layers (bg / behind / front) frame by frame with headless Chromium
  3. composites with FFmpeg:  bg -> speaker video -> behind -> person cut-out -> cutaways -> front

usage: render.py PLAN.json [--out work/composite.mp4] [--preview 3.5]   (preview = render one PNG at t)
       render.py PLAN.json --frames 0,2.5,6   (contact sheet of stills for checking the look)
"""
import argparse, json, math, os, shutil, subprocess, sys, tempfile
from vs_common import RUNTIME, load_json, run, probe, log, die, need

ap = argparse.ArgumentParser()
ap.add_argument("plan")
ap.add_argument("--out", default=None)
ap.add_argument("--preview", type=float, default=None, help="render a single composited still at this time")
ap.add_argument("--frames", default=None, help="comma list of times -> contact sheet PNG")
ap.add_argument("--workers", type=int, default=2, help="parallel browser pages")
ap.add_argument("--keep", action="store_true", help="keep rendered PNG frames")
a = ap.parse_args()
need("ffmpeg")

plan_path = os.path.abspath(a.plan)
pdir = os.path.dirname(plan_path)
plan = load_json(plan_path)
O = plan["output"]
W, H, FPS = int(O["width"]), int(O["height"]), int(O.get("fps", 30))
DUR = float(O["duration"])
NF = int(math.ceil(DUR * FPS))
work = os.path.abspath(os.path.join(pdir, plan.get("workDir", ".")))
rdir = os.path.join(work, "render")
os.makedirs(rdir, exist_ok=True)


def P(p):
    if p is None:
        return None
    if p.startswith(("http://", "https://", "data:", "file://")):
        return p
    return os.path.abspath(os.path.join(pdir, p))


def uri(p):
    p = P(p)
    return p if p.startswith(("http", "data:", "file:")) else "file://" + p

# ---------- 1. clips -> image sequences ----------
for c in plan.get("clips", []):
    src = P(c["src"])
    d = os.path.join(rdir, "clips", c["id"])
    marker = os.path.join(d, ".src")
    sig = json.dumps([src, c.get("start"), c.get("end"), c.get("maxWidth", 1080), FPS])
    if not (os.path.exists(marker) and open(marker, encoding="utf-8").read() == sig):
        shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
        cmd = ["ffmpeg", "-y", "-hide_banner"]
        if c.get("start") is not None: cmd += ["-ss", str(c["start"])]
        if c.get("end") is not None: cmd += ["-to", str(c["end"])]
        mw = c.get("maxWidth", 1080)
        cmd += ["-i", src, "-vf", f"fps={FPS},scale='min({mw},iw)':-2", "-q:v", "3", os.path.join(d, "%05d.jpg")]
        log(f"extracting clip '{c['id']}' frames")
        run(cmd)
        open(marker, "w").write(sig)
    c["frames"] = len([f for f in os.listdir(d) if f.endswith(".jpg")])
    c["dir"] = "file://" + d

# resolve element asset paths
for el in plan.get("elements", []):
    for k in ("image", "before", "after"):
        if el.get(k):
            el[k] = uri(el[k])

# ---------- 2. HTML ----------
theme = plan.get("theme", {})
css = open(os.path.join(RUNTIME, "base.css"), encoding="utf-8").read()
for cf in theme.get("cssFiles", []):
    css += "\n" + open(P(cf), encoding="utf-8").read()
css += "\n" + theme.get("css", "")
fonts = theme.get("fontsUrl")
engine = open(os.path.join(RUNTIME, "engine.js"), encoding="utf-8").read()
html = f"""<!doctype html><html><head><meta charset="utf-8">
{f'<link rel="stylesheet" href="{fonts}">' if fonts else ''}
<style>{css}</style></head><body><div id="stage"></div>
<script>window.__PLAN={json.dumps(plan, ensure_ascii=False)};</script>
<script>{engine}</script></body></html>"""
html_path = os.path.join(rdir, "index.html")
open(html_path, "w", encoding="utf-8").write(html)

# ---------- render frames ----------
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    die("playwright not installed. Run: pip install playwright && python -m playwright install chromium")


def open_page(pw):
    br = pw.chromium.launch(args=["--allow-file-access-from-files", "--disable-web-security", "--font-render-hinting=none"])
    pg = br.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
    pg.on("console", lambda m: m.type == "error" and log(f"page error: {m.text}"))
    pg.on("pageerror", lambda e: log(f"page exception: {e}"))
    pg.goto("file://" + html_path)
    try:
        pg.wait_for_function("window.__ready !== undefined", timeout=15000)
        pg.evaluate("Promise.race([window.__ready, new Promise(r=>setTimeout(r,8000))])")
    except Exception as e:
        die(f"overlay page failed to load: {e}")
    return br, pg


def shot(pg, t, layer, path):
    vis = pg.evaluate("([t,l]) => window.__render(t,l)", [t, layer])
    if vis:
        pg.screenshot(path=path, omit_background=(layer != "bg"), type="png")
    return vis


blank = os.path.join(rdir, "blank.png")
from PIL import Image
Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(blank)

with sync_playwright() as pw:
    br, pg = open_page(pw)
    layers = pg.evaluate("window.__layersUsed")

    if a.preview is not None or a.frames:
        times = [a.preview] if a.preview is not None else [float(x) for x in a.frames.split(",")]
        stills = []
        for t in times:
            lp = {}
            for l in layers:
                p = os.path.join(rdir, f"still_{l}_{t:.2f}.png")
                lp[l] = p if shot(pg, t, l, p) else blank
            stills.append((t, lp))
        br.close()
    else:
        # parallel pages
        import threading
        jobs = [(i, l) for l in layers for i in range(NF)]
        for l in layers:
            d = os.path.join(rdir, l); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
        br.close()

    if a.preview is None and not a.frames:
        nw = max(1, a.workers)
        chunks = [jobs[k::nw] for k in range(nw)]
        errors = []

        def worker(chunk, idx):
            try:
                with sync_playwright() as pw2:
                    b2, p2 = open_page(pw2)
                    for n, (i, l) in enumerate(chunk):
                        path = os.path.join(rdir, l, f"{i + 1:05d}.png")
                        if not shot(p2, i / FPS, l, path):
                            os.link(blank, path)
                        if idx == 0 and n % 90 == 0:
                            log(f"overlay frames {n * nw}/{len(jobs)}")
                    b2.close()
            except Exception as e:
                errors.append(e)
        ths = [threading.Thread(target=worker, args=(c, k)) for k, c in enumerate(chunks)]
        [t.start() for t in ths]; [t.join() for t in ths]
        if errors:
            die(f"render failed: {errors[0]}")

# ---------- 3. composite ----------
sp = plan.get("speaker", {"mode": "none"})
mode = sp.get("mode", "full") if plan.get("source") else "none"
src = P(plan.get("source")) if plan.get("source") else None
matte = P(plan.get("matte")) if plan.get("matte") else None
use_person = matte and os.path.exists(matte) and ("behind" in layers or sp.get("person"))
if plan.get("matte") and not use_person and "behind" in layers:
    log("WARNING: matte file missing - 'behind' layer will sit on top of the speaker. Run matte.py.")


COLOR_CHAIN = ""
if mode != "none" and src:
    import color as COL
    _si = probe(src)
    COLOR_CHAIN = COL.source_chain(plan, src, work, _si["width"], _si["height"])
    if COLOR_CHAIN:
        log("colour on source: " + (plan.get("color", {}).get("look") or plan.get("finish", {}).get("grade", "correction")))


def zoom_expr():
    zs = sp.get("zooms", [])
    push = sp.get("push", 0)
    terms = ["1"]
    if push:
        terms.append(f"{push}*it/{DUR}")
    for z in zs:
        s, e, k = z["start"], z["end"], z.get("scale", 1.12) - 1
        r = z.get("ramp", 0.12)
        if z.get("snap"):
            terms.append(f"{k}*between(it,{s},{e})")
        else:
            terms.append(f"{k}*clip((it-{s})/{r},0,1)*clip(({e}-it)/{r},0,1)")
    return "+".join(terms) if len(terms) > 1 else None


def _face_at(t):
    """Primary face centre (normalised source coords) at time t from plan["track"] [{t,x,y,w,h}], if present."""
    tr = plan.get("track") or []
    if not tr:
        return None
    f = min(tr, key=lambda p: abs(p["t"] - t))
    return f["x"] + f.get("w", 0) / 2, f["y"] + f.get("h", 0) / 2


def zoom_centre_expr():
    """Punch-ins zoom toward the face (or a zoom's own cx/cy, normalised) instead of the frame centre.
    Each zoom holds its centre for its whole window; zoompan keeps the crop inside the frame."""
    xs, ys = ["0.5"], ["0.5"]
    for z in sp.get("zooms", []):
        c = (z["cx"], z["cy"]) if "cx" in z and "cy" in z else (_face_at(z["start"]) if z.get("toFace", True) else None)
        if not c:
            continue
        s, e = z["start"] - 0.2, z["end"] + 0.2
        xs.append(f"{c[0] - 0.5:.4f}*between(it,{s},{e})")
        ys.append(f"{max(0.0, c[1] - 0.06) - 0.5:.4f}*between(it,{s},{e})")  # a touch above centre: eyes, not chin
    if len(xs) == 1:
        return "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    fx, fy = "+".join(xs), "+".join(ys)
    return (f"clip(iw*({fx})-iw/zoom/2,0,iw-iw/zoom)", f"clip(ih*({fy})-ih/zoom/2,0,ih-ih/zoom)")


def speaker_chain(label_in, label_out, is_mask=False, sw=0, sh=0):
    """zoom -> cover-crop to rect."""
    rx, ry, rw, rh = sp.get("rect", [0, 0, W, H])
    fx = sp.get("focusX", 0.5); fy = sp.get("focusY", 0.5)
    f = []
    ze = zoom_expr()
    if ze:
        zx, zy = zoom_centre_expr()
        f.append(f"zoompan=z='{ze}':d=1:x='{zx}':y='{zy}':s={sw}x{sh}:fps={FPS}")
    f.append(f"scale={rw}:{rh}:force_original_aspect_ratio=increase:flags=lanczos")
    f.append(f"crop={rw}:{rh}:(iw-{rw})*{fx}:(ih-{rh})*{fy}")
    if sp.get("mirror"):
        f.append("hflip")
    f.append("format=gray" if is_mask else "format=yuva420p")
    return f"[{label_in}]" + ",".join(f) + f"[{label_out}]"


def composite(out_path, single_t=None, still_layers=None):
    inputs, graph = [], []

    def add_input(args):
        inputs.extend(args); return len([x for x in inputs if x == "-i"]) - 1

    seq = lambda l: (["-loop", "1", "-t", "0.04", "-i", still_layers[l]] if single_t is not None
                     else ["-framerate", str(FPS), "-i", os.path.join(rdir, l, "%05d.png")])
    dur = 0.5 if single_t is not None else DUR
    bgcol = O.get("background", "black")
    if "bg" in layers:
        i = add_input(seq("bg")); graph.append(f"[{i}:v]format=yuva420p,scale={W}:{H}[base]")
    else:
        graph.append(f"color=c={bgcol}:s={W}x{H}:r={FPS}:d={dur}[base]")
    cur = "base"
    if mode != "none":
        ss = ["-ss", str(single_t)] if single_t is not None else []
        si = add_input(ss + ["-i", src])
        info = probe(src)
        sw, sh = info["width"], info["height"]
        rx, ry, rw, rh = sp.get("rect", [0, 0, W, H])
        n_split = 2 if use_person else 1
        # colour on the camera footage, before overlays (and identical for the person cut-out)
        cc = ("," + COLOR_CHAIN) if COLOR_CHAIN else ""
        if n_split == 2:
            graph.append(f"[{si}:v]setpts=PTS-STARTPTS{cc},split=2[srcA][srcB]")
        else:
            graph.append(f"[{si}:v]setpts=PTS-STARTPTS{cc}[srcA]")
        graph.append(speaker_chain("srcA", "spk", sw=sw, sh=sh))
        radius = min(sp.get("radius", 0), min(rw, rh) // 2)
        rmask = None
        if radius:
            rm = os.path.join(rdir, f"rmask_{rw}x{rh}_{radius}.png")
            if not os.path.exists(rm):
                from PIL import ImageDraw
                im = Image.new("L", (rw, rh), 0); ImageDraw.Draw(im).rounded_rectangle([0, 0, rw - 1, rh - 1], radius=radius, fill=255); im.save(rm)
            ri = add_input(["-loop", "1", "-i", rm])
            if use_person:
                graph.append(f"[{ri}:v]format=gray,split=2[rm1][rm2]")
            else:
                graph.append(f"[{ri}:v]format=gray[rm1]")
            graph.append("[spk][rm1]alphamerge[spkr]")
            rmask = "rm2"
            spk = "spkr"
        else:
            spk = "spk"
        graph.append(f"[{cur}][{spk}]overlay={rx}:{ry}:shortest=0:eof_action=pass[c1]"); cur = "c1"
        if "behind" in layers:
            bi = add_input(seq("behind")); graph.append(f"[{cur}][{bi}:v]overlay=0:0[c2]"); cur = "c2"
        if use_person:
            mi = add_input(ss + ["-i", matte])
            graph.append(f"[{mi}:v]setpts=PTS-STARTPTS[mraw]")
            graph.append(speaker_chain("mraw", "mk", is_mask=True, sw=sw, sh=sh))
            if rmask:
                graph.append(f"[mk][{rmask}]blend=all_mode=multiply[mk2]"); mk = "mk2"
            else:
                mk = "mk"
            graph.append(speaker_chain("srcB", "pv", sw=sw, sh=sh).replace("format=yuva420p", "format=yuv420p"))
            graph.append(f"[pv][{mk}]alphamerge[person]")
            graph.append(f"[{cur}][person]overlay={rx}:{ry}[c3]"); cur = "c3"
    elif "behind" in layers:
        bi = add_input(seq("behind")); graph.append(f"[{cur}][{bi}:v]overlay=0:0[c2]"); cur = "c2"
    # cutaways (full-frame b-roll videos); stills show the one on screen at single_t
    if single_t is not None:
        for k, cw in enumerate(c for c in plan.get("cutaways", []) if c["start"] <= single_t < c["end"]):
            off = max(0.0, single_t - cw["start"] + cw.get("srcStart", 0))
            img = str(cw["src"]).lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
            ci = add_input((["-loop", "1"] if img else ["-ss", str(off)]) + ["-i", P(cw["src"])])
            graph.append(f"[{ci}:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},format=yuva420p[cws{k}]")
            graph.append(f"[{cur}][cws{k}]overlay=0:0[cwso{k}]"); cur = f"cwso{k}"
    for k, cw in enumerate(plan.get("cutaways", []) if single_t is None else []):
        ci = add_input(["-i", P(cw["src"])])
        d = cw["end"] - cw["start"]
        graph.append(f"[{ci}:v]trim=start={cw.get('srcStart', 0)}:duration={d},setpts=PTS-STARTPTS+{cw['start']}/TB,"
                     f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},format=yuva420p[cw{k}]")
        graph.append(f"[{cur}][cw{k}]overlay=0:0:enable='between(t,{cw['start']},{cw['end']})':eof_action=pass[cwo{k}]"); cur = f"cwo{k}"
    # privacy / focus blurs on the picture (not the graphics): plan "blurs": [{x,y,w,h,start,end,strength}]
    # x,y,w,h in output pixels (top-left box); strength = blur radius (default 24); "pixelate": true for mosaic
    for k, b in enumerate(plan.get("blurs", [])):
        s_, e_ = b.get("start", 0), b.get("end", DUR + 1)
        if single_t is not None and not (s_ <= single_t < e_):
            continue
        bx, by = max(0, int(b["x"])), max(0, int(b["y"]))
        bw, bh = max(8, min(int(b["w"]), W - bx)) // 2 * 2, max(8, min(int(b["h"]), H - by)) // 2 * 2
        fx = (f"scale=iw/{int(b.get('block', 24))}:-2,scale={bw}:{bh}:flags=neighbor" if b.get("pixelate")
              else f"boxblur={min(int(b.get('strength', 24)), bw // 2 - 1, bh // 2 - 1)}:2")
        en = "" if single_t is not None else f":enable='between(t,{s_},{e_})'"
        graph.append(f"[{cur}]split=2[bb{k}a][bb{k}b]")
        graph.append(f"[bb{k}b]crop={bw}:{bh}:{bx}:{by},{fx}[bb{k}c]")
        graph.append(f"[bb{k}a][bb{k}c]overlay={bx}:{by}{en}[bbo{k}]"); cur = f"bbo{k}"
    if "front" in layers:
        fi = add_input(seq("front")); graph.append(f"[{cur}][{fi}:v]overlay=0:0[c4]"); cur = "c4"
    graph.append(f"[{cur}]format=yuv420p[vout]")
    gf = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False); gf.write(";\n".join(graph)); gf.close()
    cmd = ["ffmpeg", "-y", "-hide_banner"] + inputs + ["-filter_complex_script", gf.name, "-map", "[vout]"]
    if single_t is not None:
        cmd += ["-frames:v", "1", out_path]
    else:
        if mode != "none":
            cmd += ["-map", "1:a?" if "bg" in layers else "0:a?"]
        cmd += ["-t", str(DUR), "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out_path]
    run(cmd)
    os.unlink(gf.name)


if a.preview is not None or a.frames:
    outs = []
    for t, lp in stills:
        p = os.path.join(work, f"still_{t:.2f}.png")
        composite(p, single_t=t, still_layers=lp)
        outs.append(p)
    if len(outs) > 1:
        ims = [Image.open(p).convert("RGB") for p in outs]
        sc = 540 / ims[0].width
        ims = [im.resize((int(im.width * sc), int(im.height * sc))) for im in ims]
        cols = min(4, len(ims)); rows = math.ceil(len(ims) / cols)
        sheet = Image.new("RGB", (cols * ims[0].width, rows * ims[0].height), "white")
        for k, im in enumerate(ims):
            sheet.paste(im, ((k % cols) * im.width, (k // cols) * im.height))
        sp_path = os.path.join(work, "contact_sheet.png"); sheet.save(sp_path); log(f"contact sheet -> {sp_path}")
    else:
        log(f"still -> {outs[0]}")
    sys.exit(0)

out = a.out or os.path.join(work, "composite.mp4")
log("compositing with ffmpeg")
composite(out)
if not a.keep:
    for l in layers:
        shutil.rmtree(os.path.join(rdir, l), ignore_errors=True)
log(f"composite -> {out}")
