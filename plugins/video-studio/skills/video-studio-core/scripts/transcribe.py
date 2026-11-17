#!/usr/bin/env python3
"""Word-level transcription with faster-whisper (runs locally, free).
Writes <work>/transcript.json : {"language", "words":[{"w","start","end"}], "segments":[{"text","start","end"}]}

usage: transcribe.py --work WORKDIR [--model small] [--language en] [--audio path]
       transcribe.py --work WORKDIR --from-srt subs.srt     (import existing subtitles instead)

Models: tiny, base, small (default), medium, large-v3. Bigger = slower, more accurate.
First run downloads the model from Hugging Face (~460 MB for small).
"""
import argparse, os, re
from vs_common import save_json, log, die

ap = argparse.ArgumentParser()
ap.add_argument("--work", default="work")
ap.add_argument("--audio", default=None)
ap.add_argument("--model", default="small")
ap.add_argument("--language", default=None)
ap.add_argument("--from-srt", default=None)
ap.add_argument("--prompt", default=None, help="initial prompt: names/jargon to spell correctly")
a = ap.parse_args()
out_path = os.path.join(a.work, "transcript.json")


def srt_time(s):
    hh, mm, rest = s.replace(",", ".").split(":")
    return int(hh) * 3600 + int(mm) * 60 + float(rest)


if a.from_srt:
    # Spread each subtitle's words evenly across its time span.
    txt = open(a.from_srt, encoding="utf-8").read()
    blocks = re.split(r"\n\s*\n", txt.strip())
    words, segs = [], []
    for b in blocks:
        lines = b.strip().splitlines()
        tl = next((l for l in lines if "-->" in l), None)
        if not tl:
            continue
        s, e = [srt_time(x.strip().split(" ")[0]) for x in tl.split("-->")]
        text = " ".join(l for l in lines[lines.index(tl) + 1:]).strip()
        ws = text.split()
        if not ws:
            continue
        step = (e - s) / len(ws)
        for i, w in enumerate(ws):
            words.append({"w": w, "start": round(s + i * step, 3), "end": round(s + (i + 1) * step, 3)})
        segs.append({"text": text, "start": s, "end": e})
    save_json(out_path, {"language": a.language or "en", "words": words, "segments": segs})
    log(f"imported {len(words)} words from {a.from_srt}")
    raise SystemExit(0)

try:
    from faster_whisper import WhisperModel
except ImportError:
    die("faster-whisper is not installed. Run: pip install faster-whisper")

audio = a.audio or os.path.join(a.work, "audio16k.wav")
if not os.path.exists(audio):
    die(f"{audio} not found. Run prep.py first.")

device, ctype = "cpu", "int8"
try:
    import ctranslate2
    if ctranslate2.get_cuda_device_count() > 0:
        device, ctype = "cuda", "float16"
except Exception:
    pass
log(f"loading whisper '{a.model}' on {device}")
model = WhisperModel(a.model, device=device, compute_type=ctype)


def load_pcm(path):
    """Decode to 16 kHz mono float32 with FFmpeg. Passing an array instead of a path avoids
    faster-whisper's PyAV decoder, which breaks whenever the installed PyAV version changes its API."""
    import subprocess
    import numpy as np
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        die(f"cannot decode {path}: {p.stderr.decode(errors='ignore')[-400:]}")
    return np.frombuffer(p.stdout, dtype=np.float32)


segments, info = model.transcribe(load_pcm(audio), word_timestamps=True, language=a.language, vad_filter=True,
                                  initial_prompt=a.prompt, condition_on_previous_text=False)
words, segs = [], []
for seg in segments:
    segs.append({"text": seg.text.strip(), "start": round(seg.start, 3), "end": round(seg.end, 3)})
    for w in seg.words or []:
        t = w.word.strip()
        if t:
            words.append({"w": t, "start": round(w.start, 3), "end": round(w.end, 3), "p": round(w.probability, 3)})
save_json(out_path, {"language": info.language, "words": words, "segments": segs})
log(f"{len(words)} words, language={info.language} -> {out_path}")
