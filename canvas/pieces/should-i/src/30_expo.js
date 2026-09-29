// ============================================================================
// 30_expo: the 36 exposures (one roll), her long take (the first vocal part),
// and the phone after the roll runs out. All drawn in scene space 900 x 1350.
// Each exposure: bg(ctx) static (cached), fg(ctx, lt, t) animated (lt = time since shown).
// ============================================================================
function expoTime(k) { return T_ROLL0 + 1.5 * (k - 1); }            // shutter k fires here (k = 1..36)
function expoShown(k) { return k === 1 ? T_DROP : expoTime(k - 1); } // composition k is in the viewfinder from here

function interiorDark(ctx, base) { vgrad(ctx, 0, 0, SW, SH, [[0, col(base || [26, 22, 22])], [1, '#0b0909']]); }
function lampBokeh(ctx, t, seed, n, a) { bokehField(ctx, 0, 0, SW, SH * 0.8, n || 10, seed, t, [[255, 184, 110], [255, 150, 90], [255, 215, 160]], 30, 90, a || 0.28); }
function rimW(a) { return `rgba(255,190,120,${a == null ? 0.95 : a})`; }
function rimC(a) { return `rgba(170,205,255,${a == null ? 0.95 : a})`; }
function hallway(ctx, lampX) {
  wallTexture(ctx, 0, 0, SW, SH, [52, 42, 36], 7);
  vgrad(ctx, 0, SH * 0.84, SW, SH * 0.16, [[0, '#231a14'], [1, '#120d0a']]);
  if (lampX != null) { glowAt(ctx, SW * lampX, SH * 0.12, 420, [255, 180, 110], 0.55); ctx.fillStyle = '#ffe6b8'; ell(ctx, SW * lampX, SH * 0.12, 22, 30); ctx.fill(); }
  ctx.fillStyle = radial(ctx, SW / 2, SH * 0.45, 200, 900, [[0, 'rgba(0,0,0,0)'], [1, 'rgba(0,0,0,0.75)']]); ctx.fillRect(0, 0, SW, SH);
}

