// ============================================================
//  FRAME: two pieces of one page, each drawn, then the ink bleeds
// ============================================================
let ENV = { bass: 0, mid: 0, high: 0, air: 0, rms: 0, flux: 0, bflux: 0, hflux: 0, cent: 0 };

function drawPiece(side, st, t) {
  ctx.save();
  const g = st.gap || 0, sh = st.shake || 0;
  const dx = (side === 'L' ? -1 : 1) * g / 2 + (sh ? (hsh(seed, side === 'L' ? 3 : 4) - 0.5) * sh : 0);
  const dy = sh ? (hsh(seed, side === 'L' ? 5 : 6) - 0.5) * sh * 0.6 : 0;
  ctx.translate(dx, dy);
  if (st.tilt) { const px = side === 'L' ? 0 : W; ctx.translate(px, H / 2); ctx.rotate((side === 'L' ? -1 : 1) * st.tilt); ctx.translate(-px, -H / 2); }
  ctx.clip(PIECE[side]);
  flat(0, 0, W, H, C.paper);
  if (st.mirror !== false && side === 'R') { ctx.translate(W, 0); ctx.scale(-1, 1); }
  const cz = (st.cam ? st.cam.z : 1) * (1 + (st.pulse || 0)), ccy = st.cam ? st.cam.cy : 900;
  if (cz !== 1) { ctx.translate(SEAM, ccy); ctx.scale(cz, cz); ctx.translate(-SEAM, -ccy); }
  DRAWON = st.erase > 0 ? { t: (1 - st.erase) * 1.75, dur: 0.2, stagger: 0.0042, k: 0 }          // the inhale: un-drawn, last stroke first
        : st.drawOn != null ? { t: st.drawOn * (st.drawK || 1), dur: 0.2, stagger: 0.0042, k: 0 } : null;
  st.scene(side === 'L' ? 'him' : 'her', st.lt, ENV, st.V, side, t);
  DRAWON = null;
  ctx.restore();
}

function drawContacts() {
  base();
  for (const c of CONTACTS) {
    const bad = c.d > c.tol;
    ctx.strokeStyle = bad ? '#ff0040' : '#00e070'; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.arc(c.a[0], c.a[1], 7, 0, TAU); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(c.b[0] - 9, c.b[1]); ctx.lineTo(c.b[0] + 9, c.b[1]); ctx.stroke();
  }
}

function drawFrame(t, env, opts = {}) {
  ENV = env;
  CONTACTS.length = 0;
  seed = Math.floor(t * DRAW_FPS) + 1; ji = 0; amp = 1.2 + 0.7 * (env.rms || 0);
  const st = opts.canvas ? canvasState(t, env) : timeline(t, env, opts);
  if (opts.noSpots) st.noSpots = true;
  if (opts.noTitle) st.title = 0;
  if (opts.title) { st.title = 1; st.titleA = 1; }
  if (opts.noFlash) st.flash = 0;
  base(); flat(0, 0, W, H, C.black);
  // the dark table under the page; a thin light in the gap when it opens
  if ((st.gap || 0) > 1 && st.gapGlow) glow(SEAM, H * 0.47, 700, `rgba(255,236,200,${st.gapGlow})`, 'rgba(255,236,200,0)');
  if (st.droste) drosteViews(st, t);
  else for (const side of ['L', 'R']) drawPiece(side, st, t);
  base();
  if (st.splash != null) splashMask(st.splash);
  if (st.erase > 0) { ctx.fillStyle = `rgba(237,230,214,${(0.95 * ease(st.erase)).toFixed(3)})`; ctx.fillRect(0, 0, W, H); }   // everything fades to the bare page
  if (st.kaleido && st.kaleido.k > 0) kaleidoViews(st, t);
  if (st.post) st.post(t, st);
  spotsPass(t, st);
  base();
  for (const side of ['L', 'R']) {
    ctx.save(); const g = st.gap || 0; ctx.translate((side === 'L' ? -1 : 1) * g / 2, 0);
    tearEdge(side, 1 - (st.healed || 0), true); ctx.restore();
  }
  if (st.title > 0) titleOverlay(st);
  grain(0.07 + 0.03 * (env.rms || 0));
  base();
  if (st.flash > 0) { ctx.fillStyle = `rgba(245,242,232,${st.flash})`; ctx.fillRect(0, 0, W, H); }
  if (st.fade > 0) { ctx.fillStyle = `rgba(13,12,10,${st.fade})`; ctx.fillRect(0, 0, W, H); }
  if (QA) drawContacts();
  const worst = CONTACTS.reduce((m, c) => c.d > m.d ? c : m, { d: 0, name: '-' });
  return { contacts: CONTACTS.length ? { n: CONTACTS.length, worst: worst.name, d: +worst.d.toFixed(2) } : null };
}

