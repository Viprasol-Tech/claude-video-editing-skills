#!/usr/bin/env python3
"""One-command pipeline: raw clip -> finished edit in a given style.

usage: run.py INPUT --style STYLE_DIR [--work WORKDIR] [--format 9:16] [--model small] [--language en]
              [--no-cut] [--max-gap 0.35] [--cut "12-14.5"] [--matte-backend mediapipe]
              [--cta "Follow for more"] [--title "..."] [--formats 1:1,16:9] [--stop-after plan]

  --stop-after plan   : stop after writing plan.json so Claude can refine it, then run
                        render.py and finish.py yourself.
  INPUT may be "-" with --no-source for type-only/promo styles that need no speaker video.
  --clip/--image/--image2/--logo pass media to styles that use them (device-fly, product-spotlight...).
"""
import argparse, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))

ap = argparse.ArgumentParser()
ap.add_argument("input")
ap.add_argument("--style", required=True)
ap.add_argument("--work", default="work")
ap.add_argument("--format", default=None)
ap.add_argument("--fps", default="30")
ap.add_argument("--model", default="small")
ap.add_argument("--language", default=None)
ap.add_argument("--prompt", default=None)
ap.add_argument("--no-cut", action="store_true")
ap.add_argument("--max-gap", default="0.35")
ap.add_argument("--cut", default="")
ap.add_argument("--matte-backend", default="mediapipe")
ap.add_argument("--no-matte", action="store_true")
ap.add_argument("--no-source", action="store_true")
ap.add_argument("--duration", default=None)
ap.add_argument("--cta", default=None)
ap.add_argument("--title", default=None)
ap.add_argument("--formats", default="")
ap.add_argument("--clip", default=None, help="screen recording / product video for styles that show one")
ap.add_argument("--image", default=None)
ap.add_argument("--image2", default=None)
ap.add_argument("--logo", default=None)
ap.add_argument("--stop-after", choices=["prep", "transcribe", "cut", "matte", "plan", "render"], default=None)
a = ap.parse_args()


def step(name, args):
    print(f"\n=== {name} ===", flush=True)
    r = subprocess.run([sys.executable, os.path.join(HERE, args[0])] + args[1:])
    if r.returncode != 0:
        sys.exit(r.returncode)
    if a.stop_after == name:
        print(f"stopped after {name}"); sys.exit(0)


import json
theme = json.load(open(os.path.join(a.style, "theme.json")))
needs_matte = theme.get("matte") and not a.no_matte and not a.no_source

if not a.no_source:
    step("prep", ["prep.py", a.input, "--work", a.work, "--fps", a.fps])
    tr = ["transcribe.py", "--work", a.work, "--model", a.model]
    if a.language: tr += ["--language", a.language]
    if a.prompt: tr += ["--prompt", a.prompt]
    step("transcribe", tr)
    ac = ["autocut.py", "--work", a.work, "--max-gap", a.max_gap]
    if a.no_cut: ac.append("--keep-all")
    if a.cut: ac += ["--cut", a.cut]
    step("cut", ac)
    if needs_matte:
        step("matte", ["matte.py", "--work", a.work, "--backend", a.matte_backend])
mp = ["make_plan.py", "--work", a.work, "--style", a.style]
if a.format: mp += ["--format", a.format]
if a.no_source: mp.append("--no-source")
if a.no_matte: mp.append("--no-matte")
if a.duration: mp += ["--duration", a.duration]
if a.cta: mp += ["--cta", a.cta]
if a.title: mp += ["--title", a.title]
for k in ("clip", "image", "image2", "logo"):
    if getattr(a, k): mp += ["--" + k, getattr(a, k)]
step("plan", mp)
plan = os.path.join(a.work, "plan.json")
step("render", ["render.py", plan])
fin = ["finish.py", plan]
if a.formats: fin += ["--formats", a.formats]
step("finish", fin)
