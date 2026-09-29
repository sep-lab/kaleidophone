// ============================================================================
// 90_main: three modes off the URL.
//   live   (default): click -> procedural 80 BPM pad/beat, or drop the WAV (analyser drives it)
//   render (?render=1&w=&h=): window.__init(env) then window.__frame(t, opts) per frame
//   cover  (?cover=1): window.__cover(name, w, h) -> still
// ============================================================================
(function () {
  const Q = new URLSearchParams(location.search);
  const canvas = document.getElementById('c'); const ctx = canvas.getContext('2d');
  const MODE = Q.get('render') ? 'render' : Q.get('cover') ? 'cover' : 'live';
  window.__init = function (env) { for (const k in env) ENV[k] = env[k]; ENV.n = env.rms ? env.rms.length : 0; END_HITS = null; };
  window.__frame = function (t, opts) { renderFrame(ctx, canvas.width, canvas.height, t, opts || {}); };
  window.__size = function (w, h) { canvas.width = w; canvas.height = h; };
  window.__draw = function (name, arg) {
    const W = canvas.width, H = canvas.height; ctx.setTransform(1, 0, 0, 1, 0, 0);
    if (name === 'sheet') drawSheetFinal(ctx, W, H, arg && arg.y);
    else if (name === 'expo') drawExpoStill(ctx, W, H, arg.k);
    else if (name === 'frame') renderFrame(ctx, W, H, arg.t, arg.opts || {});
    else if (name === 'cv') drawCoverVariant(ctx, W, H, arg || {});
    else if (name === 'eye') { ctx.fillStyle = '#1b1210'; ctx.fillRect(0, 0, W, H); const k = W / SW; ctx.save(); ctx.scale(k, k); drawEye(ctx, SW / 2, (H / k) / 2, 820 * (arg && arg.s || 1), { t: 3, ocean: 1 }); ctx.restore(); overlayTile(ctx, noiseTile(256, 11, 60, 'fg'), W, H, 0, 0, 0.1, 'overlay'); }
  };
  window.__ready = false;
  const fontsOk = () => Promise.all(['30px "Space Mono"', '700 30px "Space Mono"', '600 30px "Barlow Condensed"', '30px "Permanent Marker"'].map(f => document.fonts.load(f))).then(() => document.fonts.ready);
  fontsOk().then(() => { window.__ready = true; });
  if (MODE === 'render' || MODE === 'cover') {
    canvas.width = +(Q.get('w') || 1080); canvas.height = +(Q.get('h') || 1920);
    document.body.style.background = '#000'; return;
  }
  // ---------------- live ----------------
  const N = Math.ceil(DUR * 100) + 10;
  for (const k of ['bass', 'lowmid', 'mid', 'high', 'air', 'rms', 'flux', 'bflux', 'hflux', 'voc']) ENV[k] = new Float32Array(N);
  let AC = null, an = null, src = null, t0 = 0, playing = false, lastIdx = 0, prevSpec = null, pad = null;
  function fit() { const r = Math.min(innerWidth / 1080, innerHeight / 1920); canvas.style.width = (1080 * r) + 'px'; canvas.style.height = (1920 * r) + 'px'; }
  canvas.width = 1080; canvas.height = 1920; fit(); addEventListener('resize', fit);
  function analyse(t) {
    if (!an) return; const f = new Float32Array(an.frequencyBinCount); an.getFloatFrequencyData(f);
    const bin = hz => Math.min(f.length - 1, Math.round(hz / (AC.sampleRate / 2) * f.length));
    const band = (a, b) => { let s = 0, n = 0; for (let i = bin(a); i <= bin(b); i++) { s += Math.pow(10, f[i] / 20); n++; } return 20 * Math.log10(s / Math.max(1, n) + 1e-9); };
    const nm = (d, lo, hi) => clamp((d - lo) / (hi - lo));
    const v = { bass: nm(band(20, 150), -60, -18), lowmid: nm(band(150, 400), -62, -22), mid: nm(band(400, 2000), -66, -26), high: nm(band(2000, 6000), -72, -32), air: nm(band(6000, 16000), -80, -40) };
    v.rms = clamp(0.25 * v.bass + 0.35 * v.mid + 0.25 * v.lowmid + 0.15 * v.high); v.voc = clamp((v.mid - 0.35) * 1.6);
    let fl = 0, bf = 0; if (prevSpec) { for (let i = 0; i < f.length; i++) { const d = Math.max(0, f[i] - prevSpec[i]); fl += d; if (i < bin(150)) bf += d; } } prevSpec = f;
    v.flux = clamp(fl / 900); v.bflux = clamp(bf / 60); v.hflux = v.flux;
    const idx = Math.max(0, Math.min(N - 1, Math.floor(t * 100)));
    for (let i = Math.min(lastIdx, idx); i <= idx; i++) for (const k in v) ENV[k][i] = v[k];
    lastIdx = idx;
  }
  function loop() {
    const t = playing ? (AC.currentTime - t0) % DUR : 0.01;
    if (playing) analyse(t);
    renderFrame(ctx, canvas.width, canvas.height, playing ? t : 3.2, {});
    if (!playing) { ctx.fillStyle = 'rgba(236,228,210,0.75)'; ctx.font = '30px "Space Mono"'; ctx.textAlign = 'center'; ctx.fillText('click · or drop the track', 540, 1760); }
    requestAnimationFrame(loop);
  }
  function startAC() { if (!AC) { AC = new (window.AudioContext || window.webkitAudioContext)(); an = AC.createAnalyser(); an.fftSize = 2048; an.smoothingTimeConstant = 0.5; an.connect(AC.destination); } }
  function procedural() {
    startAC(); const out = AC.createGain(); out.gain.value = 0.5; out.connect(an); pad = out; t0 = AC.currentTime + 0.1;
    // pad
    for (const hz of [73.4, 110, 146.8, 220]) { const o = AC.createOscillator(), g = AC.createGain(); o.type = 'sawtooth'; o.frequency.value = hz * (1 + (Math.random() - 0.5) * 0.004); const lp = AC.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 700; g.gain.value = 0.035; o.connect(lp).connect(g).connect(out); o.start(); }
    const noise = AC.createBuffer(1, AC.sampleRate * 0.3, AC.sampleRate); const d = noise.getChannelData(0); for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * Math.exp(-i / (AC.sampleRate * 0.06));
    for (let b = 0; b < DUR / BEAT; b++) {
      const tt = t0 + b * BEAT;
      if (b % 4 === 0 || b % 4 === 2) { const o = AC.createOscillator(), g = AC.createGain(); o.frequency.setValueAtTime(120, tt); o.frequency.exponentialRampToValueAtTime(42, tt + 0.25); g.gain.setValueAtTime(0.9, tt); g.gain.exponentialRampToValueAtTime(0.001, tt + 0.4); o.connect(g).connect(out); o.start(tt); o.stop(tt + 0.45); }
      else { const s = AC.createBufferSource(), g = AC.createGain(), hp = AC.createBiquadFilter(); hp.type = 'highpass'; hp.frequency.value = 1200; s.buffer = noise; g.gain.value = 0.5; s.connect(hp).connect(g).connect(out); s.start(tt); }
    }
    playing = true;
  }
  canvas.addEventListener('click', () => { if (!playing) procedural(); });
  addEventListener('dragover', e => e.preventDefault());
  addEventListener('drop', async e => {
    e.preventDefault(); const file = e.dataTransfer.files[0]; if (!file) return; startAC();
    const buf = await AC.decodeAudioData(await file.arrayBuffer());
    if (src) try { src.stop(); } catch (_) { }
    if (pad) { pad.disconnect(); pad = null; }   // the fallback: its pad and every beat it scheduled go through `out`
    src = AC.createBufferSource(); src.buffer = buf; src.connect(an); t0 = AC.currentTime + 0.05; src.start(t0); playing = true; lastIdx = 0;
  });
  fontsOk().then(() => requestAnimationFrame(loop));
})();
