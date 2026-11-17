#!/usr/bin/env python3
"""Person matte for depth effects (text/shapes BEHIND the speaker).
Writes <work>/matte.mp4: a grey-scale mask video, white = person, aligned frame-for-frame with the input.

usage: matte.py --work WORKDIR [--input work/cut.mp4] [--backend mediapipe|rembg|chroma]
                [--proc-width 512] [--smooth 0.55] [--feather 3]

Backends
  mediapipe (default) : fast on CPU. pip install mediapipe. Model auto-downloads once (~16 MB).
  rembg               : slower, sometimes cleaner hair. pip install rembg onnxruntime
  chroma              : for footage shot on a green screen. No downloads.
"""
import argparse, os, subprocess, sys, urllib.request
import numpy as np
from vs_common import probe, log, die, need

ap = argparse.ArgumentParser()
ap.add_argument("--work", default="work")
ap.add_argument("--input", default=None)
ap.add_argument("--out", default=None)
ap.add_argument("--backend", default="mediapipe")
ap.add_argument("--proc-width", type=int, default=512)
ap.add_argument("--smooth", type=float, default=0.55, help="temporal smoothing 0..0.9 (higher = steadier, more lag)")
ap.add_argument("--feather", type=float, default=3, help="edge blur in output pixels")
ap.add_argument("--lo", type=float, default=0.35)
ap.add_argument("--hi", type=float, default=0.75)
a = ap.parse_args()
need("ffmpeg")
inp = a.input or os.path.join(a.work, "cut.mp4")
if not os.path.exists(inp):
    inp = os.path.join(a.work, "source.mp4")
out = a.out or os.path.join(a.work, "matte.mp4")
info = probe(inp)
W, H, fps = info["width"], info["height"], info["fps"]
pw = min(a.proc_width, W) // 2 * 2
ph = int(H * pw / W) // 2 * 2

# ---------------- backends ----------------
def mk_mediapipe():
    try:
        import mediapipe as mp
        from mediapipe.tasks import python as mpt
        from mediapipe.tasks.python import vision
    except ImportError:
        die("mediapipe not installed. Run: pip install mediapipe   (or use --backend rembg / chroma)")
    cache = os.path.join(os.path.expanduser("~"), ".cache", "video-studio")
    os.makedirs(cache, exist_ok=True)
    model = os.path.join(cache, "selfie_multiclass_256x256.tflite")
    if not os.path.exists(model):
        url = "https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_multiclass_256x256/float32/latest/selfie_multiclass_256x256.tflite"
        log("downloading MediaPipe selfie model (one time)…")
        urllib.request.urlretrieve(url, model)
    opts = vision.ImageSegmenterOptions(base_options=mpt.BaseOptions(model_asset_path=model),
                                        running_mode=vision.RunningMode.VIDEO, output_confidence_masks=True)
    seg = vision.ImageSegmenter.create_from_options(opts)
    state = {"i": 0}

    def f(rgb):
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        res = seg.segment_for_video(img, int(state["i"] * 1000 / fps))
        state["i"] += 1
        bgm = res.confidence_masks[0].numpy_view()  # category 0 = background
        return 1.0 - np.squeeze(bgm)
    return f


def mk_rembg():
    try:
        from rembg import new_session, remove
    except ImportError:
        die("rembg not installed. Run: pip install rembg onnxruntime")
    from PIL import Image
    sess = new_session("u2net_human_seg")

    def f(rgb):
        m = remove(Image.fromarray(rgb), session=sess, only_mask=True)
        return np.asarray(m, dtype=np.float32) / 255.0
    return f


def mk_chroma():
    def f(rgb):
        x = rgb.astype(np.float32)
        r, g, b = x[..., 0], x[..., 1], x[..., 2]
        greenness = g - np.maximum(r, b)
        return 1.0 - np.clip((greenness - 20) / 60, 0, 1)
    return f


seg = {"mediapipe": mk_mediapipe, "rembg": mk_rembg, "chroma": mk_chroma}.get(a.backend)
if not seg:
    die("unknown backend")
seg = seg()

reader = subprocess.Popen(["ffmpeg", "-v", "error", "-i", inp, "-vf", f"scale={pw}:{ph}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                          stdout=subprocess.PIPE)
writer = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{pw}x{ph}", "-r", str(fps), "-i", "-",
                           "-vf", f"scale={W}:{H}:flags=bicubic,gblur=sigma={a.feather},format=gray",
                           "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
frame_bytes = pw * ph * 3
prev, n = None, 0
total = int(info["duration"] * fps)
while True:
    buf = reader.stdout.read(frame_bytes)
    if len(buf) < frame_bytes:
        break
    rgb = np.frombuffer(buf, np.uint8).reshape(ph, pw, 3)
    m = seg(rgb).astype(np.float32)
    if m.shape != (ph, pw):
        from PIL import Image
        m = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).resize((pw, ph)), np.float32) / 255
    m = np.clip((m - a.lo) / (a.hi - a.lo), 0, 1)
    if prev is not None:
        m = a.smooth * prev + (1 - a.smooth) * m
    prev = m
    writer.stdin.write((m * 255).astype(np.uint8).tobytes())
    n += 1
    if n % 60 == 0:
        log(f"matte {n}/{total} frames")
writer.stdin.close(); writer.wait(); reader.wait()
if n == 0:
    die("no frames read")
log(f"matte done: {n} frames -> {out}")