// ---- vector droste: the scene redrawn inside its own heart, level by level (always crisp) ----
function drosteViews(st, t) {
  const { u, hcy, hk } = st.droste;
  const cx = SEAM, cy = hcy + 2.5 * hk;
  const s = (32 * hk * 1.25) / W, Z0 = Math.pow(1 / s, u);
  let prevClip = null;
  for (let L = 0; L < 3; L++) {
    const Z = Z0 * Math.pow(s, L);
    if (Z * 32 * hk < 6) break;
    ctx.save(); base();
    if (prevClip) ctx.clip(prevClip);
    ctx.translate(cx, cy); ctx.scale(Z, Z); ctx.translate(-cx, -cy);
    if (L > 0) flat(-2000, -2000, W + 4000, H + 4000, C.black);
    for (const side of ['L', 'R']) drawPiece(side, st, t);
    ctx.restore();
    // this level's heart, in screen space, becomes the window into the next level
    const hp = new Path2D(); for (let i = 0; i <= 64; i++) { const q = heartPt(i / 64 * TAU, SEAM, hcy, hk); const x = cx + (q[0] - cx) * Z, y = cy + (q[1] - cy) * Z; i ? hp.lineTo(x, y) : hp.moveTo(x, y); } hp.closePath();
    prevClip = hp;
  }
}
// ---- vector kaleidoscope: n mirrored wedges, each a full redraw ----
function kaleidoViews(st, t) {
  const K = st.kaleido, F = fxBufs();
  const n = K.n, a = TAU / n, R = 2600;
  const kx = F.full.getContext('2d');
  withCtx(kx, () => {
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalCompositeOperation = 'source-over'; ctx.globalAlpha = 1; ctx.filter = 'none';
    base(); flat(0, 0, W, H, C.black);
    for (let i = 0; i < n; i++) {
      ctx.save(); base();
      ctx.beginPath(); ctx.moveTo(K.cx, K.cy); ctx.arc(K.cx, K.cy, R, K.rot + i * a - a / 2 - 0.003, K.rot + i * a + a / 2 + 0.003); ctx.closePath(); ctx.clip();
      ctx.translate(K.cx, K.cy); ctx.rotate(K.rot + i * a); if (i % 2) ctx.scale(1, -1); ctx.rotate(-K.rot); ctx.scale(K.zoom, K.zoom); ctx.translate(-K.cx, -K.cy);
      for (const side of ['L', 'R']) drawPiece(side, st, t);
      ctx.restore();
    }
  });
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = K.k; ctx.drawImage(F.full, 0, 0); ctx.restore();
  base();
}

// ---- the title, written on the page: SAME on his half, AS YOU on hers ----
function titleOverlay(st) {
  const hgt = 76, y = st.titleY || 322, lw = LW(1.35), u = st.title;
  const w1 = wordW('SAME', hgt), g = st.gap || 0;
  ctx.save();
  const col = st.titleCol || C.paper;
  ctx.globalAlpha = st.titleA == null ? 1 : st.titleA;
  ctx.save(); ctx.translate(-g / 2, 0); ctx.clip(PIECE.L); word('SAME', SEAM - 26 - w1, y, hgt, col, lw, clamp(u * 2, 0, 1)); ctx.restore();
  ctx.save(); ctx.translate(g / 2, 0); ctx.clip(PIECE.R); word('AS YOU', SEAM + 26, y, hgt, col, lw, clamp(u * 2 - 1, 0, 1)); ctx.restore();
  ctx.restore();
}

