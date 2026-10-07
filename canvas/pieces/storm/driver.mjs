// ⛈️ is a pure function of time and the song pack. The whole pack goes to the page once
// (window.__init): the envelopes, and the storm's events -- the intro's thunder, the kicks and
// snares, the strikes -- which __init hands to EV. The same events are baked into the build
// (__STORM__, piece.json "bake") so the live page has them when the track is dropped on it.
export default {
  keys: ['bass', 'lowmid', 'mid', 'high', 'air', 'rms', 'flux', 'bflux', 'hflux'],
  query({ w, h }) { return { render: 1, w, h }; },
  coverQuery({ size }) { return { cover: 1, size }; },
  async init(page, pack) { await page.evaluate(p => window.__init(p), pack); },
  async cover(page, name) { await page.evaluate(v => window.__cover(v), name); },
};