const EXPO = [null,
  // 1 — the door.
  { bg(c) { hallway(c, 0.18); door(c, 250, 250, 400, 880, { under: 0.8 }); },
    fg(c, lt, t) { glowAt(c, SW / 2, 1136, 300, WARM, 0.12 + 0.18 * envAt('bass', t)); } },
  // 2 — the floor, worn.
  { bg(c) { floorTop(c, { doorLight: 1, phone: true }); c.fillStyle = radial(c, SW / 2, SH * 0.55, 200, 900, [[0, 'rgba(0,0,0,0)'], [1, 'rgba(0,0,0,0.7)']]); c.fillRect(0, 0, SW, SH); },
    fg(c, lt, t) { } },
  // 3 — she laughs.
  { bg(c) { interiorDark(c, [40, 28, 22]); glowAt(c, SW * 0.85, SH * 0.25, 700, [255, 170, 100], 0.55); lampBokeh(c, 0, 3.1, 9, 0.3); },
    fg(c, lt, t) { const k = easeOut(lt / 0.5); bustProfile(c, 250, 330 - 20 * k, 330, { tilt: -0.28 - 0.08 * k, lift: 0.35, flow: -0.2, rim: rimW(), rimDx: 5, rimBlur: 8 }); } },
  // 4 — her phone, dark.
  { bg(c) { interiorDark(c, [18, 20, 30]); glowAt(c, SW * 0.2, SH * 0.2, 800, COLD, 0.35); lampBokeh(c, 0, 9.3, 7, 0.22); },
    fg(c, lt, t) {
      phone(c, SW * 0.5, SH * 0.5, 320, 640, -0.12, { screen: 'off' });
      phoneHand(c, SW * 0.5, SH * 0.5, 320, 640, -0.12, { mirror: true, thumb: 0.2, rim: rimC(0.8), rimDx: -4, rimBlur: 8 });
    } },
  // 5 — a letter under the door.
  { bg(c) { wallTexture(c, 0, 0, SW, SH, [48, 38, 32], 11); door(c, 60, -600, 780, 1560, { under: 1, peephole: false });
      c.fillStyle = '#1a1310'; c.fillRect(0, 962, SW, 400); glowAt(c, SW / 2, 965, 520, WARM, 0.35); },
    fg(c, lt, t) { const k = easeOut(lt / 1.0);
      c.save(); c.translate(SW * 0.5 + 40 - 30 * k, 1030 - 26 * k); c.rotate(-0.08); c.fillStyle = '#e9e0cf'; c.fillRect(-190, -95, 380, 190);
      c.strokeStyle = 'rgba(80,60,40,0.4)'; c.lineWidth = 3; c.beginPath(); c.moveTo(-190, -95); c.lineTo(0, 10); c.lineTo(190, -95); c.stroke();
      c.fillStyle = 'rgba(140,40,40,0.8)'; c.beginPath(); c.arc(0, 10, 16, 0, TAU); c.fill(); c.restore(); } },
  // 6 — the ghost.
  { bg(c) { hallway(c, 0.78); glowAt(c, SW * 0.5, SH * 0.3, 700, [255, 170, 110], 0.25); },
    fg(c, lt, t) { sheetGhost(c, SW * 0.5, 1210, 900, { t: t }); } },
  // 7 — the sheet worn like a veil.
  { bg(c) { interiorDark(c, [30, 28, 34]); glowAt(c, SW * 0.5, SH * 0.1, 900, [220, 225, 255], 0.3); lampBokeh(c, 0, 4.4, 8, 0.2); },
    fg(c, lt, t) {
      bustFront(c, SW / 2, 330, 300, { eyes: 1, rim: rimC(0.7), rimBlur: 10 });
      const g = c.createLinearGradient(SW / 2 - 300, 0, SW / 2 + 300, 0); g.addColorStop(0, '#6f6b70'); g.addColorStop(0.5, '#ebe6dc'); g.addColorStop(1, '#5d5962');
      c.fillStyle = g; blobPath(c, [[SW / 2, 280], [SW / 2 + 150, 300], [SW / 2 + 230, 420], [SW / 2 + 300, 800], [SW / 2 + 360, 1200], [SW / 2 + 300, 1400], [SW / 2 + 190, 1400], [SW / 2 + 170, 900], [SW / 2 + 128, 480],
        [SW / 2, 395], [SW / 2 - 128, 480], [SW / 2 - 170, 900], [SW / 2 - 190, 1400], [SW / 2 - 300, 1400], [SW / 2 - 360, 1200], [SW / 2 - 300, 800], [SW / 2 - 230, 420], [SW / 2 - 150, 300]]); c.fill();
      c.globalAlpha = 0.3; c.strokeStyle = '#8a8480'; c.lineWidth = 4; for (const sg of [-1, 1]) { c.beginPath(); c.moveTo(SW / 2 + sg * 180, 480); c.quadraticCurveTo(SW / 2 + sg * 260, 900, SW / 2 + sg * 250, 1350); c.stroke(); } c.globalAlpha = 1;
    } },
  // 8 — a ring.
  { bg(c) { vgrad(c, 0, 0, SW, SH, [[0, '#2a3148'], [0.5, '#5a5e76'], [1, '#231f2a']]); bokehField(c, 0, 0, SW, SH, 14, 8.8, 0, [[255, 220, 170], [200, 220, 255]], 30, 80, 0.3); },
    fg(c, lt, t) { handOpen(c, SW * 0.5, SH * 0.95, 780, -0.08, { rim: rimW(0.9), rimDx: -6, rimBlur: 10 });
      const rx = SW * 0.5 + 0.075 * 780 * Math.cos(-0.08) + 40, ry = SH * 0.95 - 0.52 * 780;
      const tw = 0.6 + 0.4 * Math.sin(lt * 9); c.save(); c.globalCompositeOperation = 'lighter'; c.strokeStyle = `rgba(255,245,220,${0.8 * tw})`; c.lineWidth = 3;
      for (const a of [0, Math.PI / 2]) { c.beginPath(); c.moveTo(rx - Math.cos(a) * 120 * tw, ry - Math.sin(a) * 120 * tw); c.lineTo(rx + Math.cos(a) * 120 * tw, ry + Math.sin(a) * 120 * tw); c.stroke(); }
      c.restore(); glowAt(c, rx, ry, 90, [255, 240, 210], 0.9 * tw); } },
  // 9 — rain, she stands at the window.
  { bg(c) { nightStreet(c, 0, 0, SW, SH, 0, { lampX: 0.8 }); windowFrame(c, 40, 60, 820, 1230, { cross: true, frame: 30 }); },
    fg(c, lt, t) { rainOnGlass(c, 40, 60, 820, 1230, t, {}); bustProfile(c, 110, 380, 320, { tilt: 0.05, rim: rimC(0.85), rimDx: 4, rimBlur: 8, eye: 0.5 }); } },
  // 10 — her palm on the wet glass.
  { bg(c) { interiorDark(c, [22, 24, 34]); glowAt(c, SW * 0.5, SH * 0.35, 700, [255, 200, 140], 0.4); lampBokeh(c, 0, 1.1, 10, 0.3); },
    fg(c, lt, t) { handOpen(c, SW * 0.52, SH * 0.98, 820, 0.04, { rim: rimW(0.6), rimDx: 0, rimBlur: 16 }); rainOnGlass(c, 0, 0, SW, SH, t, { n: 140 }); } },
  // 11 — on the phone, profile.
  { bg(c) { interiorDark(c, [16, 16, 24]); glowAt(c, SW * 0.1, SH * 0.2, 600, [255, 170, 100], 0.2); },
    fg(c, lt, t) { bustProfile(c, 200, 330, 340, { phone: true, phoneGlow: 0.9 + 0.1 * Math.sin(t * 3), rim: rimW(0.6), rimDx: -5, rimBlur: 10, eye: 0.6 }); } },
  // 12 — the phone face-down.
  { bg(c) { vgrad(c, 0, 0, SW, SH, [[0, '#3a2b20'], [1, '#1a120d']]);
      c.strokeStyle = 'rgba(15,8,4,0.35)'; c.lineWidth = 2; for (let i = 0; i < 40; i++) { c.beginPath(); const y = i * 34 + hash(i) * 10; c.moveTo(0, y); for (let x = 0; x <= SW; x += 60) c.lineTo(x, y + Math.sin(x * 0.01 + i) * 5); c.stroke(); }
      glowAt(c, SW * 0.25, SH * 0.1, 600, WARM, 0.35);
      c.fillStyle = '#e7ddd0'; ell(c, SW * 0.25, SH * 0.24, 110, 110); c.fill(); c.fillStyle = '#3a2416'; ell(c, SW * 0.25, SH * 0.24, 86, 86); c.fill(); },
    fg(c, lt, t) { phone(c, SW * 0.55, SH * 0.56, 330, 660, 0.18, { down: true, edgeGlow: 0.25 + 0.2 * Math.sin(t * 2.5) }); } },
  // 13 — the funfair.
  { bg(c) { vgrad(c, 0, 0, SW, SH, [[0, '#0a0718'], [1, '#261329']]); },
    fg(c, lt, t) { ferrisWheel(c, SW * 0.5, SH * 0.36, 360, t, { bulb: 18 }); c.fillStyle = '#07050a'; c.fillRect(0, SH * 0.86, SW, SH * 0.14);
      figure(c, SW * 0.4, SH * 0.97, 470, { view: 'back', head: -0.18, arms: [[0.1, 0.05], [0.1, 0.05]] }, { rim: 'rgba(255,150,170,0.7)', rimBlur: 12 }); } },
  // 14 — the wheel up close, her profile at the edge.
  { bg(c) { vgrad(c, 0, 0, SW, SH, [[0, '#0b0717'], [1, '#1d0f22']]); },
    fg(c, lt, t) { ferrisWheel(c, SW * 0.72, SH * 0.3, 620, t, { bulb: 34, rot: 0.3 }); bustProfile(c, -40, 520, 360, { rim: 'rgba(255,160,190,0.9)', rimDx: 5, rimBlur: 10, eye: 0.7, tilt: -0.12 }); } },
  // 15 — sunset, she walks away.
  { bg(c) { sunsetSky(c, { sunY: 0.6 }); },
    fg(c, lt, t) { const ph = (t / BEAT) * Math.PI; figure(c, SW * 0.47, SH * 0.93 - lt * 18, 520 - lt * 40, { view: 'back', legs: [[0.25 * Math.sin(ph), 0.2], [-0.25 * Math.sin(ph), 0.2]], arms: [[-0.2 * Math.sin(ph), 0.1], [0.2 * Math.sin(ph), 0.1]] }, { rim: 'rgba(255,190,120,0.9)', rimBlur: 10 }); } },
  // 16 — further, the sun going.
  { bg(c) { sunsetSky(c, { sunY: 0.64 }); },
    fg(c, lt, t) { const ph = (t / BEAT) * Math.PI; figure(c, SW * 0.5, SH * 0.74 - lt * 4, 150 - lt * 10, { view: 'back', legs: [[0.25 * Math.sin(ph), 0.2], [-0.25 * Math.sin(ph), 0.2]] }, { rim: 'rgba(255,200,130,0.9)', rimBlur: 6 }); } },
  // 17 — rooftop, crescent.
  { bg(c) { moonSky(c, 0.14, 0, { mx: 0.7, my: 0.2 }); },
    fg(c, lt, t) { figure(c, SW * 0.32, SH * 0.66, 560, { view: 'side', hipDrop: 0.52, legs: [[1.5, 1.45], [1.45, 1.3]], arms: [[-0.6, -0.2], [-0.5, -0.1]], head: -0.35, dress: true }, { rim: rimC(0.8), rimDx: 3, rimBlur: 6 });
      c.fillStyle = '#05070c'; c.fillRect(-10, SH * 0.66, SW * 0.72, 60); c.fillRect(-10, SH * 0.66, SW * 0.72, SH); } },
  // 18 — half moon.
  { bg(c) { moonSky(c, 0.26, 0, { mx: 0.7, my: 0.2 }); },
    fg(c, lt, t) { figure(c, SW * 0.32, SH * 0.66, 560, { view: 'side', hipDrop: 0.52, legs: [[1.5, 1.45], [1.45, 1.3]], arms: [[-0.6, -0.2], [0.3, 1.2]], head: -0.1, dress: true }, { rim: rimC(0.8), rimDx: 3, rimBlur: 6 });
      c.fillStyle = '#05070c'; c.fillRect(-10, SH * 0.66, SW * 0.72, 60); c.fillRect(-10, SH * 0.66, SW * 0.72, SH); } },
  // 19 — the door, night.
  { bg(c) { hallway(c, null); c.fillStyle = 'rgba(0,0,10,0.45)'; c.fillRect(0, 0, SW, SH); door(c, 250, 250, 400, 880, { under: 0.45 }); },
    fg(c, lt, t) { glowAt(c, SW / 2, 1136, 260, WARM, 0.08 + 0.12 * envAt('bass', t)); } },
  // 20 — through the peephole: nobody.
  { bg(c) { peepholeView(c, {}); }, fg(c, lt, t) { } },
  // 21 — on the phone, facing left.
  { bg(c) { interiorDark(c, [22, 18, 26]); lampBokeh(c, 0, 6.6, 9, 0.25); },
    fg(c, lt, t) { bustProfile(c, 690, 320, 350, { flip: true, phone: true, phoneGlow: 1, rim: rimW(0.55), rimDx: 5, rimBlur: 10, eye: 0.7, tilt: 0.08 }); } },
  // 22 — screen light on her face.
  { bg(c) { c.fillStyle = '#050508'; c.fillRect(0, 0, SW, SH); },
    fg(c, lt, t) { bustProfile(c, 60, 120, 780, { phone: true, phoneGlow: 1.2, rim: rimC(0.9), rimDx: 6, rimBlur: 14, eye: 1 }); glowAt(c, 420, 620, 520, [150, 185, 255], 0.35 + 0.1 * Math.sin(t * 4)); } },
  // 23 — height marks on the door frame.
  { bg(c) { wallTexture(c, 0, 0, SW, SH, [64, 54, 46], 23); glowAt(c, SW * 0.8, SH * 0.1, 800, [255, 200, 140], 0.4);
      c.fillStyle = '#e8dccb'; c.fillRect(SW * 0.12, 0, 120, SH); c.fillStyle = 'rgba(0,0,0,0.25)'; c.fillRect(SW * 0.12 + 104, 0, 16, SH);
      pencilMarks(c, SW * 0.12 + 8, -200, 2200, { n: 8 }); },
    fg(c, lt, t) { bustFront(c, SW * 0.6, 330, 250, { handOnHead: true, eyes: 0.8, rim: rimW(0.7), rimBlur: 12 }); } },
  // 24 — a new mark.
  { bg(c) { wallTexture(c, 0, 0, SW, SH, [70, 58, 48], 24); c.fillStyle = '#ede1cf'; c.fillRect(SW * 0.25, 0, 330, SH); c.fillStyle = 'rgba(0,0,0,0.22)'; c.fillRect(SW * 0.25 + 300, 0, 30, SH); glowAt(c, SW * 0.9, 0, 900, [255, 200, 140], 0.35); },
    fg(c, lt, t) { const k = easeInOut(lt / 1.2);
      const my0 = 200, mh = 700, ny = (my0 + mh * (0.62 - 8 * 0.055 - hash(8 * 3.3) * 0.012)) * 2.6;
      c.save(); c.translate(SW * 0.25 + 20, 0); c.scale(2.6, 2.6); pencilMarks(c, 0, my0, mh, { n: 9, draw: k }); c.restore();
      const px = SW * 0.25 + 20 + 46 * 2.6 * k, py = ny;
      c.save(); c.translate(px, py); c.rotate(-0.9); c.fillStyle = '#2b2522'; c.beginPath(); c.moveTo(0, 0); c.lineTo(-10, -34); c.lineTo(10, -34); c.fill();
      c.fillStyle = '#e8c07a'; c.fillRect(-10, -300, 20, 266); c.fillStyle = '#c2553f'; c.fillRect(-10, -330, 20, 30); c.restore();
      silhouette(c, cc => { cc.save(); cc.translate(px, py); cc.rotate(-0.9); ell(cc, 26, -150, 44, 70, 0.1); cc.fill(); ell(cc, -24, -120, 30, 60, -0.2); cc.fill(); limb(cc, 10, -170, 40, -900, 170, 230); cc.restore(); }, { rim: rimW(0.7), rimBlur: 10 }); } },
  // 25 — she jumps.
  { bg(c) { vgrad(c, 0, 0, SW, SH, [[0, '#1b1624'], [0.7, '#3b2a2e'], [1, '#150f12']]); lampBokeh(c, 0, 2.2, 16, 0.35); glowAt(c, SW / 2, SH * 0.35, 700, [255, 190, 130], 0.35); },
    fg(c, lt, t) { const j = Math.sin(clamp(lt / 1.2) * Math.PI);
      figure(c, SW * 0.47, SH * 0.9 - 120 * j, 700, { view: 'side', lean: -0.12, legs: [[-0.55, -1.5], [0.35, 0.3]], arms: [[2.7, 0.3], [2.3, -0.3]], flare: 0.06, hairLift: 0.8, hairFlow: -0.5, head: -0.25 }, { rim: rimW(0.8), rimDx: -4, rimBlur: 8 });
      c.fillStyle = 'rgba(0,0,0,0.5)'; ell(c, SW * 0.47, SH * 0.905, 120 - 40 * j, 14); c.fill(); } },
  // 26 — his hands.
  { bg(c) { vgrad(c, 0, 0, SW, SH, [[0, '#48505e'], [0.5, '#8e8a86'], [1, '#2a2622']]); windowFrame(c, 110, 60, 680, 900, { frame: 26 }); glowAt(c, SW / 2, SH * 0.35, 700, [255, 240, 220], 0.5); },
    fg(c, lt, t) { handsPray(c, SW / 2, SH * 0.72, 760, { rim: 'rgba(255,240,215,0.95)', rimBlur: 16 });
      c.strokeStyle = 'rgba(255,235,210,0.18)'; c.lineWidth = 3; for (let i = 0; i < 3; i++) { c.beginPath(); c.moveTo(SW / 2 - 60 + i * 30, SH * 0.72 - 700); c.lineTo(SW / 2 - 70 + i * 32, SH * 0.72 - 380); c.stroke(); } } },
  // 27 — the door, ajar.
  { bg(c) { hallway(c, 0.18); c.fillStyle = 'rgba(0,0,10,0.3)'; c.fillRect(0, 0, SW, SH); door(c, 250, 250, 400, 880, { under: 1, open: 0.7 }); glowAt(c, 610, 690, 380, WARM, 0.45); },
    fg(c, lt, t) { } },
  // 28 — the knob, his hand almost there.
  { bg(c) { vgrad(c, 0, 0, SW, SH, [[0, '#3d3129'], [1, '#1b1511']]); c.fillStyle = '#2a211b'; c.fillRect(0, 0, SW * 0.72, SH); c.fillStyle = 'rgba(255,220,180,0.06)'; c.fillRect(40, 120, SW * 0.6, 420);
      c.fillStyle = '#1c1612'; rrect(c, SW * 0.52, SH * 0.3, 110, 330, 14); c.fill();
      c.fillStyle = radial(c, SW * 0.55, SH * 0.4, 5, 150, [[0, '#ffe2a8'], [0.3, '#c0914e'], [1, '#2c1f12']]); c.beginPath(); c.arc(SW * 0.565, SH * 0.42, 120, 0, TAU); c.fill(); glowAt(c, SW * 0.53, SH * 0.39, 70, [255, 230, 190], 0.7); },
    fg(c, lt, t) { const reach = easeInOut(clamp(lt / 1.2)); const tx = SW * 0.565 + 150 + 110 * (1 - reach), ty = SH * 0.42 + 120;
      silhouette(c, cc => { limb(cc, tx, ty, tx + 150, ty + 40, 46, 52); ell(cc, tx + 230, ty + 70, 120, 90, 0.25); cc.fill(); for (let i = 0; i < 3; i++) { limb(cc, tx + 150, ty + 70 + i * 42, tx + 205, ty + 95 + i * 42, 44, 44); } limb(cc, tx + 270, ty + 120, tx + 700, ty + 600, 220, 260); }, { rim: rimW(0.7), rimBlur: 10 }); } },
  // 29 — the ghost at the open door.
  { bg(c) { vgrad(c, 0, 0, SW, SH, [[0, '#ffd9a0'], [0.6, '#f0a868'], [1, '#6a3f22']]); glowAt(c, SW / 2, SH * 0.4, 900, [255, 230, 190], 0.6);
      c.fillStyle = '#1a1310'; c.fillRect(0, 0, 150, SH); c.fillRect(SW - 150, 0, 150, SH); c.fillRect(0, 0, SW, 90); },
    fg(c, lt, t) { sheetGhost(c, SW / 2, SH * 0.95, 980, { t: t, light: [255, 226, 190] }); } },
  // 30 — the empty sheet on the floor.
  { bg(c) { vgrad(c, 0, 0, SW, SH, [[0, '#2a1d15'], [1, '#0f0a07']]); c.save(); c.globalCompositeOperation = 'lighter'; c.fillStyle = 'rgba(255,190,120,0.35)'; c.beginPath(); c.moveTo(SW * 0.3, 0); c.lineTo(SW * 0.7, 0); c.lineTo(SW * 1.1, SH); c.lineTo(SW * -0.1, SH); c.fill(); c.restore(); },
    fg(c, lt, t) { sheetOnFloor(c, SW * 0.5, SH * 0.66, 470, { light: [240, 210, 180] }); } },
  // 31 — a missed shot: she turned away (motion smear, tilted).
  { bg(c) { c.save(); c.translate(SW / 2, SH / 2); c.rotate(0.22); c.translate(-SW / 2, -SH / 2); hallway(c, 0.6); glowAt(c, SW * 0.5, SH * 0.4, 800, [255, 200, 140], 0.5); c.restore(); },
    fg(c, lt, t) { c.save(); c.translate(SW / 2, SH / 2); c.rotate(0.22); c.translate(-SW / 2, -SH / 2);
      for (let i = 0; i < 7; i++) { c.globalAlpha = 0.3; figure(c, SW * 0.35 + i * 38, SH * 0.98, 900, { view: 'side', flip: true, lean: -0.08, head: 0.2, hairFlow: 0.9, arms: [[0.4, 0.3], [-0.3, 0.2]], legs: [[0.3, 0.2], [-0.3, 0.3]] }, {}); }
      c.globalAlpha = 1; c.restore(); } },
  // 32 — underexposed, a light leak.
  { bg(c) { c.fillStyle = '#060404'; c.fillRect(0, 0, SW, SH); bustProfile(c, 240, 360, 330, { dark: '#020101' }); },
    fg(c, lt, t) { c.save(); c.globalCompositeOperation = 'lighter'; const g = c.createLinearGradient(SW, 0, SW * 0.55, 0); g.addColorStop(0, 'rgba(255,90,30,0.85)'); g.addColorStop(0.4, 'rgba(255,140,40,0.35)'); g.addColorStop(1, 'rgba(255,140,40,0)'); c.fillStyle = g; c.fillRect(0, 0, SW, SH); c.restore(); } },
  // 33 — hand on her heart.
  { bg(c) { interiorDark(c, [30, 24, 30]); glowAt(c, SW * 0.5, SH * 0.2, 900, [255, 180, 150], 0.4); lampBokeh(c, 0, 5.5, 8, 0.2); },
    fg(c, lt, t) { bustFront(c, SW / 2, 300, 300, { heart: true, eyes: 0.9, rim: rimW(0.75), rimBlur: 12 }); glowAt(c, SW / 2 + 6, 300 + 1.8 * 300, 180, [255, 90, 90], 0.25 + 0.25 * envAt('bass', t)); } },
  // 34 — hands on her head.
  { bg(c) { interiorDark(c, [24, 26, 34]); glowAt(c, SW * 0.5, SH * 0.1, 900, [190, 210, 255], 0.35); },
    fg(c, lt, t) { bustFront(c, SW / 2, 330, 290, { handsOnHead: true, eyes: 0.6, rim: rimC(0.8), rimBlur: 12 }); } },
  // 35 — her face, close.
  { bg(c) { vgrad(c, 0, 0, SW, SH, [[0, '#1a2238'], [1, '#0a0c14']]); glowAt(c, SW * 0.95, SH * 0.35, 900, [150, 190, 255], 0.45); },
    fg(c, lt, t) { bustProfile(c, -120, 60, 1150, { rim: rimC(0.95), rimDx: 7, rimBlur: 16, tilt: 0.02 });
      const ex = -120 + 0.31 * 1150 + 0.02 * 1150 * 0, ey = 60 + 0.445 * 1150; glowAt(c, ex, ey, 60, [120, 190, 255], 0.9); c.fillStyle = 'rgba(90,170,235,0.9)'; ell(c, ex, ey, 20, 14); c.fill(); c.fillStyle = '#fff'; ell(c, ex + 5, ey - 4, 5, 4); c.fill(); } },
  // 36 — her eye, into the lens.
  { bg(c) { c.fillStyle = '#1b1210'; c.fillRect(0, 0, SW, SH); },
    fg(c, lt, t, o) { drawEye(c, SW / 2, SH * 0.5, 820, { t: t, ocean: 1, blink: (o && o.blink) || 0, look: (o && o.look) || [0, 0] }); } },
];

