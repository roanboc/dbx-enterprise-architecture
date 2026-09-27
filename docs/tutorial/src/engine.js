/* The tour's engine: every frame is a function of time.
 *
 * The narration (narration.json) and the voiced length of each line (vodur.json) make the
 * timeline; scenes.js says what each scene shows. A screen of the application is one of the
 * shots the capture took (shots.json), drawn in a browser window: the camera moves in on the
 * control the narration names, a ring marks it, and a pointer presses what the narration
 * presses. The chapters that are not screens are drawn here, with one small kit of cards,
 * icons and type. `renderAt(t)` draws the moment t and hands back the frame; `filmInfo()`
 * says when everything happens, for the voice, the sound and the captions. */
const W = 1920, H = 1080;
const WIN = { x: 160, y: 26, w: 1600, bar: 38 };
const CY = WIN.y + WIN.bar, CH = 900; // the window's content: one screen of the application
const GAP = 0.75, LEAD = 0.8, TAIL = 1.2, FADE = 0.5, MOVE = 1.5;
const C = {
  ink: '#1b2240', dim: '#56607f', faint: '#8a93b0', indigo: '#4c6ef5', deep: '#364fc7', pale: '#edf2ff',
  bg1: '#f4f6fc', bg2: '#e2e8f8', card: '#ffffff', line: '#d6dcef', red: '#e03131', green: '#2f9e44',
  amber: '#f59f00', shadow: 'rgba(27, 34, 64, 0.16)',
};
const SANS = 'Manrope, sans-serif', MONO = '"IBM Plex Mono", monospace';

const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
const lerp = (a, b, t) => a + (b - a) * t;
const ease = x => (x <= 0 ? 0 : x >= 1 ? 1 : 0.5 - 0.5 * Math.cos(Math.PI * x));
/** 0 before `at`, 1 once `d` seconds have passed, eased between. */
const rise = (t, at, d = 0.6) => ease((t - at) / d);

let canvas, ctx, TL, IMG = {};

// ------------------------------------------------------------------ the timeline

function buildTimeline() {
  let t = 0;
  const scenes = [], caps = [], chapters = [], clicks = [];
  for (const sc of NARRATION.scenes) {
    const s = { id: sc.id, chapter: sc.chapter, start: t, cues: {} };
    if (!chapters.length || chapters[chapters.length - 1].name !== sc.chapter) chapters.push({ name: sc.chapter, start: t });
    let u = sc.lead ?? LEAD;
    for (const ln of sc.lines) {
      u += ln.pause || 0;
      const d = VODUR[sc.id + '/' + ln.id] ?? Math.max(1.4, ln.text.split(/\s+/).length / 2.6);
      s.cues[ln.id] = u;
      caps.push({ sid: sc.id, id: ln.id, s: t + u, e: t + u + d, text: ln.text });
      u += d + (ln.gap ?? GAP) + (ln.hold || 0);
    }
    s.cues.end = u;
    u += sc.tail ?? TAIL;
    s.dur = u;
    const def = SCENES[sc.id];
    if (def && def.beats) {
      s.states = states(def.beats, s.cues);
      for (const st of s.states) if (st.click) clicks.push(t + st.click.at);
    }
    scenes.push(s);
    t += u;
  }
  return { total: t, scenes, caps, chapters, clicks };
}

/** A scene's beats as the states the screen passes through, each from its own moment. */
function states(beats, cues) {
  const out = [];
  let last = null;
  const resolve = b => (b && typeof b.focus === 'function' ? { ...b, focus: b.focus() } : b);
  for (const raw of beats) {
    const b = resolve(raw);
    if (b.then) b.then = resolve(b.then);
    if (!(b.at in cues)) throw new Error('no cue ' + b.at);
    const at = cues[b.at] + (b.off || 0);
    if (b.click) {
      if (!last) throw new Error('a click needs a screen to press on');
      const press = at + (b.move ?? 1.2);
      last.click = { at: press, from: at, region: b.click };
      if (b.then) {
        last = { t: press + 0.3, cut: true, ...b.then };
        out.push(last);
      }
    } else {
      last = { t: at, cut: !last || last.shot !== b.shot, ...b };
      out.push(last);
    }
  }
  return out;
}

