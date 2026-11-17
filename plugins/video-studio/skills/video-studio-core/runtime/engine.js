/* Video Studio runtime — deterministic, seekable overlay engine.
 * window.__PLAN  : the plan object (see references/plan-schema.md)
 * window.__render(t, layer) -> Promise<boolean>  (true if anything visible on that layer)
 * Every element is a pure function of time t: no CSS animations, no timers,
 * so any frame can be rendered in any order.
 */
(function () {
  "use strict";
  const P = window.__PLAN;
  const W = P.output.width, H = P.output.height, FPS = P.output.fps || 30;

  // ---------- math / easing ----------
  const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
  const lerp = (a, b, k) => a + (b - a) * k;
  const E = {
    linear: k => k,
    out: k => 1 - Math.pow(1 - k, 3),
    in: k => k * k * k,
    inOut: k => (k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2),
    back: k => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(k - 1, 3) + c1 * Math.pow(k - 1, 2); },
    elastic: k => k === 0 || k === 1 ? k : Math.pow(2, -10 * k) * Math.sin((k * 10 - .75) * (2 * Math.PI / 3)) + 1,
  };
  const rand = s => { const x = Math.sin(s * 9301.13 + 49297.7) * 233280; return x - Math.floor(x); };

  // ---------- in/out animations: return {tx,ty,s,r,o,blur,clip} ----------
  function animState(name, k, dir) {
    // k: 0 -> hidden, 1 -> fully shown. dir: "in" | "out"
    const st = { tx: 0, ty: 0, s: 1, r: 0, o: 1, blur: 0, clip: null };
    if (!name || name === "none" || k >= 1) return st;
    const e = E.out(k);
    switch (name) {
      case "fade": st.o = e; break;
      case "pop": st.s = lerp(0.4, 1, dir === "in" ? E.back(k) : e); st.o = clamp(k * 3); break;
      case "bounce": st.s = lerp(0.2, 1, E.elastic(k)); st.o = clamp(k * 4); break;
      case "rise": case "slideUp": st.ty = lerp(60, 0, e); st.o = e; break;
      case "drop": case "slideDown": st.ty = lerp(-60, 0, e); st.o = e; break;
      case "slideLeft": st.tx = lerp(120, 0, e); st.o = e; break;
      case "slideRight": st.tx = lerp(-120, 0, e); st.o = e; break;
      case "scale": st.s = lerp(1.25, 1, e); st.o = e; break;
      case "zoomIn": st.s = lerp(0.6, 1, e); st.o = e; break;
      case "blur": st.blur = lerp(24, 0, e); st.o = e; st.s = lerp(1.08, 1, e); break;
      case "spin": st.r = lerp(-25, 0, E.back(k)); st.s = lerp(.5, 1, E.back(k)); st.o = clamp(k * 3); break;
      case "wipe": st.clip = `inset(0 ${(1 - e) * 100}% 0 0)`; break;
      case "wipeUp": st.clip = `inset(${(1 - e) * 100}% 0 0 0)`; break;
      case "stamp": st.s = lerp(2.2, 1, E.out(k)); st.o = clamp(k * 2); st.r = lerp(-8, 0, e); break;
      case "flip": st.r = 0; st.o = e; st.flip = lerp(90, 0, e); break;
      case "glitch": st.tx = (k < 1 ? (rand(Math.floor(k * 20)) - .5) * 40 * (1 - k) : 0); st.o = k > .15 ? 1 : 0; break;
      default: st.o = e;
    }
    return st;
  }
  function combine(a, b) {
    return { tx: a.tx + b.tx, ty: a.ty + b.ty, s: a.s * b.s, r: a.r + b.r, o: a.o * b.o,
      blur: a.blur + b.blur, clip: a.clip || b.clip, flip: (a.flip || 0) + (b.flip || 0) };
  }
  function applyAnim(node, st, extra) {
    let tf = `translate(${st.tx}px,${st.ty}px) scale(${st.s}) rotate(${st.r}deg)`;
    if (st.flip) tf = `perspective(800px) rotateX(${st.flip}deg) ` + tf;
    if (extra) tf += " " + extra;
    node.style.transform = tf;
    node.style.opacity = st.o;
    node.style.filter = st.blur > 0.05 ? `blur(${st.blur}px)` : "";
    node.style.clipPath = st.clip || "";
  }

  // ---------- helpers ----------
  const h = (tag, cls, parent, html) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html != null) n.innerHTML = html;
    if (parent) parent.appendChild(n);
    return n;
  };
  const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const styleObj = (n, o) => { if (o) for (const k in o) n.style.setProperty(k.startsWith("--") ? k : k.replace(/[A-Z]/g, m => "-" + m.toLowerCase()), o[k]); };
  const px = v => (typeof v === "number" ? v + "px" : v);

  function position(node, el) {
    // x,y are the anchor point in output pixels (default centre of frame)
    const x = el.x != null ? el.x : W / 2, y = el.y != null ? el.y : H / 2;
    const a = el.anchor || "center";
    const ax = a.includes("left") ? 0 : a.includes("right") ? -100 : -50;
    const ay = a.includes("top") ? 0 : a.includes("bottom") ? -100 : -50;
    node.style.left = px(x); node.style.top = px(y);
    node.style.transform = `translate(${ax}%,${ay}%) rotate(${el.rotate || 0}deg)`;
    if (el.w) node.style.width = px(el.w);
    if (el.h) node.style.height = px(el.h);
    if (el.z != null) node.style.zIndex = el.z;
  }

  // Base wrapper shared by all components
  function base(el, root) {
    const outer = h("div", "el el-" + el.type + (el.className ? " " + el.className : ""), root);
    position(outer, el);
    const inner = h("div", "anim", outer);
    styleObj(inner, el.style);
    return { outer, inner };
  }
  function windowState(el, t) {
    const s = el.start != null ? el.start : 0, e = el.end != null ? el.end : P.output.duration + 1;
    if (t < s || t >= e) return null;
    const ind = el.inDur != null ? el.inDur : 0.35, outd = el.outDur != null ? el.outDur : 0.25;
    const kin = ind > 0 ? clamp((t - s) / ind) : 1;
    const kout = outd > 0 ? clamp((e - t) / outd) : 1;
    const st = combine(animState(el.in || "fade", kin, "in"), animState(el.out || "fade", kout, "out"));
    // optional idle motion
    const lt = t - s;
    if (el.float) { st.ty += Math.sin(lt * 2 * Math.PI * (el.floatSpeed || 0.35)) * el.float; }
    if (el.drift) { st.s *= 1 + el.drift * lt; }
    if (el.wobble) { st.r += Math.sin(lt * 6) * el.wobble; }
    return { st, lt, kin, kout, dur: e - s };
  }

  // ---------- components ----------
  const C = {};

  // Captions from transcript words
  C.captions = function (el, root) {
    const words = (el.words || P.words || []).filter(w => w.w && w.w.trim());
    const maxWords = el.maxWords || 3, maxChars = el.maxChars || 22, gap = el.breakGap || 0.45;
    const groups = []; let cur = [];
    const flush = () => { if (cur.length) groups.push(cur); cur = []; };
    words.forEach((w, i) => {
      const prev = words[i - 1];
      const chars = cur.reduce((a, b) => a + b.w.length + 1, 0) + w.w.length;
      if (cur.length && (cur.length >= maxWords || chars > maxChars || (prev && w.start - prev.end > gap))) flush();
      cur.push(w);
      if (/[.!?,;:]$/.test(w.w.trim()) && el.breakOnPunct !== false) flush();
    });
    flush();
    const hold = el.hold != null ? el.hold : 0.5;
    groups.forEach((g, i) => {
      g.s = g[0].start; const next = groups[i + 1];
      g.e = Math.min(g[g.length - 1].end + hold, next ? next[0].start : 1e9);
    });
    const kw = new Set((el.keywords || []).map(s => s.toLowerCase().replace(/[^\p{L}\p{N}']/gu, "")));
    const outer = h("div", "el el-captions " + (el.className || ""), root);
    outer.style.left = el.x != null ? px(el.x) : "50%"; outer.style.top = px(el.y != null ? el.y : H * 0.68);
    outer.style.transform = "translate(-50%,-50%)";
    outer.style.width = px(el.w || W * 0.86);
    const line = h("div", "cap-line", outer);
    styleObj(line, el.style);
    let built = -1, spans = [];
    const clean = s => s.toLowerCase().replace(/[^\p{L}\p{N}']/gu, "");
    const fmt = s => {
      let x = s.trim();
      if (el.stripPunct !== false) x = x.replace(/[.,;:!?"]+$/g, "").replace(/^["]+/, "");
      if (el.uppercase) x = x.toUpperCase();
      if (el.lowercase) x = x.toLowerCase();
      return x;
    };
    if (el.lines) {
      // pre-written lines (e.g. translations): [{text, start, end}]
      let lastLi = -1;
      return {
        layer: el.layer || "front",
        update(t) {
          const li = el.lines.findIndex(l => t >= l.start && t < l.end);
          if (li < 0) { outer.style.display = "none"; return false; }
          outer.style.display = "";
          if (li !== lastLi) { line.innerHTML = ""; h("span", "cap-word is-line", line, esc(fmt(el.lines[li].text))); lastLi = li; }
          applyAnim(line, animState(el.groupIn || "fade", clamp((t - el.lines[li].start) / 0.15), "in"));
          return true;
        }
      };
    }
    return {
      layer: el.layer || "front",
      update(t) {
        const gi = groups.findIndex(g => t >= g.s && t < g.e);
        if (gi < 0) { outer.style.display = "none"; return false; }
        outer.style.display = "";
        const g = groups[gi];
        if (built !== gi) {
          line.innerHTML = ""; spans = g.map(w => {
            const sp = h("span", "cap-word" + (kw.has(clean(w.w)) ? " is-key" : ""), line, esc(fmt(w.w)));
            return sp;
          });
          built = gi;
        }
        const mode = el.mode || "karaoke";
        g.forEach((w, j) => {
          const sp = spans[j];
          const spoken = t >= w.start, active = t >= w.start && (t < w.end + 0.05 || j === g.length - 1 && t < g.e) && !(g[j + 1] && t >= g[j + 1].start);
          let st = { tx: 0, ty: 0, s: 1, r: 0, o: 1, blur: 0, clip: null };
          if (mode === "reveal" || mode === "single") {
            if (!spoken) st.o = 0; else st = animState(el.wordIn || "pop", clamp((t - w.start) / (el.wordInDur || 0.18)), "in");
            if (mode === "single") sp.style.display = active ? "" : "none";
          }
          sp.classList.toggle("is-active", active);
          sp.classList.toggle("is-spoken", spoken);
          if (active && el.activeScale) st.s *= el.activeScale;
          applyAnim(sp, st);
        });
        // group in/out
        const kin = clamp((t - g.s) / (el.groupInDur || 0.12));
        applyAnim(line, animState(el.groupIn || "fade", kin, "in"));
        return true;
      }
    };
  };

  // Generic text: headline, chip, tile, sticker, poster word ...
  C.text = function (el, root) {
    const { outer, inner } = base(el, root);
    const txt = el.uppercase ? String(el.text).toUpperCase() : String(el.text);
    let parts = [];
    if (el.split === "words" || el.split === "chars") {
      // words stay unbroken: each word is a nowrap group; chars animate inside it
      txt.split(/(\s+)/).forEach(tok => {
        if (!tok) return;
        if (/^\s+$/.test(tok)) { inner.appendChild(document.createTextNode(" ")); return; }
        if (el.split === "words") { parts.push(h("span", "unit", inner, esc(tok))); return; }
        const wg = h("span", "word-group", inner);
        wg.style.whiteSpace = "nowrap"; wg.style.display = "inline-block";
        Array.from(tok).forEach(ch => parts.push(h("span", "unit", wg, esc(ch))));
      });
    } else inner.innerHTML = el.html ? el.text : esc(txt).replace(/\n/g, "<br>");
    let fitted = !(el.fit || (el.type === "headline" && el.fit !== false));
    const doFit = () => {
      // shrink font until the text fits its box width (and height if h given)
      const maxW = el.w || W * 0.92, maxH = el.h || 1e9;
      inner.style.whiteSpace = el.wrap ? "pre-line" : "nowrap";
      inner.style.width = "auto"; inner.style.display = "inline-block";
      let fs = parseFloat(getComputedStyle(inner).fontSize), guard = 0;
      while ((inner.scrollWidth > maxW || inner.scrollHeight > maxH) && fs > 12 && guard++ < 60) {
        fs *= 0.92; inner.style.fontSize = fs + "px";
      }
      inner.style.width = ""; inner.style.display = "";
      fitted = true;
    };
    return {
      layer: el.layer || "front",
      update(t) {
        const ws = windowState(el, t);
        if (!ws) { outer.style.display = "none"; return false; }
        outer.style.display = "";
        if (!fitted) doFit();
        applyAnim(inner, ws.st);
        if (parts.length) {
          const stg = el.stagger != null ? el.stagger : 0.06;
          parts.forEach((p, i) => {
            const k = clamp((ws.lt - i * stg) / (el.unitDur || 0.3));
            applyAnim(p, animState(el.unitIn || "rise", k, "in"));
          });
        }
        return true;
      }
    };
  };
  C.headline = C.text; C.chip = C.text; C.sticker = C.text; C.tile = C.text;

  // Card: title/body/list/image/clip
  C.card = function (el, root) {
    const { outer, inner } = base(el, root);
    let media = null, clipC = null;
    if (el.image) { media = h("img", "card-media", inner); media.src = el.image; }
    if (el.clip) { clipC = clipPlayer(el.clip, el.clipOffset || 0, inner, "card-media"); }
    if (el.kicker) h("div", "card-kicker", inner, esc(el.kicker));
    if (el.title) h("div", "card-title", inner, esc(el.title));
    if (el.body) h("div", "card-body", inner, esc(el.body));
    const items = (el.items || []).map((it, i) => {
      const li = h("div", "card-item", inner);
      h("span", "card-mark", li, el.marker || (el.numbered ? String(i + 1) : "✓"));
      h("span", "card-item-text", li, esc(typeof it === "string" ? it : it.text));
      return { li, at: typeof it === "object" && it.at != null ? it.at : null, i };
    });
    return {
      layer: el.layer || "front",
      async update(t) {
        const ws = windowState(el, t);
        if (!ws) { outer.style.display = "none"; return false; }
        outer.style.display = "";
        applyAnim(inner, ws.st);
        items.forEach(o => {
          const at = o.at != null ? o.at : (el.start || 0) + 0.4 + o.i * (el.itemStagger || 0.5);
          const k = clamp((t - at) / 0.3);
          applyAnim(o.li, animState(el.itemIn || "slideLeft", k, "in"));
          o.li.classList.toggle("is-done", t >= at);
        });
        if (clipC) await clipC.seek(t - (el.start || 0));
        return true;
      }
    };
  };

  // Image sequence player for clips declared in plan.clips (extracted by render.py)
  const CLIPS = {};
  (P.clips || []).forEach(c => { CLIPS[c.id] = c; });
  function clipPlayer(id, offset, parent, cls) {
    const c = CLIPS[id];
    const img = h("img", cls || "clip", parent);
    let lastIdx = -1;
    return {
      img,
      async seek(lt) {
        if (!c) return;
        const n = c.frames || 1;
        let idx = Math.floor((lt + offset) * FPS);
        idx = c.loop ? ((idx % n) + n) % n : clamp(idx, 0, n - 1);
        if (idx !== lastIdx) {
          img.src = `${c.dir}/${String(idx + 1).padStart(5, "0")}.jpg`;
          lastIdx = idx;
          try { await img.decode(); } catch (e) { }
        }
      }
    };
  }

  // Clip on screen with optional device frame and 3D motion
  C.clip = function (el, root) {
    const { outer, inner } = base(el, root);
    let host = inner;
    if (el.device) {
      host = h("div", "device device-" + el.device, inner);
      if (el.device === "browser") { const bar = h("div", "device-bar", host); h("i", "", bar); h("i", "", bar); h("i", "", bar); }
      host = h("div", "device-screen", host);
    }
    const player = clipPlayer(el.clip, el.clipOffset || 0, host, "clip-media");
    if (el.image) player.img.src = el.image;
    return {
      layer: el.layer || "front",
      async update(t) {
        const ws = windowState(el, t);
        if (!ws) { outer.style.display = "none"; return false; }
        outer.style.display = "";
        let extra = "";
        const m = el.motion || "none", lt = ws.lt;
        if (m === "flyIn") {
          const k = E.out(clamp(lt / (el.flyDur || 1.2)));
          extra = `perspective(1600px) translateZ(${lerp(-900, 0, k)}px) rotateY(${lerp(-38, el.tiltY || -12, k)}deg) rotateX(${lerp(22, el.tiltX || 6, k)}deg)`;
        } else if (m === "tilt") {
          extra = `perspective(1600px) rotateY(${Math.sin(lt * .6) * 10 + (el.tiltY || -10)}deg) rotateX(${Math.cos(lt * .5) * 4 + (el.tiltX || 5)}deg)`;
        } else if (m === "float") {
          extra = `translateY(${Math.sin(lt * 1.2) * 14}px) rotate(${Math.sin(lt * .8) * 1.5}deg)`;
        } else if (m === "kenburns") {
          extra = `scale(${1 + lt * 0.02})`;
        } else if (m === "orbit") {
          extra = `perspective(1600px) rotateY(${Math.sin(lt * .4) * 25}deg)`;
        }
        applyAnim(inner, ws.st, extra);
        if (!el.image) await player.seek(lt);
        return true;
      }
    };
  };
  C.image = function (el, root) { return C.clip(Object.assign({}, el, { clip: null }), root); };

  // Animated counter
  C.counter = function (el, root) {
    const { outer, inner } = base(el, root);
    const num = h("div", "counter-num", inner);
    if (el.label) h("div", "counter-label", inner, esc(el.label));
    const dec = el.decimals || 0;
    const fmtN = v => (el.prefix || "") + Number(v).toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec }) + (el.suffix || "");
    return {
      layer: el.layer || "front",
      update(t) {
        const ws = windowState(el, t);
        if (!ws) { outer.style.display = "none"; return false; }
        outer.style.display = "";
        applyAnim(inner, ws.st);
        const k = E.out(clamp(ws.lt / (el.countDur || 1.2)));
        num.textContent = fmtN(lerp(el.from || 0, el.to, k));
        return true;
      }
    };
  };

  // Bar chart
  C.bars = function (el, root) {
    const { outer, inner } = base(el, root);
    if (el.title) h("div", "bars-title", inner, esc(el.title));
    const max = el.max || Math.max(...el.items.map(i => i.value));
    const rows = el.items.map(it => {
      const r = h("div", "bar-row", inner);
      h("div", "bar-label", r, esc(it.label));
      const track = h("div", "bar-track", r);
      const fill = h("div", "bar-fill" + (it.highlight ? " is-hi" : ""), track);
      const val = h("div", "bar-value", r);
      return { fill, val, it };
    });
    return {
      layer: el.layer || "front",
      update(t) {
        const ws = windowState(el, t);
        if (!ws) { outer.style.display = "none"; return false; }
        outer.style.display = "";
        applyAnim(inner, ws.st);
        rows.forEach((o, i) => {
          const k = E.out(clamp((ws.lt - 0.2 - i * 0.15) / 0.9));
          o.fill.style.width = (o.it.value / max * 100 * k) + "%";
          o.val.textContent = (el.prefix || "") + Math.round(o.it.value * k).toLocaleString("en-US") + (el.suffix || "");
        });
        return true;
      }
    };
  };

  // Lower third
  C.lowerthird = function (el, root) {
    const e2 = Object.assign({ x: 70, y: H - 360, anchor: "left", in: "slideRight" }, el);
    const { outer, inner } = base(e2, root);
    h("div", "lt-name", inner, esc(el.name));
    if (el.role) h("div", "lt-role", inner, esc(el.role));
    return { layer: el.layer || "front", update(t) { const ws = windowState(e2, t); if (!ws) { outer.style.display = "none"; return false; } outer.style.display = ""; applyAnim(inner, ws.st); return true; } };
  };

  // Full-frame title card
  C.titlecard = function (el, root) {
    const e2 = Object.assign({ x: W / 2, y: H / 2, w: W, h: H }, el);
    const { outer, inner } = base(e2, root);
    if (el.kicker) h("div", "tc-kicker", inner, esc(el.kicker));
    h("div", "tc-title", inner, esc(el.title));
    if (el.subtitle) h("div", "tc-sub", inner, esc(el.subtitle));
    return { layer: el.layer || "front", update(t) { const ws = windowState(e2, t); if (!ws) { outer.style.display = "none"; return false; } outer.style.display = ""; applyAnim(inner, ws.st); return true; } };
  };

  // Decorative shapes (rings, glows, orbits, ribbons, rays, grids, blobs, sparkles...)
  C.shape = function (el, root) {
    const e2 = Object.assign({ x: W / 2, y: H * 0.4, w: W * 0.8, h: W * 0.8, in: "fade", inDur: 0.6 }, el);
    const { outer, inner } = base(e2, root);
    const kind = el.kind || "ring";
    inner.classList.add("shape", "shape-" + kind);
    const c1 = el.color || "var(--c-accent)", c2 = el.color2 || "var(--c-accent2)";
    inner.style.setProperty("--s1", c1); inner.style.setProperty("--s2", c2);
    let svg = null, parts = [];
    if (kind === "orbit" || kind === "sparkles" || kind === "bubbles" || kind === "confetti") {
      const n = el.count || (kind === "orbit" ? 3 : 18);
      for (let i = 0; i < n; i++) parts.push(h("i", "p", inner));
    }
    if (kind === "ribbon") {
      inner.innerHTML = `<svg viewBox="0 0 1000 1000" preserveAspectRatio="none"><defs><linearGradient id="rg${el._i}" x1="0" x2="1"><stop offset="0" stop-color="${c1}"/><stop offset="1" stop-color="${c2}"/></linearGradient></defs><path class="rib" fill="none" stroke="url(#rg${el._i})" stroke-linecap="round"/></svg>`;
      svg = inner.querySelector("path");
    }
    return {
      layer: el.layer || "behind",
      update(t) {
        const ws = windowState(e2, t);
        if (!ws) { outer.style.display = "none"; return false; }
        outer.style.display = "";
        const lt = ws.lt, sp = el.speed || 1;
        let extra = "";
        if (kind === "ring" || kind === "glow") extra = `scale(${1 + Math.sin(lt * 2.2 * sp) * 0.03 + (el.pulseOn || []).reduce((a, p) => a + Math.max(0, 0.12 - Math.abs(t - p) * 0.4), 0)})`;
        if (kind === "rays" || kind === "burst") extra = `rotate(${lt * 12 * sp}deg)`;
        if (kind === "blob") inner.style.borderRadius = `${50 + Math.sin(lt * sp) * 12}% ${50 + Math.cos(lt * 1.3 * sp) * 12}% ${50 + Math.sin(lt * .7 * sp) * 12}% ${50 + Math.cos(lt * .9 * sp) * 12}%`;
        if (kind === "orbit") parts.forEach((p, i) => {
          const a = lt * 1.4 * sp + i * (Math.PI * 2 / parts.length);
          const rx = (e2.w / 2) * 0.92, ry = (e2.h / 2) * 0.32;
          const x = Math.cos(a) * rx, y = Math.sin(a) * ry;
          p.style.transform = `translate(${x}px,${y}px) scale(${0.7 + 0.5 * (Math.sin(a) + 1) / 2})`;
          p.style.opacity = 0.35 + 0.65 * (Math.sin(a) + 1) / 2;
          p.style.zIndex = Math.sin(a) > 0 ? 2 : 0;
        });
        if (kind === "sparkles" || kind === "bubbles" || kind === "confetti") parts.forEach((p, i) => {
          const r1 = rand(i + 1), r2 = rand(i + 7.3), r3 = rand(i + 3.1);
          const life = 2 + r3 * 2, ph = ((lt * sp + r1 * life) % life) / life;
          const x = (r1 - .5) * e2.w, y = (kind === "bubbles" ? (0.5 - ph) : (r2 - .5)) * e2.h + (kind === "confetti" ? ph * e2.h * .5 : 0);
          p.style.transform = `translate(${x}px,${y}px) rotate(${ph * 360 * (kind === "confetti" ? 2 : 0)}deg) scale(${kind === "sparkles" ? Math.sin(ph * Math.PI) : 1})`;
          p.style.opacity = kind === "sparkles" ? Math.sin(ph * Math.PI) : 1 - ph * .6;
        });
        if (svg) {
          const pts = []; for (let i = 0; i <= 40; i++) { const u = i / 40; pts.push(`${u * 1000},${500 + Math.sin(u * 6.2 + lt * 1.6 * sp) * 210 + Math.sin(u * 2.3 - lt * sp) * 90}`); }
          svg.setAttribute("d", "M" + pts.join(" L")); svg.style.strokeWidth = el.thickness || 90;
        }
        applyAnim(inner, ws.st, extra);
        return true;
      }
    };
  };

  // Hand-drawn marks: circle, underline, arrow, box, cross, check, highlight
  C.scribble = function (el, root) {
    const e2 = Object.assign({ w: 360, h: 160, in: "none", out: "fade" }, el);
    const { outer, inner } = base(e2, root);
    const kind = el.kind || "circle";
    const paths = {
      circle: "M 520 90 C 760 80 960 190 940 330 C 920 470 640 520 430 505 C 200 490 40 420 60 290 C 80 160 300 70 560 95",
      underline: "M 20 520 C 260 470 600 490 980 455",
      arrow: "M 40 900 C 200 700 500 520 900 140 M 900 140 L 700 170 M 900 140 L 860 340",
      box: "M 40 60 L 960 50 L 950 560 L 50 570 Z",
      cross: "M 80 80 L 920 920 M 920 80 L 80 920",
      check: "M 80 520 L 380 860 L 940 120",
      highlight: "M 0 500 L 1000 500",
      zigzag: "M 20 500 L 140 380 L 260 600 L 380 380 L 500 600 L 620 380 L 740 600 L 860 380 L 980 500",
    };
    const vb = kind === "circle" || kind === "box" ? "0 0 1000 600" : "0 0 1000 1000";
    inner.innerHTML = `<svg viewBox="${vb}" preserveAspectRatio="none" width="100%" height="100%"><path d="${paths[kind] || paths.circle}" fill="none" stroke="${el.color || "var(--c-mark)"}" stroke-width="${el.strokeWidth || (kind === "highlight" ? 380 : 18)}" stroke-linecap="round" stroke-linejoin="round" vector-effect="${kind === "highlight" ? "" : "non-scaling-stroke"}" ${kind === "highlight" ? 'opacity="0.45"' : ""}/></svg>`;
    const p = inner.querySelector("path");
    const L = 4000;
    p.style.strokeDasharray = L;
    return {
      layer: el.layer || "front",
      update(t) {
        const ws = windowState(e2, t);
        if (!ws) { outer.style.display = "none"; return false; }
        outer.style.display = "";
        const k = E.inOut(clamp(ws.lt / (el.drawDur || 0.5)));
        p.style.strokeDashoffset = L * (1 - k);
        applyAnim(inner, ws.st);
        return true;
      }
    };
  };

  // Progress bar
  C.progress = function (el, root) {
    const outer = h("div", "el el-progress " + (el.className || ""), root);
    const fill = h("div", "progress-fill", outer);
    styleObj(outer, el.style);
    if (el.position === "bottom") { outer.style.bottom = "0"; } else outer.style.top = "0";
    return { layer: el.layer || "front", update(t) { fill.style.width = clamp(t / P.output.duration) * 100 + "%"; return true; } };
  };

  // Background (opaque, for bg layer)
  C.background = function (el, root) {
    const outer = h("div", "el el-background bg-" + (el.kind || "solid") + " " + (el.className || ""), root);
    outer.style.inset = "0";
    styleObj(outer, el.style);
    if (el.image) { outer.style.backgroundImage = `url(${el.image})`; outer.style.backgroundSize = "cover"; outer.style.backgroundPosition = "center"; }
    return {
      layer: el.layer || "bg",
      update(t) {
        if (el.start != null && (t < el.start || t >= (el.end || 1e9))) { outer.style.display = "none"; return false; }
        outer.style.display = "";
        if (el.kind === "mesh" || el.kind === "gradient") outer.style.backgroundPosition = `${50 + Math.sin(t * .3) * 30}% ${50 + Math.cos(t * .25) * 30}%`;
        return true;
      }
    };
  };

  // Emoji burst
  C.burst = function (el, root) {
    const e2 = Object.assign({ w: 10, h: 10, in: "none", out: "none" }, el);
    const { outer, inner } = base(e2, root);
    const chars = Array.from(el.chars || "✨");
    const n = el.count || 8;
    const ps = []; for (let i = 0; i < n; i++) ps.push(h("span", "burst-p", inner, esc(chars[i % chars.length])));
    return {
      layer: el.layer || "front",
      update(t) {
        const ws = windowState(e2, t);
        if (!ws) { outer.style.display = "none"; return false; }
        outer.style.display = "";
        const k = clamp(ws.lt / (el.burstDur || 0.9));
        ps.forEach((p, i) => {
          const a = (i / n) * Math.PI * 2 + rand(i) * 0.6, d = (el.radius || 260) * E.out(k) * (0.7 + rand(i + 2) * 0.5);
          p.style.transform = `translate(${Math.cos(a) * d}px,${Math.sin(a) * d + k * k * 120}px) scale(${lerp(0.3, 1.2, E.back(clamp(k * 2)))}) rotate(${(rand(i + 5) - .5) * 90 * k}deg)`;
          p.style.opacity = 1 - clamp((k - 0.6) / 0.4);
        });
        return true;
      }
    };
  };

  // News ticker
  C.ticker = function (el, root) {
    const outer = h("div", "el el-ticker " + (el.className || ""), root);
    outer.style.top = px(el.y != null ? el.y : H - 140);
    if (el.label) h("div", "ticker-label", outer, esc(el.label));
    const track = h("div", "ticker-track", outer);
    const txt = h("div", "ticker-text", track, esc((el.text + "  •  ").repeat(6)));
    return {
      layer: el.layer || "front",
      update(t) {
        if (el.start != null && (t < el.start || t >= (el.end || 1e9))) { outer.style.display = "none"; return false; }
        outer.style.display = ""; txt.style.transform = `translateX(${-(t * (el.speed || 140)) % 2000}px)`; return true;
      }
    };
  };

  // REC / timecode overlay (VHS, camcorder)
  C.rec = function (el, root) {
    const outer = h("div", "el el-rec " + (el.className || ""), root);
    const dot = h("span", "rec-dot", outer); h("span", "rec-label", outer, esc(el.label || "REC"));
    const tc = h("div", "rec-tc", outer);
    const d0 = el.date || "JAN 01 1997";
    return {
      layer: el.layer || "front",
      update(t) {
        dot.style.opacity = Math.floor(t * 1.5) % 2 ? 0.2 : 1;
        const s = Math.floor(t + (el.offset || 0)); tc.textContent = `${d0}  ${String(Math.floor(s / 3600)).padStart(2, "0")}:${String(Math.floor(s / 60) % 60).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
        return true;
      }
    };
  };

  // Full-screen flash / colour hit
  C.flash = function (el, root) {
    const outer = h("div", "el el-flash", root); outer.style.inset = "0"; outer.style.background = el.color || "#fff";
    const times = el.times || [];
    return {
      layer: el.layer || "front",
      update(t) {
        let o = 0; times.forEach(x => { if (t >= x && t < x + (el.dur || 0.18)) o = Math.max(o, 1 - (t - x) / (el.dur || 0.18)); });
        outer.style.opacity = o * (el.opacity || 0.8); outer.style.display = o > 0 ? "" : "none"; return o > 0;
      }
    };
  };

  // Before / after wipe compare (two images or clips)
  C.compare = function (el, root) {
    const { outer, inner } = base(Object.assign({ w: W * 0.9, h: H * 0.5 }, el), root);
    inner.classList.add("compare");
    const a = h("div", "cmp-a", inner), b = h("div", "cmp-b", inner);
    const ia = h("img", "", a), ib = h("img", "", b);
    if (el.before) ia.src = el.before; if (el.after) ib.src = el.after;
    h("div", "cmp-tag cmp-tag-a", inner, esc(el.beforeLabel || "BEFORE"));
    h("div", "cmp-tag cmp-tag-b", inner, esc(el.afterLabel || "AFTER"));
    const handle = h("div", "cmp-handle", inner);
    return {
      layer: el.layer || "front",
      update(t) {
        const ws = windowState(el, t);
        if (!ws) { outer.style.display = "none"; return false; }
        outer.style.display = "";
        applyAnim(inner, ws.st);
        const k = E.inOut(clamp((ws.lt - (el.wipeDelay || 0.8)) / (el.wipeDur || 1.4)));
        const pos = lerp(100, el.wipeTo != null ? el.wipeTo : 0, k);
        b.style.clipPath = `inset(0 0 0 ${pos}%)`; handle.style.left = pos + "%";
        return true;
      }
    };
  };

  // Audio-reactive-looking bars (deterministic pseudo spectrum)
  C.equalizer = function (el, root) {
    const e2 = Object.assign({ w: W * 0.8, h: 180 }, el);
    const { outer, inner } = base(e2, root); inner.classList.add("eq");
    const n = el.count || 32; const bars = []; for (let i = 0; i < n; i++) bars.push(h("i", "", inner));
    const words = P.words || [];
    return {
      layer: el.layer || "front",
      update(t) {
        const ws = windowState(e2, t); if (!ws) { outer.style.display = "none"; return false; } outer.style.display = "";
        const speaking = words.some(w => t >= w.start && t <= w.end) ? 1 : 0.25;
        bars.forEach((b, i) => { const v = 0.15 + speaking * 0.85 * Math.abs(Math.sin(t * (5 + rand(i) * 9) + i)) * (0.5 + rand(i + 9) * .5); b.style.transform = `scaleY(${v})`; });
        applyAnim(inner, ws.st); return true;
      }
    };
  };

  // Rating stars (only for real reviews supplied by the user)
  C.stars = function (el, root) {
    const { outer, inner } = base(el, root); inner.classList.add("stars");
    const n = el.count || 5, ss = []; for (let i = 0; i < n; i++) ss.push(h("span", "star", inner, "★"));
    return {
      layer: el.layer || "front",
      update(t) {
        const ws = windowState(el, t); if (!ws) { outer.style.display = "none"; return false; } outer.style.display = "";
        applyAnim(inner, ws.st); ss.forEach((s, i) => applyAnim(s, animState("pop", clamp((ws.lt - i * 0.12) / 0.3), "in"))); return true;
      }
    };
  };

  // ---------- build ----------
  const themeVars = P.theme && P.theme.vars;
  if (themeVars) styleObj(document.documentElement, themeVars);
  document.documentElement.style.setProperty("--W", W + "px");
  document.documentElement.style.setProperty("--H", H + "px");
  const roots = {};
  ["bg", "behind", "front"].forEach(l => { roots[l] = h("div", "layer layer-" + l, document.getElementById("stage")); });
  const comps = [];
  (P.elements || []).forEach((el, i) => {
    el._i = i;
    const f = C[el.type];
    if (!f) { console.warn("unknown element type", el.type); return; }
    const layer = el.layer || (el.type === "shape" ? "behind" : el.type === "background" ? "bg" : "front");
    el.layer = layer;
    const c = f(el, roots[layer]);
    c.layer = layer;
    comps.push(c);
  });

  window.__layersUsed = ["bg", "behind", "front"].filter(l => comps.some(c => c.layer === l));
  window.__render = async function (t, layer) {
    Object.keys(roots).forEach(l => { roots[l].style.display = !layer || l === layer ? "" : "none"; });
    let any = false;
    for (const c of comps) {
      if (layer && c.layer !== layer) continue;
      const v = await c.update(t);
      any = any || v;
    }
    return any;
  };
  window.__ready = (document.fonts ? document.fonts.ready : Promise.resolve()).then(() => true);
})();