// ---- a hand holding a phone: fingertips hooked over one edge, thumb on the other
function phoneHand(ctx, cx, cy, w, h, rot, o) {
  o = o || {}; const sg = o.mirror ? -1 : 1;
  silhouette(ctx, cc => { cc.save(); cc.translate(cx, cy); cc.rotate(rot); cc.scale(sg, 1);
    // four fingertips over the left edge
    for (let i = 0; i < 4; i++) { const fy = -h * 0.08 + i * h * 0.105, L = w * (0.2 - Math.abs(i - 1.3) * 0.02); limb(cc, -w * 0.58, fy + h * 0.02, -w * 0.5 + L, fy, w * 0.13, w * 0.115); }
    // palm + wrist under the phone, exiting the bottom
    blobPath(cc, [[-w * 0.62, -h * 0.12], [-w * 0.45, h * 0.3], [-w * 0.2, h * 0.52], [w * 0.25, h * 0.55], [w * 0.62, h * 0.35], [w * 0.8, h * 0.9], [w * 0.2, h * 1.4], [-w * 0.6, h * 1.3], [-w * 0.72, h * 0.4]]); cc.fill();
    // thumb reaching over the right edge onto the screen
    const tk = o.thumb == null ? 0.5 : o.thumb;
    limb(cc, w * 0.62, h * 0.3, lerp(w * 0.45, w * 0.1, tk), lerp(h * 0.12, h * 0.25, tk), w * 0.2, w * 0.15);
    cc.restore(); }, o);
}
// ---- cached static layers (LRU) ------------------------------------------
const BGCACHE = new Map();
function expoBG(k, S) {
  const key = k + '@' + S; if (BGCACHE.has(key)) { const v = BGCACHE.get(key); BGCACHE.delete(key); BGCACHE.set(key, v); return v; }
  const c = mkCanvas(SW * S, SH * S), x = c.getContext('2d'); x.scale(S, S); EXPO[k].bg(x);
  BGCACHE.set(key, c); while (BGCACHE.size > 10) BGCACHE.delete(BGCACHE.keys().next().value);
  return c;
}
// draw exposure k into a scene-space context (already scaled so that 1 unit = 1 scene px)
function drawExpo(ctx, k, t, S, o) {
  const lt = Math.max(0, t - expoShown(k));
  ctx.drawImage(expoBG(k, S), 0, 0, SW, SH);
  EXPO[k].fg(ctx, lt, t, o);
}