// ============================================================
//  modes
// ============================================================
if (RENDER) {
  setSize(+Q.get('w') || 1080, +Q.get('h') || 1920);
  window.__frame = p => drawFrame(p.t, { bass: p.bass || 0, mid: p.mid || 0, high: p.high || 0, air: p.air || 0, rms: p.rms || 0, flux: p.flux || 0, bflux: p.bflux || 0, hflux: p.hflux || 0, cent: p.cent || 0 },
    { canvas: !!p.canvas, noSpots: !!p.noSpots, noTitle: !!p.noTitle, title: !!p.title, noFlash: !!p.noFlash });
  window.__ready = true;
} else {
  // ---------------- live: click → a procedural pad at 120 BPM, or drop the WAV ----------------
  setSize(1080, 1920);
  const hint = document.getElementById('hint');
  let ac = null, analyser = null, buf = null, srcNode = null, startAt = 0, running = false, loopLen = DUR, pad = null;
  const env = { bass: 0, mid: 0, high: 0, air: 0, rms: 0, flux: 0, bflux: 0, hflux: 0, cent: 0 };
  let prevSpec = null;
  const agc = { bass: 1e-3, mid: 1e-3, high: 1e-3, air: 1e-3, rms: 1e-3 };
  function bands() {
    if (!analyser) return;
    const n = analyser.frequencyBinCount, data = new Float32Array(n); analyser.getFloatFrequencyData(data);
    const sr = ac.sampleRate, hz = i => i * sr / 2 / n;
    let b = 0, m = 0, h = 0, a = 0, fl = 0, bfl = 0;
    const cur = new Float32Array(n);
    for (let i = 1; i < n; i++) { const v = Math.pow(10, data[i] / 20); cur[i] = v; const f = hz(i); if (f < 150) b += v; else if (f < 2000) m += v; else if (f < 8000) h += v; else a += v; if (prevSpec) { const d = Math.max(0, v - prevSpec[i]); fl += d; if (f < 150) bfl += d; } }
    prevSpec = cur;
    const td = new Float32Array(analyser.fftSize); analyser.getFloatTimeDomainData(td); let s2 = 0; for (let i = 0; i < td.length; i++) s2 += td[i] * td[i]; const rms = Math.sqrt(s2 / td.length);
    const upd = (k, v) => { agc[k] = Math.max(agc[k] * 0.9995, v); env[k] = clamp(v / agc[k], 0, 1); };
    upd('bass', b); upd('mid', m); upd('high', h); upd('air', a); upd('rms', rms);
    env.flux = clamp(fl / (agc.mid * 0.5 + 1e-6), 0, 1); env.bflux = clamp(bfl / (agc.bass * 0.4 + 1e-6), 0, 1); env.hflux = env.flux;
  }
  function procedural() {
    // a rainy pad + a soft kick on every beat, so the piece is never silent
    pad = ac.createGain(); pad.connect(analyser);   // all of it goes through `pad`: a dropped track disconnects it
    const g = ac.createGain(); g.gain.value = 0.16; g.connect(pad); analyser.connect(ac.destination);
    [146.83, 174.61, 220, 261.63].forEach((f, i) => {
      const o = ac.createOscillator(); o.type = i % 2 ? 'triangle' : 'sine'; o.frequency.value = f * (1 + (i - 1.5) * 0.0015);
      const lg = ac.createGain(); lg.gain.value = 0.22; const lfo = ac.createOscillator(); lfo.frequency.value = 0.06 + i * 0.021; const lgg = ac.createGain(); lgg.gain.value = 0.1; lfo.connect(lgg); lgg.connect(lg.gain); lfo.start();
      o.connect(lg); lg.connect(g); o.start();
    });
    // rain: filtered noise
    const nb = ac.createBuffer(1, ac.sampleRate * 2, ac.sampleRate), nd = nb.getChannelData(0); for (let i = 0; i < nd.length; i++) nd[i] = Math.random() * 2 - 1;
    const ns = ac.createBufferSource(); ns.buffer = nb; ns.loop = true; const bp = ac.createBiquadFilter(); bp.type = 'highpass'; bp.frequency.value = 3000; const ng = ac.createGain(); ng.gain.value = 0.05; ns.connect(bp); bp.connect(ng); ng.connect(pad); ns.start();
    let next = ac.currentTime + 0.1;
    function tick() {
      while (next < ac.currentTime + 0.5) {
        const o = ac.createOscillator(); o.type = 'sine'; o.frequency.setValueAtTime(90, next); o.frequency.exponentialRampToValueAtTime(42, next + 0.18);
        const eg = ac.createGain(); eg.gain.setValueAtTime(0.0001, next); eg.gain.exponentialRampToValueAtTime(0.8, next + 0.008); eg.gain.exponentialRampToValueAtTime(0.0001, next + 0.35);
        o.connect(eg); eg.connect(pad); o.start(next); o.stop(next + 0.4); next += BEAT;
      }
      if (pad) setTimeout(tick, 200);   // until a track is dropped (`running` is still false on the first call)
    }
    tick();
  }
  function start(withBuffer) {
    if (!ac) { ac = new (window.AudioContext || window.webkitAudioContext)(); analyser = ac.createAnalyser(); analyser.fftSize = 2048; analyser.smoothingTimeConstant = 0.6; }
    if (ac.state === 'suspended') ac.resume();
    if (srcNode) { try { srcNode.stop(); } catch (e) { } srcNode.disconnect(); srcNode = null; }
    if (withBuffer) { if (pad) { pad.disconnect(); pad = null; } srcNode = ac.createBufferSource(); srcNode.buffer = buf; srcNode.loop = true; srcNode.connect(analyser); analyser.connect(ac.destination); srcNode.start(); loopLen = buf.duration; }
    else if (!running) procedural();
    startAt = ac.currentTime; running = true; hint.classList.add('off');
  }
  let last = -1;
  function loop() {
    requestAnimationFrame(loop);
    if (!running) { if (last !== -2) { last = -2; drawFrame(0.1, env); } return; }
    const t = ((ac.currentTime - startAt) % loopLen);
    const fi = Math.floor(t * 24); if (fi === last) return; last = fi;
    bands(); drawFrame(t, env);
  }
  cv.addEventListener('click', () => start(!!buf));
  window.addEventListener('dragover', e => e.preventDefault());
  window.addEventListener('drop', async e => {
    e.preventDefault(); const f = e.dataTransfer.files[0]; if (!f) return;
    if (!ac) { ac = new (window.AudioContext || window.webkitAudioContext)(); analyser = ac.createAnalyser(); analyser.fftSize = 2048; analyser.smoothingTimeConstant = 0.6; }
    buf = await ac.decodeAudioData(await f.arrayBuffer()); start(true);
  });
  loop();
}
