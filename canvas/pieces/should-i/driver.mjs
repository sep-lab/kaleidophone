// SHOULD I ? takes the whole song pack once (window.__init: the 100 Hz envelopes plus the vocal
// envelope `voc`), then draws any t on demand: __frame(t, { cardT0 }). Its vocal onsets are baked
// into the HTML at build time (__STUTTER__, from the song pack's events.stutter) so the live mode
// has them too. Pure function of time -> windows render independently, in parallel.
export default {
  async init(page, pack) {
    const env = {};
    for (const [k, v] of Object.entries(pack)) if (k !== 'events') env[k] = v;
    await page.evaluate(e => window.__init(e), env);
  },
  frame(t, pack, opts) { return { t, cardT0: opts.card ? opts.t0 : null }; },
  async draw(page, p) { await page.evaluate(q => window.__frame(q.t, { cardT0: q.cardT0 }), p); },
  async cover(page, name, arg, pack, variant) {
    await page.evaluate(([n, a]) => window.__draw(n, a), [variant.draw || 'cv', variant.arg || {}]);
  },
};
