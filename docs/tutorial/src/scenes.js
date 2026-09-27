/* What each scene shows. A scene of the application is a list of beats, each on a line of the
 * narration (`at`, and `off` seconds after it starts): a shot and where the camera looks
 * (`focus`, a named control of the shot or a rectangle), how close it may go (`zoom`), the
 * control a ring marks (`ring`), or a press (`click`) and the screen that follows it (`then`).
 * The other scenes draw themselves from the time since the scene began and the time each line
 * starts (`cue`). */

/** A part of a shot's control, from `a` to `b` of its height. */
function part(shot, name, a, b) {
  const r = SHOTS[shot].regions[name];
  return [r[0], r[1] + r[3] * a, r[2], r[3] * (b - a)];
}

/** The smallest rectangle holding two of a shot's controls. */
function both(shot, one, two) {
  const a = SHOTS[shot].regions[one], b = SHOTS[shot].regions[two];
  const x = Math.min(a[0], b[0]), y = Math.min(a[1], b[1]);
  return [x, y, Math.max(a[0] + a[2], b[0] + b[2]) - x, Math.max(a[1] + a[3], b[1] + b[3]) - y];
}

// A rectangle as a region the engine can look at: stored on the shot under a name of its own.
function named(shot, name, rect) {
  SHOTS[shot].regions[name] = rect.map(Math.round);
  return name;
}

function problem(x, y, w, h, ic, title, sub, t, at, active) {
  const a = rise(t, at, 0.6);
  if (a <= 0) return;
  ctx.save();
  ctx.globalAlpha = a;
  ctx.translate(0, (1 - a) * 24);
  card(x, y, w, h, { stroke: active ? C.indigo : null });
  icon(ic, x + 40, y + 44, 72, active ? C.red : C.faint);
  text(title, x + 144, y + 46, { size: 42, weight: 800, max: w - 180 });
  text(sub, x + 144, y + 108, { size: 29, weight: 600, color: C.dim, max: w - 180 });
  ctx.restore();
}

function feature(x, y, w, h, ic, title, sub, t, at, active, extra) {
  const a = rise(t, at, 0.6);
  if (a <= 0) return;
  ctx.save();
  ctx.globalAlpha = a;
  ctx.translate(0, (1 - a) * 24);
  card(x, y, w, h, { stroke: active ? C.indigo : null });
  ctx.fillStyle = C.pale;
  rr(x + 36, y + 36, 88, 88, 20);
  ctx.fill();
  icon(ic, x + 48, y + 48, 64, C.indigo);
  const th = text(title, x + 36, y + 146, { size: 34, weight: 800, max: w - 72, lh: 42 });
  text(sub, x + 36, y + 146 + th + 10, { size: 26, weight: 600, color: C.dim, max: w - 72, lh: 34 });
  if (extra) extra(x, y, w, h);
  ctx.restore();
}

function chip(label, x, y, o = {}) {
  ctx.save();
  ctx.font = `500 ${o.size ?? 22}px ${MONO}`;
  const w = ctx.measureText(label).width + 28;
  ctx.fillStyle = o.fill ?? C.pale;
  rr(x, y, w, (o.size ?? 22) + 18, 10);
  ctx.fill();
  ctx.fillStyle = o.color ?? C.deep;
  ctx.textBaseline = 'middle';
  ctx.fillText(label, x + 14, y + ((o.size ?? 22) + 18) / 2 + 1);
  ctx.restore();
  return w;
}