// ------------------------------------------------------------------ the camera

function region(shot, name) {
  const S = SHOTS[shot];
  if (!S) throw new Error('no shot ' + shot);
  if (Array.isArray(name)) return name;
  if (!name || name === 'all') return [0, 0, S.w, Math.min(S.h, CH)];
  const r = S.regions[name];
  if (!r) throw new Error('no region ' + name + ' in ' + shot);
  return r;
}

/** Where the camera stands to show a region: as close as `zoom` allows, and never past the picture. */
function camFor(st) {
  const S = SHOTS[st.shot], r = region(st.shot, st.focus), pad = st.pad ?? 40;
  let z = Math.min(st.zoom ?? 1.5, WIN.w / (r[2] + 2 * pad), CH / (r[3] + 2 * pad));
  z = Math.max(1, z);
  const vw = WIN.w / z, vh = CH / z;
  let cx = r[0] + r[2] / 2, cy = r[1] + r[3] / 2;
  if (r[3] + 2 * pad > vh) cy = r[1] - pad + vh / 2; // taller than the view: its top
  if (r[2] + 2 * pad > vw) cx = r[0] - pad + vw / 2; // wider: its left
  cx = clamp(cx, vw / 2, S.w - vw / 2);
  cy = clamp(cy, vh / 2, Math.max(vh / 2, S.h - vh / 2));
  return { cx, cy, z };
}

function camAt(list, i, t) {
  const st = list[i], goal = camFor(st);
  if (i === 0 || st.cut) return goal;
  const from = camAt(list, i - 1, st.t), k = ease((t - st.t) / (st.glide ?? MOVE));
  return { cx: lerp(from.cx, goal.cx, k), cy: lerp(from.cy, goal.cy, k), z: lerp(from.z, goal.z, k) };
}

function toScreen(cam, x, y) {
  const vw = WIN.w / cam.z, vh = CH / cam.z;
  return [WIN.x + (x - (cam.cx - vw / 2)) * cam.z, CY + (y - (cam.cy - vh / 2)) * cam.z];
}

// ------------------------------------------------------------------ drawing kit

function rr(x, y, w, h, r) {
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, r);
}

function card(x, y, w, h, o = {}) {
  ctx.save();
  ctx.shadowColor = o.shadow ?? C.shadow;
  ctx.shadowBlur = o.blur ?? 28;
  ctx.shadowOffsetY = o.lift ?? 8;
  ctx.fillStyle = o.fill ?? C.card;
  rr(x, y, w, h, o.radius ?? 18);
  ctx.fill();
  ctx.restore();
  if (o.stroke) {
    ctx.save();
    ctx.strokeStyle = o.stroke;
    ctx.lineWidth = o.width ?? 3;
    rr(x, y, w, h, o.radius ?? 18);
    ctx.stroke();
    ctx.restore();
  }
}

function lines(text, size, weight, maxWidth, font = SANS) {
  ctx.font = `${weight} ${size}px ${font}`;
  const out = [];
  for (const para of String(text).split('\n')) {
    let line = '';
    for (const word of para.split(' ')) {
      const next = line ? line + ' ' + word : word;
      if (ctx.measureText(next).width > maxWidth && line) {
        out.push(line);
        line = word;
      } else line = next;
    }
    out.push(line);
  }
  return out;
}

/** Text, wrapped to `max`, from its top; returns the height it took. */
function text(str, x, y, o = {}) {
  const size = o.size ?? 32, lh = o.lh ?? size * 1.3;
  const ls = lines(str, size, o.weight ?? 600, o.max ?? 1600, o.font ?? SANS);
  ctx.save();
  ctx.fillStyle = o.color ?? C.ink;
  ctx.textAlign = o.align ?? 'left';
  ctx.textBaseline = 'top';
  ctx.globalAlpha *= o.alpha ?? 1;
  ls.forEach((l, i) => ctx.fillText(l, x, y + i * lh));
  ctx.restore();
  return ls.length * lh;
}

