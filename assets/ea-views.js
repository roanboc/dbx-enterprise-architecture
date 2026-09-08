/* Generated architecture views: render Mermaid, let the reader move shapes, report positions.
 *
 * Nothing here is saved: positions live in a browser-side store for the page's lifetime and
 * are handed to the draw.io export. Mermaid's layout engine is not re-run after a move; the
 * relationships of a moved shape are redrawn as straight connectors and its layer box grows
 * to keep it inside.
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

  function clusterInfo(svg, nodes) {
    const clusters = [];
    svg.querySelectorAll('g.cluster').forEach(function (c) {
      const rect = c.querySelector('rect');
      if (!rect) { return; }
      const x = parseFloat(rect.getAttribute('x')), y = parseFloat(rect.getAttribute('y'));
      const w = parseFloat(rect.getAttribute('width')), h = parseFloat(rect.getAttribute('height'));
      const members = Object.keys(nodes).filter(function (k) {
        const n = nodes[k]; return n.cx >= x && n.cx <= x + w && n.cy >= y && n.cy <= y + h;
      });
      const label = c.querySelector('.cluster-label');
      clusters.push({ rect: rect, label: label, members: members, pad: 12 });
    });
    return clusters;
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

  function growClusters(clusters, nodes) {
    clusters.forEach(function (c) {
      if (!c.members.length) { return; }
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      c.members.forEach(function (k) {
        const n = nodes[k];
        x0 = Math.min(x0, n.cx - n.w / 2); y0 = Math.min(y0, n.cy - n.h / 2);
        x1 = Math.max(x1, n.cx + n.w / 2); y1 = Math.max(y1, n.cy + n.h / 2);
      });
      const rx = parseFloat(c.rect.getAttribute('x')), ry = parseFloat(c.rect.getAttribute('y'));
      const rw = parseFloat(c.rect.getAttribute('width')), rh = parseFloat(c.rect.getAttribute('height'));
      const nx = Math.min(rx, x0 - c.pad), ny = Math.min(ry, y0 - c.pad - 24);
      const nx1 = Math.max(rx + rw, x1 + c.pad), ny1 = Math.max(ry + rh, y1 + c.pad);
      c.rect.setAttribute('x', nx); c.rect.setAttribute('y', ny);
      c.rect.setAttribute('width', nx1 - nx); c.rect.setAttribute('height', ny1 - ny);
      if (c.label) {
        const t = /translate\(([-\d.]+),\s*([-\d.]+)\)/.exec(c.label.getAttribute('transform') || '');
        if (t) { c.label.setAttribute('transform', 'translate(' + ((nx + nx1) / 2) + ', ' + ny + ')'); }
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

  function arranging(evt) {
    return evt.ctrlKey || evt.metaKey;
  }

  function enableDrag(svg, onChange) {
    const nodes = nodeInfo(svg);
    let edges = edgeInfo(svg, nodes);
    let clusters = clusterInfo(svg, nodes);
    let dragging = null, start = null, origin = null;
    function toSvg(evt) {
      const pt = svg.createSVGPoint(); pt.x = evt.clientX; pt.y = evt.clientY;
      return pt.matrixTransform(svg.getScreenCTM().inverse());
    }
    Object.keys(nodes).forEach(function (k) {
      const n = nodes[k];
      n.el.addEventListener('pointerdown', function (evt) {
        // a plain drag belongs to the canvas; only the modifier moves a shape
        if (!arranging(evt)) { return; }
        dragging = k; start = toSvg(evt); origin = { cx: n.cx, cy: n.cy };
        evt.preventDefault(); evt.stopPropagation();
        try { n.el.setPointerCapture(evt.pointerId); } catch (e) { /* older browsers */ }
      });
      n.el.addEventListener('pointermove', function (evt) {
        if (dragging !== k) { return; }
        const p = toSvg(evt);
        n.cx = origin.cx + (p.x - start.x); n.cy = origin.cy + (p.y - start.y);
        n.el.setAttribute('transform', 'translate(' + n.cx + ', ' + n.cy + ')');
        reroute(edges, nodes, k);
        growClusters(clusters, nodes);
      });
      const end = function (evt) {
        if (dragging !== k) { return; }
        dragging = null;
        // let the canvas grow with the shapes so nothing is clipped
        try {
          const bb = svg.getBBox();
          svg.setAttribute('viewBox', (bb.x - 10) + ' ' + (bb.y - 10) + ' ' + (bb.width + 20) + ' ' + (bb.height + 20));
          svg.setAttribute('width', bb.width + 20); svg.setAttribute('height', bb.height + 20);
        } catch (e) { /* ignore */ }
        if (onChange) { onChange(positionsOf(nodes)); }
      };
      n.el.addEventListener('pointerup', end);
      n.el.addEventListener('pointercancel', end);
    });
    return {
      positions: positionsOf(nodes),
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
        clusters = clusterInfo(svg, nodes);
        return positionsOf(nodes);
      },
    };
  }

  // ---------------------------------------------------------------- pan and zoom
  // The rendered SVG sits on a canvas the reader drags and scales. A plain drag pans,
  // wherever it starts; Ctrl (Command on a Mac) turns the same drag into a shape move.
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

  function setupViewport(container, svg, remeasure) {
    const canvas = document.createElement('div');
    canvas.className = 'ea-mermaid-canvas';
    canvas.appendChild(svg);
    container.innerHTML = '';
    container.appendChild(canvas);
    const v = { container: container, canvas: canvas, svg: svg, k: 1, x: 0, y: 0, touched: false };
    viewports[container.id] = v;

    container.addEventListener('wheel', function (evt) {
      evt.preventDefault();
      v.touched = true;
      const r = container.getBoundingClientRect();
      zoomAt(v, evt.clientX - r.left, evt.clientY - r.top, Math.exp(-evt.deltaY * 0.0015));
    }, { passive: false });

    let pan = null;
    container.addEventListener('pointerdown', function (evt) {
      if (arranging(evt) && evt.target.closest && evt.target.closest('g.node')) { return; }
      pan = { px: evt.clientX, py: evt.clientY, x: v.x, y: v.y };
      v.touched = true;
      container.classList.add('is-panning');
      try { container.setPointerCapture(evt.pointerId); } catch (e) { /* older browsers */ }
    });
    container.addEventListener('pointermove', function (evt) {
      if (!pan) { return; }
      v.x = pan.x + (evt.clientX - pan.px);
      v.y = pan.y + (evt.clientY - pan.py);
      applyView(v);
    });
    const endPan = function () { pan = null; container.classList.remove('is-panning'); };
    container.addEventListener('pointerup', endPan);
    container.addEventListener('pointercancel', endPan);
    container.addEventListener('pointerleave', endPan);

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
        setupViewport(el, svg, function () {
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
    // the viewport changes size on the way in and on the way out
    Object.keys(viewports).forEach(function (id) {
      setTimeout(function () { fitView(viewports[id]); }, 120);
    });
  });

  function showArrangeCursor(on) {
    document.querySelectorAll('.ea-mermaid').forEach(function (el) {
      el.classList.toggle('is-arranging', on);
    });
  }
  document.addEventListener('keydown', function (evt) {
    if (evt.key === 'Control' || evt.key === 'Meta') { showArrangeCursor(true); }
  });
  document.addEventListener('keyup', function (evt) {
    if (evt.key === 'Control' || evt.key === 'Meta') { showArrangeCursor(false); }
  });
  window.addEventListener('blur', function () { showArrangeCursor(false); });
})();

