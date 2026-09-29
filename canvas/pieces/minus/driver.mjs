// ( - ) is a pure function of time: __frame({ t, bass, mid, high, rms, flux, card }).
// `card: true` replaces the frame with the hand-drawn title -- the signature card that opens the
// reel and the story (one bar, 2.4 s at 100 BPM), so the platform's auto-picked cover is the title
// and not a mid-scene frame. `render.mjs --card` turns it on for the first bar of the window.
// Covers have their own mode (?cover=1&size=N -> window.__cover(variant)), which draws the
// portrait composition through a setTransform crop onto a square canvas (docs/TECHNIQUES.md,
// "square cover = crop of the portrait").
import { sampleLinear } from '../../tools/lib/common.mjs';

const KEYS = ['bass', 'mid', 'high', 'rms', 'flux'];
const CARD_SECONDS = 2.4;

export default {
  keys: KEYS,
  frame(t, pack, opts) {
    const card = !!opts.card && t - (opts.t0 || 0) < CARD_SECONDS - 1e-9;
    return { t, ...sampleLinear(pack, KEYS, t), ...(opts.flags || {}), card };
  },
  coverQuery({ size }) { return { cover: 1, size }; },
  async cover(page, name) { await page.evaluate(v => window.__cover(v), name); },
};