// ---- her long take (the first vocal part): the snowy window -----------------------
// turn: 0 profile .. 1 facing the lens
function herTurn(t) {
  const turns = [[16.3, 18.6, 20.2], [31.0, 33.0, 34.6], [38.4, 45.8, 47.2]]; // [start, hold until, back by]
  let v = 0; for (const [a, b, c2] of turns) { if (t >= a && t < c2) v = Math.max(v, t < a + 0.6 ? smooth(a, a + 0.6, t) : t < b ? 1 : 1 - smooth(b, c2, t)); }
  return v;
}
function breathAt(t) { let f = 0; for (let d = 0; d < 2.2; d += 0.1) f = Math.max(f, vocAt(t - d) * Math.exp(-d / 0.7)); return f; }
function drawHerTake(ctx, t, S) {
  // her face sits in the focusing circle; the snowy window is just past her nose
  const wx = 470, burn = smooth(42.6, 45.5, t) * (1 - smooth(47.5, 50, t));
  nightStreet(ctx, wx, 0, SW - wx, SH, t, { lampX: 0.62 });
  snowfall(ctx, wx, 0, SW - wx, SH, t, 60, 1.7, false);
  snowfall(ctx, wx, 0, SW - wx, SH, t * 1.4, 10, 9.1, true);
  vgrad(ctx, 0, 0, wx, SH, [[0, '#3a2a20'], [1, '#150e0b']]);
  glowAt(ctx, -40, SH * 0.36, 760, [255, 170, 100], 0.55 + 0.1 * envAt('lowmid', t));
  ctx.fillStyle = '#110d0b'; ctx.fillRect(wx - 6, 0, 30, SH); ctx.fillRect(wx + (SW - wx) * 0.62, 0, 22, SH);
  ctx.fillStyle = 'rgba(160,170,195,0.35)'; ctx.fillRect(wx + 24, SH * 0.885, SW, 10); ctx.fillStyle = '#110d0b'; ctx.fillRect(wx - 6, SH * 0.895, SW, SH);
  const tr = herTurn(t);
  const hx = 250, hy = 470, hs = 330, breathe = Math.sin(t * 1.3) * 3;
  if (tr < 0.99) { ctx.save(); ctx.globalAlpha = 1 - smooth(0.35, 0.75, tr); const px = hx + 0.05 * hs; ctx.translate(px, 0); ctx.scale(1 - 0.55 * tr, 1); ctx.translate(-px + 130 * tr, 0);
    bustProfile(ctx, hx, hy + breathe, hs, { tilt: 0.04 + 0.05 * Math.sin(t * 0.4), rim: rimC(0.9), rimDx: 5, rimBlur: 9, rim2: rimW(0.7), rim2Dx: -8, rim2Blur: 18, eye: 0.6 }); ctx.restore(); }
  if (tr > 0.01) { ctx.save(); ctx.globalAlpha = smooth(0.3, 0.7, tr); const fx = lerp(hx + 0.03 * hs, 400, tr); ctx.translate(fx, 0); ctx.scale(0.55 + 0.45 * tr, 1); ctx.translate(-fx, 0);
    bustFront(ctx, fx, hy - 10 + breathe, hs, { eyes: smooth(0.6, 1, tr), rim: rimW(0.65), rimBlur: 14 }); ctx.restore(); }
  // breath fog on the glass, pulsing with her voice
  const b = breathAt(t) * (1 - tr);
  ctx.save(); ctx.beginPath(); ctx.rect(wx + 24, 0, SW, SH); ctx.clip(); breathFog(ctx, wx + 58, hy + 0.68 * hs, 40 + 80 * b, clamp(b * 1.15)); ctx.restore();
  if (burn > 0) { ctx.save(); ctx.globalCompositeOperation = 'lighter'; const g = ctx.createLinearGradient(0, 0, SW * 0.8, 0); g.addColorStop(0, `rgba(255,60,30,${0.75 * burn})`); g.addColorStop(0.5, `rgba(255,110,40,${0.3 * burn})`); g.addColorStop(1, 'rgba(255,110,40,0)'); ctx.fillStyle = g; ctx.fillRect(0, 0, SW, SH); ctx.restore(); }
  const melt = smooth(35.5, 37.0, t) * (1 - smooth(38.5, 40, t));
  if (melt > 0) glowAt(ctx, hx + 120, hy + 200, 700, [255, 200, 150], 0.4 * melt);
}