function backdrop() {
  const g = ctx.createLinearGradient(0, 0, W, H);
  g.addColorStop(0, C.bg1);
  g.addColorStop(1, C.bg2);
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);
  ctx.save(); // a faint grid, the drawing table the architecture used to live on
  ctx.strokeStyle = 'rgba(76, 110, 245, 0.05)';
  ctx.lineWidth = 1;
  for (let x = 0; x < W; x += 60) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke(); }
  for (let y = 0; y < H; y += 60) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); }
  ctx.restore();
}

function kicker(label, t) {
  ctx.save();
  ctx.globalAlpha = rise(t, 0, 0.8);
  ctx.font = `800 26px ${SANS}`;
  ctx.fillStyle = C.indigo;
  ctx.textBaseline = 'top';
  ctx.letterSpacing = '3px';
  ctx.fillText(label.toUpperCase(), 120, 84);
  ctx.restore();
}

/** Line icons, drawn in a box of `s` at x, y. */
function icon(name, x, y, s = 64, color = C.indigo) {
  ctx.save();
  ctx.translate(x, y);
  ctx.scale(s / 64, s / 64);
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = 4;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  const P = pts => { ctx.beginPath(); pts.forEach(([a, b], i) => (i ? ctx.lineTo(a, b) : ctx.moveTo(a, b))); ctx.stroke(); };
  const box = (a, b, w, h, r = 4) => { rr(a, b, w, h, r); ctx.stroke(); };
  const dot = (a, b, r) => { ctx.beginPath(); ctx.arc(a, b, r, 0, 7); ctx.fill(); };
  const ring = (a, b, r, s0 = 0, s1 = 7) => { ctx.beginPath(); ctx.arc(a, b, r, s0, s1); ctx.stroke(); };
  switch (name) {
    case 'diagram': box(6, 8, 20, 14); box(38, 8, 20, 14); box(22, 42, 20, 14); P([[16, 22], [28, 42]]); P([[48, 22], [36, 42]]); P([[26, 15], [38, 15]]); break;
    case 'sheet': box(8, 8, 48, 48); P([[8, 22], [56, 22]]); P([[8, 36], [56, 36]]); P([[24, 8], [24, 56]]); P([[40, 8], [40, 56]]); break;
    case 'desk': ring(32, 32, 20, Math.PI, 2 * Math.PI); box(8, 30, 9, 16, 3); box(47, 30, 9, 16, 3); P([[52, 46], [52, 52], [38, 56]]); break;
    case 'register': [16, 30, 44].forEach(v => { dot(12, v, 3); P([[22, v], [54, v]]); }); break;
    case 'person': ring(32, 20, 11); P([[12, 56], [14, 46], [22, 38], [42, 38], [50, 46], [52, 56]]); break;
    case 'question': ring(32, 32, 24); ctx.font = `800 30px ${SANS}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText('?', 32, 34); break;
    case 'lock': box(14, 28, 36, 28, 5); ring(32, 28, 11, Math.PI, 2 * Math.PI); P([[21, 28], [21, 22]]); P([[43, 28], [43, 22]]); dot(32, 42, 3); break;
    case 'copy': box(8, 16, 30, 40, 4); box(24, 8, 30, 40, 4); break;
    case 'blocked': box(10, 16, 34, 34, 4); P([[30, 33], [56, 33]]); P([[48, 25], [56, 33], [48, 41]]); ctx.strokeStyle = C.red; P([[8, 56], [56, 8]]); break;
    case 'tag': P([[8, 30], [30, 8], [56, 8], [56, 34], [34, 56], [8, 30]]); ring(45, 19, 4); break;
    case 'bubble': P([[10, 12], [54, 12], [54, 42], [30, 42], [18, 54], [18, 42], [10, 42], [10, 12]]); P([[20, 24], [44, 24]]); P([[20, 32], [36, 32]]); break;
    case 'feed': ctx.beginPath(); ctx.ellipse(40, 16, 16, 6, 0, 0, 7); ctx.stroke(); P([[24, 16], [24, 48]]); P([[56, 16], [56, 48]]); ctx.beginPath(); ctx.ellipse(40, 48, 16, 6, 0, 0, Math.PI); ctx.stroke(); P([[4, 32], [18, 32]]); P([[12, 26], [18, 32], [12, 38]]); break;
    case 'layers': [[12, 0], [26, 1], [40, 2]].forEach(([v]) => P([[32, v], [58, v + 10], [32, v + 20], [6, v + 10], [32, v]])); break;
    case 'sliders': [[16, 22], [32, 44], [48, 30]].forEach(([a, b]) => { P([[a, 8], [a, 56]]); ctx.fillStyle = C.card; ctx.beginPath(); ctx.arc(a, b, 6, 0, 7); ctx.fill(); ctx.stroke(); }); break;
    case 'shield': P([[32, 6], [54, 14], [52, 36], [32, 58], [12, 36], [10, 14], [32, 6]]); P([[22, 32], [30, 40], [44, 24]]); break;
    case 'robot': box(12, 18, 40, 32, 8); P([[32, 18], [32, 8]]); dot(32, 7, 3); dot(24, 32, 4); dot(40, 32, 4); P([[24, 42], [40, 42]]); break;
    case 'check': ring(32, 32, 24); P([[20, 32], [29, 41], [45, 24]]); break;
    case 'cross': ring(32, 32, 24); P([[22, 22], [42, 42]]); P([[42, 22], [22, 42]]); break;
    case 'calendar': box(8, 12, 48, 44, 6); P([[8, 24], [56, 24]]); P([[20, 6], [20, 16]]); P([[44, 6], [44, 16]]); break;
    case 'branch': ring(16, 14, 6); ring(16, 50, 6); ring(48, 26, 6); P([[16, 20], [16, 44]]); P([[48, 32], [48, 36], [36, 44], [22, 48]]); break;
    default: ring(32, 32, 20);
  }
  ctx.restore();
}

// ------------------------------------------------------------------ a screen in its window

function drawWindow(shot, alpha) {
  const S = SHOTS[shot];
  ctx.save();
  ctx.globalAlpha = alpha;
  card(WIN.x, WIN.y, WIN.w, WIN.bar + CH, { radius: 14, blur: 40, lift: 14, fill: '#f8f9fc' });
  ctx.fillStyle = '#eceff6';
  rr(WIN.x, WIN.y, WIN.w, WIN.bar, [14, 14, 0, 0]);
  ctx.fill();
  ['#ff6b6b', '#fcc419', '#51cf66'].forEach((c, i) => {
    ctx.fillStyle = c;
    ctx.beginPath();
    ctx.arc(WIN.x + 24 + i * 22, WIN.y + WIN.bar / 2, 7, 0, 7);
    ctx.fill();
  });
  ctx.fillStyle = '#ffffff';
  rr(WIN.x + 110, WIN.y + 7, 640, WIN.bar - 14, 12);
  ctx.fill();
  ctx.font = `500 16px ${MONO}`;
  ctx.fillStyle = C.dim;
  ctx.textBaseline = 'middle';
  ctx.fillText(S.path.length > 60 ? S.path.slice(0, 58) + '…' : S.path, WIN.x + 128, WIN.y + WIN.bar / 2 + 1);
  ctx.font = `700 17px ${SANS}`;
  ctx.textAlign = 'right';
  ctx.fillStyle = C.ink;
  ctx.fillText('EA Repository · ' + S.title, WIN.x + WIN.w - 24, WIN.y + WIN.bar / 2 + 1);
  ctx.restore();
}

function drawShot(shot, cam, alpha) {
  const S = SHOTS[shot], img = IMG[shot], k = img.naturalWidth / S.w;
  const vw = WIN.w / cam.z, vh = CH / cam.z, sx = cam.cx - vw / 2, sy = cam.cy - vh / 2;
  ctx.save();
  ctx.globalAlpha = alpha;
  rr(WIN.x, CY, WIN.w, CH, [0, 0, 14, 14]);
  ctx.clip();
  ctx.fillStyle = '#f1f3f5';
  ctx.fillRect(WIN.x, CY, WIN.w, CH);
  ctx.drawImage(img, sx * k, sy * k, vw * k, vh * k, WIN.x, CY, WIN.w, CH);
  // The navigation is fixed to the application's window: on a page taller than it, the
  // capture stops it at the window's foot, and it is drawn on down here.
  if (S.nav && S.h > CH) {
    const [nx, ny, nw, nh] = S.nav.box, foot = ny + nh;
    if (sy + vh > foot && sx < nx + nw) {
      const [ax, ay] = toScreen(cam, nx, Math.max(foot, sy)), [bx, by] = toScreen(cam, nx + nw, sy + vh);
      ctx.fillStyle = S.nav.fill;
      ctx.fillRect(ax, ay, bx - ax, by - ay + 1);
      ctx.fillStyle = S.nav.edge;
      ctx.fillRect(bx - Math.max(1, cam.z), ay, Math.max(1, cam.z), by - ay + 1);
    }
  }
  ctx.restore();
}

function spot(cam, r, a) {
  if (a <= 0) return;
  const pad = 10, [x0, y0] = toScreen(cam, r[0] - pad, r[1] - pad), [x1, y1] = toScreen(cam, r[0] + r[2] + pad, r[1] + r[3] + pad);
  ctx.save();
  rr(WIN.x, CY, WIN.w, CH, [0, 0, 14, 14]);
  ctx.clip();
  ctx.fillStyle = `rgba(20, 26, 51, ${0.22 * a})`; // the rest of the screen steps back
  ctx.beginPath();
  ctx.rect(WIN.x, CY, WIN.w, CH);
  ctx.roundRect(x0, y0, x1 - x0, y1 - y0, 12);
  ctx.fill('evenodd');
  ctx.globalAlpha = a;
  ctx.shadowColor = 'rgba(76, 110, 245, 0.55)';
  ctx.shadowBlur = 18;
  ctx.strokeStyle = C.indigo;
  ctx.lineWidth = 4;
  rr(x0, y0, x1 - x0, y1 - y0, 12);
  ctx.stroke();
  ctx.restore();
}

function pointer(x, y, a, press) {
  if (a <= 0) return;
  ctx.save();
  ctx.globalAlpha = a;
  if (press > 0 && press < 1) { // the press: a ring that opens and fades
    ctx.strokeStyle = `rgba(76, 110, 245, ${1 - press})`;
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.arc(x, y, 12 + 34 * press, 0, 7);
    ctx.stroke();
  }
  ctx.translate(x, y);
  const s = press > 0 && press < 0.25 ? 0.88 : 1;
  ctx.scale(1.5 * s, 1.5 * s);
  ctx.beginPath();
  ctx.moveTo(0, 0); ctx.lineTo(0, 24); ctx.lineTo(6, 18.5); ctx.lineTo(10.5, 28); ctx.lineTo(14.5, 26.2);
  ctx.lineTo(10.2, 17); ctx.lineTo(18, 17); ctx.closePath();
  ctx.shadowColor = 'rgba(0,0,0,0.35)';
  ctx.shadowBlur = 6;
  ctx.shadowOffsetY = 2;
  ctx.fillStyle = '#ffffff';
  ctx.fill();
  ctx.shadowColor = 'transparent';
  ctx.strokeStyle = '#1b2240';
  ctx.lineWidth = 1.6;
  ctx.stroke();
  ctx.restore();
}

function tour(s, t) {
  const list = s.states;
  let i = 0;
  while (i + 1 < list.length && list[i + 1].t <= t) i++;
  const st = list[i], cam = camAt(list, i, t);
  drawWindow(st.shot, 1);
  if (st.cut && i > 0 && t < st.t + FADE) { // the screen changes: the last one fades out under it
    const prev = list[i - 1];
    drawShot(prev.shot, camAt(list, i - 1, st.t), 1);
    drawShot(st.shot, cam, ease((t - st.t) / FADE));
  } else drawShot(st.shot, cam, 1);
  if (st.ring) {
    const settle = st.cut ? 0.35 : (st.glide ?? MOVE) * 0.7;
    const next = list[i + 1], out = next ? clamp((next.t - t) / 0.3, 0, 1) : 1;
    spot(cam, region(st.shot, st.ring), rise(t, st.t + settle, 0.45) * out);
  }
  // The pointer: it travels to what is pressed, presses it, and stays a moment on the next screen.
  let press = null;
  for (let j = 0; j <= i; j++) if (list[j].click && list[j].click.from <= t) press = { st: list[j], j };
  if (press) {
    const c = press.st.click, camP = camAt(list, press.j, c.at), r = region(press.st.shot, c.region);
    const [tx, ty] = toScreen(camP, r[0] + r[2] * 0.5, r[1] + r[3] * 0.55);
    const k = ease((t - c.from) / (c.at - c.from));
    const x = lerp(WIN.x + WIN.w * 0.72, tx, k), y = lerp(CY + CH * 0.9, ty, k);
    const a = rise(t, c.from, 0.25) * (1 - rise(t, c.at + 1.2, 0.4));
    pointer(x, y, a, (t - c.at) / 0.55);
  }
}

// ------------------------------------------------------------------ captions

function caption(t) {
  const c = TL.caps.find(k => t >= k.s - 0.12 && t <= k.e + 0.35);
  if (!c) return;
  const a = Math.min(rise(t, c.s - 0.12, 0.18), 1 - rise(t, c.e + 0.15, 0.2));
  const size = 34, ls = lines(c.text, size, 600, 1500);
  ctx.font = `600 ${size}px ${SANS}`;
  const w = Math.max(...ls.map(l => ctx.measureText(l).width)) + 56, h = ls.length * 44 + 24;
  const y = 1022 - h / 2;
  ctx.save();
  ctx.globalAlpha = a;
  ctx.fillStyle = 'rgba(20, 26, 51, 0.88)';
  rr(W / 2 - w / 2, y, w, h, 16);
  ctx.fill();
  ctx.fillStyle = '#ffffff';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ls.forEach((l, i) => ctx.fillText(l, W / 2, y + 14 + i * 44));
  ctx.restore();
}

// ------------------------------------------------------------------ the frame

function sceneAt(t) {
  let s = TL.scenes[0];
  for (const k of TL.scenes) if (t >= k.start) s = k;
  return s;
}

function drawAt(t) {
  t = clamp(t, 0, TL.total - 1e-3);
  const s = sceneAt(t), lt = t - s.start, def = SCENES[s.id];
  backdrop();
  const cue = (id, off = 0) => s.cues[id] + off;
  if (def.beats) tour(s, lt);
  if (def.draw) def.draw(lt, cue, s);
  // a scene fades in from the last one's ending
  const into = TL.scenes.indexOf(s);
  if (into > 0 && lt < 0.4 && !(def.beats && SCENES[TL.scenes[into - 1].id].beats)) {
    ctx.save();
    ctx.globalAlpha = 1 - rise(lt, 0, 0.4);
    ctx.fillStyle = C.bg1;
    ctx.fillRect(0, 0, W, H);
    ctx.restore();
  }
  caption(t);
  const end = TL.total - t; // the last seconds fade to the backdrop
  if (end < 1.2) {
    ctx.save();
    ctx.globalAlpha = 1 - end / 1.2;
    ctx.fillStyle = C.bg1;
    ctx.fillRect(0, 0, W, H);
    ctx.restore();
  }
}

function renderAt(t, quality = 0.92) {
  drawAt(t);
  return canvas.toDataURL('image/jpeg', quality);
}

function filmInfo() {
  return {
    total: TL.total,
    scenes: TL.scenes.map(s => ({ id: s.id, chapter: s.chapter, start: s.start, dur: s.dur, cues: s.cues })),
    caps: TL.caps,
    chapters: TL.chapters,
    clicks: TL.clicks,
  };
}

async function boot(scale = 1) {
  canvas = document.createElement('canvas');
  canvas.width = W * scale;
  canvas.height = H * scale;
  document.body.appendChild(canvas);
  ctx = canvas.getContext('2d');
  ctx.scale(scale, scale);
  await Promise.all(Object.entries(SHOTS).map(([id, S]) => new Promise((ok, fail) => {
    const img = new Image();
    img.onload = () => img.decode().then(ok, ok);
    img.onerror = () => fail(new Error('shot ' + S.file + ' did not load'));
    img.src = 'shots/' + S.file;
    IMG[id] = img;
  })));
  await document.fonts.load(`600 20px ${SANS}`);
  await document.fonts.load(`800 20px ${SANS}`);
  await document.fonts.load(`500 20px ${MONO}`);
  TL = buildTimeline();
  window.__READY__ = true;
}

window.renderAt = renderAt;
window.drawAt = drawAt;
window.filmInfo = filmInfo;
boot(window.__SCALE__ || 1).catch(e => { window.__ERROR__ = String(e); });
