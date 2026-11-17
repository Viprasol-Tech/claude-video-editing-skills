#!/usr/bin/env python3
"""Check that everything Video Studio needs is installed, and print the fix for anything missing."""
import importlib, shutil, subprocess, sys

ok = True


def report(name, good, fix=""):
    global ok
    print(f"  [{'ok' if good else 'MISSING'}] {name}" + ("" if good else f"\n          fix: {fix}"))
    ok = ok and good


print("Video Studio environment check")
report("python >= 3.9", sys.version_info >= (3, 9), "install Python 3.10+ from python.org")
report("ffmpeg", bool(shutil.which("ffmpeg")), "macOS: brew install ffmpeg | Windows: winget install ffmpeg | Linux: sudo apt install ffmpeg")
report("ffprobe", bool(shutil.which("ffprobe")), "comes with ffmpeg")
for mod, fix, req in [("numpy", "pip install numpy", True), ("PIL", "pip install pillow", True),
                      ("playwright", "pip install playwright && python -m playwright install chromium", True),
                      ("faster_whisper", "pip install faster-whisper", True),
                      ("mediapipe", "pip install mediapipe   (only for text-behind-head styles)", False),
                      ("rembg", "pip install rembg onnxruntime   (optional matte backend)", False)]:
    try:
        importlib.import_module(mod); good = True
    except Exception:
        good = False
    if req:
        report(mod, good, fix)
    else:
        print(f"  [{'ok' if good else 'optional'}] {mod}" + ("" if good else f"  -> {fix}"))
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(); b.close()
    report("chromium for playwright", True)
except Exception:
    report("chromium for playwright", False, "python -m playwright install chromium")
print("\nAll required parts are installed." if ok else "\nInstall the missing parts above, then run this check again.")
sys.exit(0 if ok else 1)