// ---- after the roll: his phone in the viewfinder ---------------------------
function drawPhoneScene(ctx, t, S, st) {
  // st: {screen, typed, del, callPulse, press}
  vgrad(ctx, 0, 0, SW, SH, [[0, '#1b1512'], [1, '#0a0807']]);
  lampBokeh(ctx, t, 7.7, 10, 0.18);
  glowAt(ctx, SW * 0.5, SH * 0.5, 700, [120, 150, 220], 0.25 + (st.press || 0) * 0.6);
  const PY = SH * 0.5 - 235; glowAt(ctx, SW * 0.5, PY + 300, 900, [110, 140, 220], 0.35);
  phone(ctx, SW * 0.5, PY, 470, 940, -0.04, Object.assign({ t }, st));
  phoneHand(ctx, SW * 0.5, PY, 470, 940, -0.04, { thumb: st.screen === 'call' ? 0.35 + 0.5 * (st.press || 0) : 0.15 + 0.1 * Math.sin(t * 9) * (st.typed < 1 ? 1 : 0), rim: rimC(0.5), rimBlur: 10 });
}

// ---- frame 37: the door is open and she is there (the last shot, on the last vocal line)
function drawDoorway(ctx, t, o) {
  o = o || {};
  const hs = 270, crown = 548;                                      // her face lands in the focusing circle
  const dx = 60, dw = SW - 120, dy = 205, dh = SH - dy;
  vgrad(ctx, 0, 0, SW, SH, [[0, '#110c0a'], [1, '#060404']]);
  wallTexture(ctx, 0, 0, SW, dy, [22, 17, 15], 37); ctx.fillStyle = 'rgba(0,0,0,0.35)'; ctx.fillRect(0, 0, SW, dy);
  // light from the room beyond
  const g = ctx.createRadialGradient(SW / 2, dy + dh * 0.3, 10, SW / 2, dy + dh * 0.34, dh * 0.72);
  g.addColorStop(0, '#fff8e8'); g.addColorStop(0.28, '#ffe0b0'); g.addColorStop(0.7, '#ec9d5a'); g.addColorStop(1, '#8a4b25');
  ctx.fillStyle = g; ctx.fillRect(dx, dy, dw, dh);
  bokeh(ctx, dx + dw * 0.14, dy + 150, 78, [255, 238, 205], 0.55);
  bokeh(ctx, dx + dw * 0.9, dy + 330, 52, [255, 214, 165], 0.42);
  bokeh(ctx, dx + dw * 0.76, dy + 110, 34, [255, 226, 190], 0.35);
  // the door, swung open against the left jamb
  ctx.fillStyle = '#2a1d15'; ctx.beginPath(); ctx.moveTo(dx, dy); ctx.lineTo(dx + 96, dy + 52); ctx.lineTo(dx + 96, SH); ctx.lineTo(dx, SH); ctx.fill();
  ctx.fillStyle = 'rgba(255,210,150,0.2)'; ctx.fillRect(dx + 90, dy + 52, 6, SH - dy);
  const cw = 44; ctx.fillStyle = '#1b1310'; ctx.fillRect(dx - cw, dy - cw, dw + cw * 2, cw); ctx.fillRect(dx - cw, dy - cw, cw, SH); ctx.fillRect(dx + dw, dy - cw, cw, SH);
  ctx.fillStyle = 'rgba(255,200,140,0.14)'; ctx.fillRect(dx - 4, dy, 4, SH); ctx.fillRect(dx + dw, dy, 4, SH);
  glowAt(ctx, SW / 2, dy + dh * 0.32, dh * 0.72, [255, 190, 120], 0.32);
  for (let i = 0; i < 30; i++) { const px = dx + hash(i * 3.7) * dw, py = dy + ((hash(i * 1.9) * dh + t * (6 + hash(i) * 10)) % dh); ctx.fillStyle = `rgba(255,240,215,${0.22 + 0.35 * hash(i + 4)})`; ctx.beginPath(); ctx.arc(px + Math.sin(t * 0.7 + i) * 6, py, 1.5 + hash(i + 7) * 2.6, 0, TAU); ctx.fill(); }
  // her, facing him, backlit; the body continues past the bottom of the frame
  const breathe = Math.sin(t * 1.4) * 2;
  silhouette(ctx, c => { c.beginPath(); c.moveTo(SW / 2 - 0.868 * hs, crown + 1.9 * hs + breathe); c.lineTo(SW / 2 + 0.868 * hs, crown + 1.9 * hs + breathe); c.lineTo(SW / 2 + 0.9 * hs, SH + 40); c.lineTo(SW / 2 - 0.9 * hs, SH + 40); c.fill(); }, { rim: 'rgba(255,215,165,0.95)', rimBlur: 22 });
  ctx.save(); ctx.beginPath(); ctx.rect(0, 0, SW, crown + 2.1 * hs + breathe); ctx.clip();
  bustFront(ctx, SW / 2, crown + breathe, hs, { flow: 0.06 * Math.sin(t * 0.6), tilt: 0.015 * Math.sin(t * 0.8), eyes: 1, rim: 'rgba(255,215,165,0.95)', rimBlur: 22 });
  ctx.restore();
}
