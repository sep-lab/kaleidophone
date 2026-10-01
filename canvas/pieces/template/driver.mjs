// The template uses the lib's live.js bootstrap, which accepts both driving styles:
// __init(songPack) once, and __frame({ t, ...envelope at t, ...flags }) per frame.
// It is a pure function of time, so the default driver (linear 100 Hz sampling) is exact. The pack
// sent to __init matters too: on twos, the piece re-reads it at each drawing's time (ink.js heldEnv),
// so both frames of a drawing see the same music, and its events (events.midi.kick, .snare) become
// EV, which the lamp and the nod read. A variant (--variant ending=lamp) reaches the page as
// p.variant through the default frame(); boot() checks it against the piece's declared endings.
export default {
  keys: ['bass', 'lowmid', 'mid', 'high', 'air', 'rms', 'flux', 'bflux', 'hflux', 'cent'],
  query({ w, h }) { return { render: 1, w, h }; },
  coverQuery({ size }) { return { cover: 1, size }; },
  async init(page, pack) { await page.evaluate(p => window.__init(p), pack); },
  async cover(page, name) { await page.evaluate(v => window.__cover(v), name); },
};
