// ---------------------------------------------------------------- the camera: straight down, perspective
// The camera hangs straight above the city, so a building's roof is a scaled copy of its
// footprint, pushed out from the middle of the frame -- the lean of the old top-down games. Its
// height is the zoom: low and close on foot, high for the reveals.
const F = 1100;                         // focal length in game pixels (360 px wide frame)
let BW = 360, BH = 640;                 // the game frame (set per output)
const CAM = { x: 0, y: 0, h: 80, shx: 0, shy: 0 };

// camera height by song time: [t, metres]. 360 px at 80 m is 26 m of street.
const CAM_KEYS = [
  [0, 84], [14, 76], [17.4, 84], [25, 96], [28.0, 136], [31, 142], [33.02, 150], [37, 215], [41.5, 245], [45.02, 245],
  [50, 150], [56, 104], [63, 96],
  [75, 80], [100, 120], [130, 70], [180, 160], [200, 90], [250, 110],
  [278.98, 88], [288, 80], [293.5, 72], [298.5, 76], [300.02, 78], [304, 230], [308.5, 430], [312.5, 430],
  [318.02, 150], [324.02, 96], [330, 72], [334.5, 58], [336.02, 52], [337.3, 44], [339.5, 37], [342, 36],
];
function camHeight(t) {
  return kf(t, CAM_KEYS, easeInOut);
}
// where the camera looks: him, plus a little of the way ahead (gone by the stop)
function camTarget(t) {
  const w = walker(t), s = w.s;
  // the chord from 3 m behind him to 6 m ahead: it turns smoothly through a corner (the
  // segments' own directions switch in one frame, and the camera jumped with them)
  const a = routeAt(s - 3).p, b = routeAt(s + 6).p, d = nrm([b[0] - a[0], b[1] - a[1]]);
  const H = camHeight(t), viewH = BH * H / F;
  const ahead = viewH * 0.04 * (1 - step(t, SONG.stop - 9, SONG.stop - 1));
  return [w.p[0] + d[0] * ahead, w.p[1] + d[1] * ahead];
}
function setCamera(t, shake = 0) {
  const c = camTarget(t);
  CAM.x = c[0]; CAM.y = c[1]; CAM.h = camHeight(t);
  CAM.shx = shake ? (hsh(Math.floor(t * 48), 3) - 0.5) * shake : 0;
  CAM.shy = shake ? (hsh(Math.floor(t * 48), 5) - 0.5) * shake : 0;
}
const kAt = z => F / Math.max(0.5, CAM.h - z);
function proj(x, y, z = 0) {
  const k = kAt(z);
  return [BW / 2 + (x - CAM.x) * k + CAM.shx, BH / 2 - (y - CAM.y) * k + CAM.shy];
}
function viewRect(margin = 0) {          // the ground the frame sees, metres
  const k = F / CAM.h, hw = BW / 2 / k + margin, hh = BH / 2 / k + margin;
  return [CAM.x - hw, CAM.y - hh, CAM.x + hw, CAM.y + hh];
}
// a polygon at height z, projected and traced
function tracePoly(ctx, pts, z = 0) {
  ctx.beginPath();
  for (let i = 0; i < pts.length; i++) { const q = proj(pts[i][0], pts[i][1], z); if (i) ctx.lineTo(q[0], q[1]); else ctx.moveTo(q[0], q[1]); }
  ctx.closePath();
}
