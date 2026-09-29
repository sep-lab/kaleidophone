// SAME AS YOU is a pure function of time: every frame is drawn from (t, envelope at t) alone,
// so any window renders on its own and the default driver (linear 100 Hz sampling) is exact.
// Flags a frame understands: canvas (the Spotify Canvas loop state), noSpots, noTitle, title, noFlash.
const KEYS = ['bass', 'mid', 'high', 'air', 'rms', 'flux', 'bflux', 'hflux', 'cent'];

export default {
  keys: KEYS,
  // Covers are single frames of the film at 3000x5333 with the flash suppressed; the square
  // covers are crops of these portraits.
  async cover(page, name, variant, pack) {
    const { name: _n, t, ...flags } = variant;
    await page.evaluate(q => window.__frame(q), { t, ...this.frame(t, pack, { flags: {} }), ...flags, noFlash: true });
  },
};