const SCENES = {
  // ---------------------------------------------------------------- 1 · why
  why: {
    draw(t, cue) {
      const title = rise(t, 0.2, 0.9) * (1 - rise(t, cue('know') - 0.7, 0.5));
      if (title > 0) {
        ctx.save();
        ctx.globalAlpha = title;
        ctx.fillStyle = C.indigo;
        rr(W / 2 - 60, 250, 120, 120, 30);
        ctx.fill();
        icon('diagram', W / 2 - 36, 274, 72, '#ffffff');
        text('The EA Repository', W / 2, 410, { size: 96, weight: 800, align: 'center' });
        text('Why it exists, what is new, and a tour of the screens', W / 2, 540, { size: 40, weight: 600, color: C.dim, align: 'center' });
        ctx.restore();
      }
      if (t < cue('know') - 0.6) return;
      kicker('Why a new EA platform', t - cue('know') + 0.6);

      // the question and the week it takes
      const p1 = rise(t, cue('know'), 0.6) * (1 - rise(t, cue('ask') - 0.3, 0.5));
      if (p1 > 0) {
        ctx.save();
        ctx.globalAlpha = p1;
        text('Most organisations know how they work.', W / 2, 300, { size: 70, weight: 800, align: 'center', max: 1600 });
        ctx.globalAlpha = p1 * rise(t, cue('week'), 0.6);
        text('Very few can answer a question about it in less than a week.', W / 2, 420, { size: 44, weight: 600, color: C.dim, align: 'center', max: 1500 });
        for (let i = 0; i < 7; i++) {
          const x = 468 + i * 144, y = 570, on = rise(t, cue('week') + 0.6 + i * 0.32, 0.25);
          card(x, y, 120, 150, { radius: 16, blur: 18, lift: 5 });
          ctx.fillStyle = i === 6 ? C.red : C.amber;
          ctx.globalAlpha = p1 * on;
          rr(x, y, 120, 44, [16, 16, 0, 0]);
          ctx.fill();
          ctx.globalAlpha = p1 * rise(t, cue('week'), 0.6);
          text('Day ' + (i + 1), x + 60, y + 70, { size: 28, weight: 800, align: 'center', color: on > 0.5 ? C.ink : C.faint });
        }
        ctx.restore();
      }

      // three questions, and where their answers live
      const p2 = rise(t, cue('ask') - 0.1, 0.5) * (1 - rise(t, cue('pictures') - 0.4, 0.5));
      if (p2 > 0) {
        ctx.save();
        ctx.globalAlpha = p2;
        const qs = ['What depends on this system?', 'Who owns this information?', 'What breaks if we change it?'];
        const lift = rise(t, cue('spread') - 0.2, 0.8);
        qs.forEach((q, i) => {
          const a = rise(t, cue('ask') + i * 1.45, 0.5);
          if (a <= 0) return;
          const x = 120 + i * 580, y = lerp(260, 170, lift);
          ctx.save();
          ctx.globalAlpha = p2 * a;
          card(x, y, 520, 140, { stroke: lift > 0 ? null : C.indigo, width: 2 });
          icon('question', x + 30, y + 38, 64);
          text(q, x + 116, y + 34, { size: 32, weight: 800, max: 380 });
          ctx.restore();
        });
        const hub = [W / 2, 440];
        const sources = [['diagram', 'Diagrams'], ['sheet', 'Spreadsheets'], ['desk', 'A service desk'], ['register', 'An asset register'], ['person', "People's memory"]];
        sources.forEach(([ic, label], i) => {
          const a = rise(t, cue('spread') + 2.2 + i * 0.85, 0.45);
          if (a <= 0) return;
          const x = 175 + i * 320, y = 590;
          ctx.save();
          ctx.globalAlpha = p2 * a;
          ctx.setLineDash([10, 10]);
          ctx.lineDashOffset = -t * 30;
          ctx.strokeStyle = C.faint;
          ctx.lineWidth = 3;
          ctx.beginPath();
          ctx.moveTo(hub[0], hub[1] + 30);
          ctx.lineTo(x + 145, y);
          ctx.stroke();
          ctx.setLineDash([]);
          card(x, y, 290, 170, { radius: 16 });
          icon(ic, x + 113, y + 26, 64, C.dim);
          text(label, x + 145, y + 112, { size: 27, weight: 700, align: 'center', max: 260 });
          ctx.restore();
        });
        const h = rise(t, cue('spread') + 2.0, 0.5);
        if (h > 0) {
          ctx.save();
          ctx.globalAlpha = p2 * h;
          ctx.fillStyle = C.card;
          ctx.beginPath();
          ctx.arc(hub[0], hub[1], 40, 0, 7);
          ctx.fill();
          icon('question', hub[0] - 30, hub[1] - 30, 60, C.amber);
          ctx.restore();
        }
        const pr = rise(t, cue('project'), 0.5);
        if (pr > 0) {
          ctx.save();
          ctx.globalAlpha = p2 * pr;
          ctx.fillStyle = '#fff4e6';
          rr(W / 2 - 330, 800, 660, 76, 38);
          ctx.fill();
          icon('calendar', W / 2 - 300, 812, 52, C.amber);
          text('A small project, every time', W / 2 + 30, 818, { size: 34, weight: 800, align: 'center', color: '#a35200' });
          ctx.restore();
        }
        ctx.restore();
      }

      // what goes wrong
      const cues = ['pictures', 'copied', 'nobody', 'vocab'];
      const now = cues.filter(c => t >= cue(c)).length - 1;
      const grid = [
        ['lock', 'Locked in pictures', 'Current only until someone redraws them'],
        ['copy', 'Copied by hand', 'From systems that already hold the facts'],
        ['blocked', 'Out of reach', 'No team, report or assistant can read it without an export'],
        ['tag', "The tool's vocabulary", "Not the business's, and not yours to change"],
      ];
      grid.forEach(([ic, title, sub], i) => {
        const x = 120 + (i % 2) * 860, y = 200 + Math.floor(i / 2) * 330;
        problem(x, y, 820, 280, ic, title, sub, t, cue(cues[i]) - 0.1, i === now);
      });
    },
  },

  // ---------------------------------------------------------------- 2 · what's new
  new: {
    draw(t, cue) {
      kicker("What's new", t);
      const pa = rise(t, 0.1, 0.6) * (1 - rise(t, cue('cited') - 0.4, 0.5));
      if (pa > 0) {
        ctx.save();
        ctx.globalAlpha = pa;
        text('The architecture as governed data, not drawings', W / 2, 180, { size: 58, weight: 800, align: 'center', max: 1600 });
        // a drawing, hand-made and unreadable to anyone but its author
        const fadeSketch = 1 - 0.65 * rise(t, cue('data') + 2.2, 1.0);
        ctx.save();
        ctx.globalAlpha = pa * fadeSketch;
        card(150, 360, 640, 460, { radius: 20 });
        ctx.strokeStyle = C.faint;
        ctx.lineWidth = 4;
        [[210, 420, 180, 90, -0.03], [520, 440, 200, 90, 0.04], [260, 640, 190, 100, 0.02], [540, 660, 170, 90, -0.05]].forEach(([x, y, w, h, r]) => {
          ctx.save();
          ctx.translate(x + w / 2, y + h / 2);
          ctx.rotate(r);
          rr(-w / 2, -h / 2, w, h, 10);
          ctx.stroke();
          ctx.restore();
        });
        ctx.beginPath();
        ctx.moveTo(390, 470); ctx.bezierCurveTo(450, 430, 470, 520, 520, 480);
        ctx.moveTo(300, 510); ctx.lineTo(340, 640);
        ctx.moveTo(620, 530); ctx.bezierCurveTo(640, 580, 600, 620, 620, 660);
        ctx.stroke();
        text('diagram-final-v7.png', 470, 770, { size: 22, weight: 600, font: MONO, color: C.faint, align: 'center' });
        ctx.restore();
        // the same knowledge as rows: each with an identifier, a type and a source
        const ar = rise(t, cue('data') + 1.2, 0.6);
        ctx.save();
        ctx.globalAlpha = pa * ar;
        ctx.strokeStyle = C.indigo;
        ctx.lineWidth = 5;
        ctx.beginPath(); ctx.moveTo(830, 590); ctx.lineTo(990, 590); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(970, 570); ctx.lineTo(994, 590); ctx.lineTo(970, 610); ctx.stroke();
        card(1030, 360, 740, 460, { radius: 20, stroke: C.indigo, width: 2 });
        const rows = [
          ['DE-SRS-COURSE', 'SRS_Course', 'catalogue'],
          ['PAC-SRS', 'Student Records System', 'cmdb'],
          ['LDC-CURR', 'Curriculum', 'register'],
          ['INT-CMS-SRS', 'CMS to SRS sync', 'catalogue'],
          ['WP-CMS-UPGRADE', 'CMS upgrade', 'portfolio'],
        ];
        text('id', 1070, 392, { size: 22, weight: 800, color: C.faint });
        text('name', 1330, 392, { size: 22, weight: 800, color: C.faint });
        text('source', 1640, 392, { size: 22, weight: 800, color: C.faint });
        rows.forEach(([id, name, src], i) => {
          const a = rise(t, cue('data') + 1.6 + i * 0.35, 0.4);
          const y = 440 + i * 72;
          ctx.save();
          ctx.globalAlpha = pa * ar * a;
          ctx.fillStyle = i % 2 ? '#f8f9fe' : '#ffffff';
          ctx.fillRect(1050, y - 12, 700, 64);
          chip(id, 1062, y, { size: 19 });
          text(name, 1330, y + 6, { size: 25, weight: 700, max: 290 });
          text(src, 1640, y + 6, { size: 23, weight: 600, color: C.dim });
          ctx.restore();
        });
        ctx.restore();
        ctx.restore();
      }
      const keys = ['cited', 'current', 'platform', 'language', 'governed', 'drafts'];
      const now = keys.filter(k => t >= cue(k)).length - 1;
      const cards = [
        ['bubble', 'Answers in seconds', 'Every fact cites the element it came from', (x, y) => chip('DE-SRS-COURSE-OFFERING', x + 150, y + 62, { size: 18 })],
        ['feed', 'Fed by the owners of the facts', 'Every row keeps its source'],
        ['layers', 'On the data platform', 'People and agents read the same model'],
        ['sliders', 'Your metamodel', 'Change what the model can describe, on a copy first'],
        ['branch', 'Governed change', 'Propose on a branch; owners review; a person approves'],
        ['shield', 'Agents draft, people approve', 'The assistant never approves'],
      ];
      cards.forEach(([ic, title, sub, extra], i) => {
        const x = 120 + (i % 3) * 580, y = 170 + Math.floor(i / 3) * 370;
        feature(x, y, 540, 330, ic, title, sub, t, cue(keys[i]) - 0.1, i === now, extra);
      });
    },
  },

  // ---------------------------------------------------------------- 3 · the tour
  home: {
    beats: [
      { at: 'app', shot: 'home-welcome', focus: 'all' },
      { at: 'welcome', off: -0.2, shot: 'home-welcome', focus: 'welcome', zoom: 1.6, ring: 'welcome' },
      { at: 'nav', off: -0.2, shot: 'home', focus: 'all', ring: 'nav' },
    ],
  },
  help: {
    beats: [
      { at: 'button', off: -0.3, shot: 'browse-help', focus: 'title', zoom: 1.45, ring: 'help' },
      { at: 'button', off: 1.8, click: 'help', move: 1.0, then: { shot: 'browse-help-open', focus: 'all', ring: 'panel' } },
      { at: 'panel', off: 0.6, shot: 'browse-help-open', focus: () => named('browse-help-open', 'panel-top', part('browse-help-open', 'panel', 0, 0.62)), zoom: 1.7 },
    ],
  },
  browse: {
    beats: [
      { at: 'find', off: -0.2, shot: 'browse', focus: 'search', zoom: 1.9, ring: 'search' },
      { at: 'find', off: 2.0, shot: 'browse', focus: 'grid', zoom: 1.2 },
      { at: 'open', off: -0.4, shot: 'browse', focus: 'row', zoom: 1.5, ring: 'row' },
      { at: 'open', off: 0.4, click: 'row', move: 0.9, then: { shot: 'element', focus: 'all' } },
      { at: 'open', off: 3.2, shot: 'element', focus: 'attributes', zoom: 1.4, ring: 'attributes' },
      { at: 'shapes', off: -0.6, shot: 'element', focus: 'tabs', zoom: 1.4, ring: 'graphtab' },
      { at: 'shapes', off: 0.6, click: 'graphtab', move: 0.8, then: { shot: 'element-graph', focus: 'graph', zoom: 1.1 } },
      { at: 'shapes', off: 3.4, shot: 'element-graph', focus: 'view', zoom: 1.2, ring: 'view' },
    ],
  },
  ask: {
    beats: [
      { at: 'ask', off: -0.2, shot: 'ask', focus: 'input', zoom: 1.6, ring: 'input' },
      { at: 'ask', off: 1.5, click: 'button', move: 0.9, then: { shot: 'ask-answer', focus: 'view', zoom: 1.2 } },
      // a cut, not a glide: the camera does not pass over the offline reader's own note
      { at: 'answer', off: 3.4, shot: 'ask-answer', focus: 'table', zoom: 1.25, ring: 'table', cut: true },
      { at: 'impact', off: -0.3, shot: 'impact', focus: 'upstream', zoom: 1.35, ring: 'upstream' },
      { at: 'impact', off: 3.4, shot: 'impact', focus: 'graph', zoom: 1.2 },
    ],
  },
  propose: {
    beats: [
      { at: 'page', off: -0.3, shot: 'propose', focus: 'where', zoom: 1.4, ring: 'where' },
      { at: 'split', off: -0.3, shot: 'propose', focus: 'editor', zoom: 1.2, ring: 'divider' },
      { at: 'split', off: 3.2, shot: 'propose', focus: 'analyse', zoom: 1.5, ring: 'analyse' },
      { at: 'analyse', off: -0.4, click: 'analyse', move: 0.9, then: { shot: 'propose-analysed', focus: 'conv', zoom: 1.35, ring: 'conv' } },
      { at: 'branch', off: -0.3, shot: 'propose-analysed', focus: 'rows', zoom: 1.2, ring: 'rows' },
      { at: 'branch', off: 3.0, shot: 'propose-analysed', focus: 'apply', zoom: 1.5, ring: 'apply' },
    ],
  },
  review: {
    beats: [
      { at: 'review', off: -0.3, shot: 'branches', focus: 'detail', zoom: 1.3, ring: 'approve' },
      { at: 'merge', off: -0.2, shot: 'branches', focus: () => named('branches', 'mergelog', both('branches', 'merge', 'log')), zoom: 1.3, ring: 'merge' },
      { at: 'target', off: -0.3, shot: 'target', focus: 'all', ring: 'matrix' },
      { at: 'target', off: 3.0, shot: 'target', focus: 'elements', zoom: 1.25, ring: 'elements' },
    ],
  },
  manage: {
    beats: [
      { at: 'feeds', off: -0.3, shot: 'feeds', focus: 'all', ring: 'runs' },
      { at: 'metamodel', off: -0.3, shot: 'metamodel', focus: 'all', ring: 'tabs' },
      { at: 'metamodel', off: 2.6, shot: 'metamodel-notation', focus: 'preview', zoom: 1.1 },
      { at: 'orgs', off: -0.3, shot: 'organisations', focus: 'table', zoom: 1.35, ring: 'table' },
      { at: 'users', off: -0.3, shot: 'users', focus: 'grant', zoom: 1.3, ring: 'grant' },
      { at: 'health', off: -0.3, shot: 'health', focus: 'fresh', zoom: 1.3, ring: 'fresh' },
      { at: 'health', off: 2.4, shot: 'health', focus: 'complete', zoom: 1.1 },
    ],
  },
  guide: {
    beats: [
      { at: 'guide', off: -0.4, shot: 'guide', focus: 'contents', zoom: 1.3, ring: 'contents' },
      { at: 'guide', off: 2.4, shot: 'guide', focus: 'title', zoom: 2.2, ring: 'help' },
    ],
  },

  // ---------------------------------------------------------------- 4 · the close
  end: {
    draw(t, cue) {
      ctx.save();
      ctx.globalAlpha = rise(t, 0, 0.8);
      ctx.fillStyle = C.indigo;
      rr(W / 2 - 56, 200, 112, 112, 28);
      ctx.fill();
      icon('diagram', W / 2 - 34, 222, 68, '#ffffff');
      text('EA Repository', W / 2, 350, { size: 92, weight: 800, align: 'center' });
      ctx.globalAlpha = rise(t, cue('close'), 0.6);
      text('Agents draft. People approve.', W / 2, 480, { size: 50, weight: 800, color: C.indigo, align: 'center' });
      ctx.globalAlpha = rise(t, cue('close') + 2.6, 0.6);
      text('Current, cited and shared.', W / 2, 556, { size: 40, weight: 700, color: C.dim, align: 'center' });
      ctx.globalAlpha = rise(t, cue('end') + 0.2, 0.8);
      text('Screens: the application, running on the sample model of a fictional university.', W / 2, 700, { size: 26, weight: 600, color: C.dim, align: 'center' });
      text('Narration: a synthetic voice. The film is made from code in docs/tutorial.', W / 2, 744, { size: 26, weight: 600, color: C.dim, align: 'center' });
      ctx.restore();
    },
  },
};
