/* Generated architecture views: render Mermaid, let the reader move shapes, report positions.
 *
 * The mouse works as it does in draw.io: a drag on a shape moves it (with every shape selected
 * beside it), a drag on the empty canvas draws a selection box, and the right or middle button,
 * Ctrl (Command on a Mac) or a held Space turn a drag into a pan. The wheel scrolls — Shift
 * sideways — and zooms with Ctrl, Command or Alt, which is also what a trackpad pinch sends.
 * With the diagram focused, Escape clears the selection, Ctrl+A selects every shape, the arrow
 * keys nudge the selection (Shift for ten points) and Ctrl+Shift+H fits the diagram.
 *
 * Nothing here is saved: positions live in a browser-side store for the page's lifetime and
 * are handed to the draw.io export. Mermaid's layout engine is not re-run after a move; the
 * relationships of a moved shape are redrawn as straight connectors.
 */
(function () {
  const ID_RE = /\[([^\[\]]+)\]\s*$/;

  function ensureMermaid() {
    if (!window.mermaid) { return false; }
    if (!window.__eaMermaidInit) {
      window.mermaid.initialize({
        startOnLoad: false, securityLevel: 'strict', theme: 'neutral',
        flowchart: { htmlLabels: true, useMaxWidth: false, curve: 'basis', nodeSpacing: 30, rankSpacing: 50 },
      });
      window.__eaMermaidInit = true;
    }
    return true;
  }

  function nodeInfo(svg) {
    // mermaid node id -> {el, elementId, cx, cy, w, h}
    const nodes = {};
    svg.querySelectorAll('g.node').forEach(function (g) {
      const m = /^flowchart-(.+)-\d+$/.exec(g.id || '');
      if (!m) { return; }
      const label = (g.textContent || '').trim();
      const idm = ID_RE.exec(label);
      const t = /translate\(([-\d.]+),\s*([-\d.]+)\)/.exec(g.getAttribute('transform') || '');
      let bb;
      try { bb = g.getBBox(); } catch (e) { bb = { x: -60, y: -20, width: 120, height: 40 }; }
      nodes[m[1]] = {
        el: g, elementId: idm ? idm[1] : null,
        cx: t ? parseFloat(t[1]) : 0, cy: t ? parseFloat(t[2]) : 0, w: bb.width, h: bb.height,
      };
    });
    return nodes;
  }

  function edgeInfo(svg, nodes) {
    const ids = Object.keys(nodes).sort(function (a, b) { return b.length - a.length; });
    const edges = [];
    svg.querySelectorAll('path.flowchart-link').forEach(function (p) {
      const id = p.id || '';
      if (!id.startsWith('L_')) { return; }
      let src = null, dst = null;
      for (const a of ids) {
        if (!id.startsWith('L_' + a + '_')) { continue; }
        const rest = id.slice(('L_' + a + '_').length).replace(/_\d+$/, '');
        if (nodes[rest]) { src = a; dst = rest; break; }
      }
      if (!src) { return; }
      const label = svg.querySelector('g.edgeLabel g.label[data-id="' + id + '"]');
      edges.push({ path: p, src: src, dst: dst, labelGroup: label ? label.parentElement : null });
    });
    return edges;
  }

  function borderPoint(n, tx, ty) {
    // where the segment from the node centre towards (tx, ty) leaves the node's rectangle
    const dx = tx - n.cx, dy = ty - n.cy;
    if (dx === 0 && dy === 0) { return { x: n.cx, y: n.cy }; }
    const hw = n.w / 2, hh = n.h / 2;
    const sx = dx !== 0 ? hw / Math.abs(dx) : Infinity, sy = dy !== 0 ? hh / Math.abs(dy) : Infinity;
    const s = Math.min(sx, sy);
    return { x: n.cx + dx * s, y: n.cy + dy * s };
  }

  function reroute(edges, nodes, nodeId) {
    edges.forEach(function (e) {
      if (e.src !== nodeId && e.dst !== nodeId) { return; }
      const a = nodes[e.src], b = nodes[e.dst];
      const p1 = borderPoint(a, b.cx, b.cy), p2 = borderPoint(b, a.cx, a.cy);
      e.path.setAttribute('d', 'M' + p1.x + ',' + p1.y + 'L' + p2.x + ',' + p2.y);
      if (e.labelGroup) {
        e.labelGroup.setAttribute('transform', 'translate(' + (p1.x + p2.x) / 2 + ', ' + (p1.y + p2.y) / 2 + ')');
      }
    });
  }

  function positionsOf(nodes) {
    const out = {};
    Object.keys(nodes).forEach(function (k) {
      const n = nodes[k];
      if (n.elementId) { out[n.elementId] = { x: n.cx, y: n.cy, w: n.w, h: n.h }; }
    });
    return out;
  }

  function panGesture(evt, v) {
    // draw.io pans with the right or middle button, or the left one with Ctrl, Command or Space
    return evt.button === 1 || evt.button === 2 ||
      (evt.button === 0 && (evt.ctrlKey || evt.metaKey || (v && v.space)));
  }

  function enableDrag(svg, onChange) {
    const nodes = nodeInfo(svg);
    let edges = edgeInfo(svg, nodes);
    const selected = new Set();
    function toSvg(evt) {
      const pt = svg.createSVGPoint(); pt.x = evt.clientX; pt.y = evt.clientY;
      return pt.matrixTransform(svg.getScreenCTM().inverse());
    }
    function keyOf(el) {
      const g = el && el.closest ? el.closest('g.node') : null;
      if (!g) { return null; }
      return Object.keys(nodes).find(function (k) { return nodes[k].el === g; }) || null;
    }
    function paint() {
      Object.keys(nodes).forEach(function (k) { nodes[k].el.classList.toggle('is-selected', selected.has(k)); });
    }
    function select(keys, add) {
      if (!add) { selected.clear(); }
      keys.forEach(function (k) { selected.add(k); });
      paint();
    }
    function toggle(k) {
      if (selected.has(k)) { selected.delete(k); } else { selected.add(k); }
      paint();
    }
    function moveBy(keys, dx, dy, origins) {
      keys.forEach(function (k) {
        const n = nodes[k], o = origins ? origins[k] : { cx: n.cx, cy: n.cy };
        n.cx = o.cx + dx; n.cy = o.cy + dy;
        n.el.setAttribute('transform', 'translate(' + n.cx + ', ' + n.cy + ')');
      });
      keys.forEach(function (k) { reroute(edges, nodes, k); });
    }
    function settle() {
      // let the canvas grow with the shapes so nothing is clipped
      try {
        const bb = svg.getBBox();
        svg.setAttribute('viewBox', (bb.x - 10) + ' ' + (bb.y - 10) + ' ' + (bb.width + 20) + ' ' + (bb.height + 20));
        svg.setAttribute('width', bb.width + 20); svg.setAttribute('height', bb.height + 20);
      } catch (e) { /* ignore */ }
      if (onChange) { onChange(positionsOf(nodes)); }
    }
    let drag = null;
    return {
      positions: positionsOf(nodes),
      keyOf: keyOf,
      // A left press on a shape: select it (Shift adds or takes it away) and start moving the selection.
      press: function (evt, key) {
        if (evt.shiftKey) { toggle(key); } else if (!selected.has(key)) { select([key], false); }
        if (!selected.has(key)) { drag = null; return; }
        const keys = Array.from(selected), origins = {};
        keys.forEach(function (k) { origins[k] = { cx: nodes[k].cx, cy: nodes[k].cy }; });
        drag = { start: toSvg(evt), keys: keys, origins: origins, moved: false, sx: evt.clientX, sy: evt.clientY };
      },
      move: function (evt) {
        if (!drag) { return; }
        if (!drag.moved && Math.abs(evt.clientX - drag.sx) + Math.abs(evt.clientY - drag.sy) < 4) { return; }
        drag.moved = true;
        const p = toSvg(evt);
        moveBy(drag.keys, p.x - drag.start.x, p.y - drag.start.y, drag.origins);
      },
      release: function () {
        const moved = drag && drag.moved;
        drag = null;
        if (moved) { settle(); }
      },
      // The shapes whose whole box lies inside a rectangle on screen, as draw.io's rubber band selects.
      selectIn: function (rect, add) {
        const keys = Object.keys(nodes).filter(function (k) {
          const r = nodes[k].el.getBoundingClientRect();
          return r.left >= rect.left && r.right <= rect.right && r.top >= rect.top && r.bottom <= rect.bottom;
        });
        select(keys, add);
      },
      clear: function () { select([], false); },
      selectAll: function () { select(Object.keys(nodes), false); },
      nudge: function (dx, dy) {
        if (!selected.size) { return false; }
        moveBy(Array.from(selected), dx, dy);
        settle();
        return true;
      },
      // A view drawn where it could not be seen cannot be measured: `getBBox` throws on a
      // hidden shape, so every node falls back to the same default box. Read the geometry
      // again into the very nodes the drag already holds — a second, separate reading would
      // leave the drag reporting the sizes it first guessed.
      remeasure: function () {
        const fresh = nodeInfo(svg);
        Object.keys(nodes).forEach(function (k) {
          const f = fresh[k];
          if (!f) { return; }
          nodes[k].cx = f.cx; nodes[k].cy = f.cy; nodes[k].w = f.w; nodes[k].h = f.h;
        });
        edges = edgeInfo(svg, nodes);
        return positionsOf(nodes);
      },
    };
  }

  // ---------------------------------------------------------------- pan and zoom
  // The rendered SVG sits on a canvas the reader pans and scales, with draw.io's gestures.
  const viewports = {};
  const MIN_K = 0.05, MAX_K = 4;

  function applyView(v) {
    v.canvas.style.transform = 'translate(' + v.x + 'px, ' + v.y + 'px) scale(' + v.k + ')';
  }

  function contentSize(v) {
    const r = v.svg.getBoundingClientRect();
    return { w: r.width / v.k, h: r.height / v.k };
  }

  function fitView(v, pad) {
    const p = pad === undefined ? 16 : pad;
    const cw = v.container.clientWidth, ch = v.container.clientHeight;
    const s = contentSize(v);
    if (!s.w || !s.h || !cw || !ch) { return; }
    v.k = Math.max(MIN_K, Math.min(MAX_K, Math.min((cw - 2 * p) / s.w, (ch - 2 * p) / s.h)));
    v.x = (cw - s.w * v.k) / 2;
    v.y = (ch - s.h * v.k) / 2;
    applyView(v);
  }

  function zoomAt(v, px, py, factor) {
    const k = Math.max(MIN_K, Math.min(MAX_K, v.k * factor));
    const r = k / v.k;
    v.x = px - r * (px - v.x);
    v.y = py - r * (py - v.y);
    v.k = k;
    applyView(v);
  }

  function setupViewport(container, svg, shapes, remeasure) {
    const canvas = document.createElement('div');
    canvas.className = 'ea-mermaid-canvas';
    canvas.appendChild(svg);
    container.innerHTML = '';
    container.appendChild(canvas);
    container.tabIndex = 0;
    container.setAttribute('role', 'application');
    container.setAttribute('aria-label',
      'Diagram. Drag a shape to move it, drag the canvas to select, right-drag or Ctrl-drag to pan, ' +
      'Ctrl and the wheel to zoom.');
    const v = { container: container, canvas: canvas, svg: svg, k: 1, x: 0, y: 0, touched: false, space: false };
    viewports[container.id] = v;

    container.addEventListener('wheel', function (evt) {
      evt.preventDefault();
      v.touched = true;
      if (evt.ctrlKey || evt.metaKey || evt.altKey) {
        const r = container.getBoundingClientRect();
        zoomAt(v, evt.clientX - r.left, evt.clientY - r.top, Math.exp(-evt.deltaY * 0.0015));
        return;
      }
      const dx = evt.shiftKey && !evt.deltaX ? evt.deltaY : evt.deltaX;
      const dy = evt.shiftKey && !evt.deltaX ? 0 : evt.deltaY;
      v.x -= dx; v.y -= dy;
      applyView(v);
    }, { passive: false });

    // no browser menu over the diagram: the right button pans, as in draw.io
    container.addEventListener('contextmenu', function (evt) { evt.preventDefault(); });

    let gesture = null, band = null;
    container.addEventListener('pointerdown', function (evt) {
      try { container.focus({ preventScroll: true }); } catch (e) { container.focus(); }
      const key = shapes ? shapes.keyOf(evt.target) : null;
      if (panGesture(evt, v)) {
        gesture = { kind: 'pan', px: evt.clientX, py: evt.clientY, x: v.x, y: v.y };
        v.touched = true;
        container.classList.add('is-panning');
      } else if (evt.button === 0 && key && shapes) {
        gesture = { kind: 'move' };
        shapes.press(evt, key);
      } else if (evt.button === 0) {
        const r = container.getBoundingClientRect();
        band = document.createElement('div');
        band.className = 'ea-rubber-band';
        container.appendChild(band);
        gesture = { kind: 'band', sx: evt.clientX, sy: evt.clientY, ox: r.left, oy: r.top, add: evt.shiftKey };
      } else {
        return;
      }
      evt.preventDefault();
      try { container.setPointerCapture(evt.pointerId); } catch (e) { /* older browsers */ }
    });
    container.addEventListener('pointermove', function (evt) {
      if (!gesture) { return; }
      if (gesture.kind === 'pan') {
        v.x = gesture.x + (evt.clientX - gesture.px);
        v.y = gesture.y + (evt.clientY - gesture.py);
        applyView(v);
      } else if (gesture.kind === 'move') {
        shapes.move(evt);
      } else if (band) {
        const x0 = Math.min(gesture.sx, evt.clientX), y0 = Math.min(gesture.sy, evt.clientY);
        band.style.left = (x0 - gesture.ox) + 'px';
        band.style.top = (y0 - gesture.oy) + 'px';
        band.style.width = Math.abs(evt.clientX - gesture.sx) + 'px';
        band.style.height = Math.abs(evt.clientY - gesture.sy) + 'px';
      }
    });
    const end = function (evt) {
      if (!gesture) { return; }
      if (gesture.kind === 'move') {
        shapes.release();
      } else if (gesture.kind === 'band' && shapes) {
        const rect = {
          left: Math.min(gesture.sx, evt.clientX), right: Math.max(gesture.sx, evt.clientX),
          top: Math.min(gesture.sy, evt.clientY), bottom: Math.max(gesture.sy, evt.clientY),
        };
        // a click on the empty canvas clears the selection; a drag selects what it encloses
        if (rect.right - rect.left < 3 && rect.bottom - rect.top < 3) {
          if (!gesture.add) { shapes.clear(); }
        } else {
          shapes.selectIn(rect, gesture.add);
        }
      }
      if (band) { band.remove(); band = null; }
      gesture = null;
      container.classList.remove('is-panning');
    };
    container.addEventListener('pointerup', end);
    container.addEventListener('pointercancel', end);

    container.addEventListener('keydown', function (evt) {
      const mod = evt.ctrlKey || evt.metaKey;
      if (evt.key === ' ') {
        v.space = true; container.classList.add('is-pan-ready'); evt.preventDefault();
      } else if (evt.key === 'Escape' && shapes) {
        shapes.clear();
      } else if (mod && evt.shiftKey && (evt.key === 'H' || evt.key === 'h')) {
        v.touched = false; fitView(v); evt.preventDefault();
      } else if (mod && (evt.key === 'a' || evt.key === 'A') && shapes) {
        shapes.selectAll(); evt.preventDefault();
      } else if (shapes && evt.key.indexOf('Arrow') === 0) {
        const step = evt.shiftKey ? 10 : 1;
        const d = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[evt.key];
        if (d && shapes.nudge(d[0], d[1])) { evt.preventDefault(); }
      }
    });
    container.addEventListener('keyup', function (evt) {
      if (evt.key === ' ') { v.space = false; container.classList.remove('is-pan-ready'); }
    });
    container.addEventListener('blur', function () { v.space = false; container.classList.remove('is-pan-ready'); });

    // the container may still be laying out (or hidden on another tab) when the SVG lands
    fitView(v);
    requestAnimationFrame(function () { if (!v.touched) { fitView(v); } });
    if (window.ResizeObserver) {
      let hadSize = container.clientWidth > 0;
      new ResizeObserver(function () {
        if (!v.touched) { fitView(v); }
        // A view drawn on a tab nobody had opened has no layout, so every shape measured
        // the same. The first time it has a size, measure it again and say so, or its
        // export is a grid of identical boxes.
        const hasSize = container.clientWidth > 0;
        if (hasSize && !hadSize && !v.touched && remeasure) { remeasure(); }
        hadSize = hasSize;
      }).observe(container);
    }
    return v;
  }

  // Render `code` into the target container, make it draggable, return a promise of the positions.
  window.eaViews = {
    render: function (targetId, code, onChange) {
      const el = document.getElementById(targetId);
      if (!el) { return Promise.resolve(null); }
      if (!code || !code.trim()) { el.innerHTML = ''; delete viewports[targetId]; return Promise.resolve({}); }
      if (!ensureMermaid()) { el.innerHTML = '<div style="color:#c92a2a;font-size:12px">Mermaid is not loaded.</div>'; return Promise.resolve(null); }
      const uid = 'ea-svg-' + Math.random().toString(36).slice(2, 10);
      return window.mermaid.render(uid, code).then(function (r) {
        el.innerHTML = r.svg;
        const svg = el.querySelector('svg');
        if (!svg) { return {}; }
        svg.style.maxWidth = 'none';
        // Once the reader has moved a shape the drawing is theirs, and nothing measures
        // it again: the re-measure below exists only for a view that was drawn where it
        // could not be seen.
        let arranged = false;
        const drag = enableDrag(svg, function (p) {
          arranged = true;
          if (onChange) { onChange(p); }
        });
        setupViewport(el, svg, drag, function () {
          if (arranged || !onChange) { return; }
          onChange(drag.remeasure());
        });
        return drag.positions;
      }).catch(function (err) {
        el.innerHTML = '<pre style="color:#c92a2a;font-size:12px;white-space:pre-wrap">' + String(err) + '</pre>';
        return null;
      });
    },

    zoom: function (targetId, factor) {
      const v = viewports[targetId];
      if (!v) { return; }
      v.touched = true;
      zoomAt(v, v.container.clientWidth / 2, v.container.clientHeight / 2, factor);
    },

    fit: function (targetId) {
      const v = viewports[targetId];
      if (!v) { return; }
      v.touched = false;
      fitView(v);
    },

    fullscreen: function (targetId) {
      const v = viewports[targetId];
      if (!v) { return; }
      const frame = v.container.closest('.ea-mermaid-frame') || v.container;
      if (document.fullscreenElement) { document.exitFullscreen(); return; }
      if (frame.requestFullscreen) { frame.requestFullscreen(); }
    },
  };

  document.addEventListener('fullscreenchange', function () {
    // the viewport changes size on the way in and on the way out; two frames so the
    // browser has applied the new layout before we measure it (a fixed timeout could
    // fire before fullscreen exit finished, leaving the diagram sized for the old box)
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        Object.keys(viewports).forEach(function (id) { fitView(viewports[id]); });
      });
    });
  });

})();

