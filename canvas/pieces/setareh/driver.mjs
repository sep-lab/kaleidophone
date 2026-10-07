// SETAREH: a pure function of time, the song pack and the cut. The pack goes in once through __init (the piece
// reads its events -- events.setareh.snare / .line and the cues -- and the vocal stem's envelope from it), and
// every frame is __frame({ t, ...envelope at t, ...flags }); flags.open is the song time the exposure opens at
// (the cut's t0: render.mjs --flags '{"open":89.99}'). Without it the piece opens the cut that contains t.
export default {
  keys: ['bass', 'lowmid', 'mid', 'high', 'air', 'rms', 'flux', 'bflux', 'hflux', 'cent', 'voc'],
  query({ w, h }) { return { render: 1, w, h }; },
  coverQuery({ size }) { return { cover: 1, size }; },
  async init(page, pack) { await page.evaluate(p => window.__init(p), pack); },
  async cover(page, name) { await page.evaluate(v => window.__cover(v), name); },
};
