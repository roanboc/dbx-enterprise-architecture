/* Network graph panels: the Cytoscape instance behind a panel id, the toolbar's gestures, and
 * the mouse as draw.io uses it.
 *
 * Cytoscape itself moves a node dragged with the left button and draws a selection box when
 * the drag starts on the empty canvas (its own panning and wheel zoom are turned off in
 * `graph.py`). What draw.io adds is handled here, before Cytoscape sees it: the right or middle
 * button, Ctrl (Command on a Mac) or a held Space pan; the wheel scrolls, Shift sideways, and
 * zooms with Ctrl, Command or Alt, which is what a trackpad pinch sends.
 */
(function () {
  function container(panelId) {
    return document.getElementById(JSON.stringify({ id: panelId, type: 'gp-cy' }));
  }

  function instance(panelId) {
    const el = container(panelId);
    if (!el) { return null; }
    if (el._cyreg && el._cyreg.cy) { return el._cyreg.cy; }
    const child = el.firstElementChild;
    return child && child._cyreg ? child._cyreg.cy : null;
  }

  window.eaGraph = {
    instance: instance,

    zoom: function (panelId, factor) {
      const cy = instance(panelId);
      if (!cy) { return; }
      const ext = cy.extent();
      cy.zoom({
        level: cy.zoom() * factor,
        renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 },
        position: { x: (ext.x1 + ext.x2) / 2, y: (ext.y1 + ext.y2) / 2 },
      });
    },

    fullscreen: function (panelId) {
      const el = container(panelId);
      const frame = el && (el.closest('.ea-graph-frame') || el);
      if (!frame) { return; }
      if (document.fullscreenElement) { document.exitFullscreen(); return; }
      if (frame.requestFullscreen) { frame.requestFullscreen(); }
    },
  };

  document.addEventListener('fullscreenchange', function () {
    // the panel changes size on the way in and on the way out; wait two frames so the
    // browser has actually applied the layout (fullscreen exit can lag a fixed timeout,
    // which left Cytoscape resizing to a stale, larger box and spilling past the frame)
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        instances().forEach(function (cy) { cy.resize(); cy.fit(undefined, 30); });
      });
    });
  });

  function instances() {
    const found = [];
    document.querySelectorAll('.ea-graph-frame *').forEach(function (el) {
      if (el._cyreg && el._cyreg.cy) { found.push(el._cyreg.cy); }
    });
    return found;
  }

  function cyAt(target) {
    const frame = target && target.closest ? target.closest('.ea-graph-canvas') : null;
    if (!frame) { return null; }
    if (frame._cyreg && frame._cyreg.cy) { return frame._cyreg.cy; }
    let found = null;
    frame.querySelectorAll('*').forEach(function (el) { if (!found && el._cyreg && el._cyreg.cy) { found = el._cyreg.cy; } });
    return found;
  }

  let space = false, pan = null;

  function panGesture(evt) {
    return evt.button === 1 || evt.button === 2 || (evt.button === 0 && (evt.ctrlKey || evt.metaKey || space));
  }

  // Capture, on the document, runs before Cytoscape's own listeners inside the panel, so a pan
  // gesture never also starts a selection box or a node drag.
  function down(evt) {
    const cy = cyAt(evt.target);
    if (!cy || (!pan && !panGesture(evt))) { return; }
    evt.stopPropagation();
    evt.preventDefault();
    if (!pan) { pan = { cy: cy, x: evt.clientX, y: evt.clientY }; }
  }
  document.addEventListener('pointerdown', down, true);
  document.addEventListener('mousedown', down, true);
  document.addEventListener('pointermove', function (evt) {
    if (!pan) { return; }
    pan.cy.panBy({ x: evt.clientX - pan.x, y: evt.clientY - pan.y });
    pan.x = evt.clientX; pan.y = evt.clientY;
  }, true);
  function up(evt) {
    if (!pan) { return; }
    evt.stopPropagation();
    if (evt.type === 'pointerup' || evt.type === 'pointercancel') { pan = null; }
  }
  document.addEventListener('pointerup', up, true);
  document.addEventListener('pointercancel', up, true);
  document.addEventListener('mouseup', function (evt) { if (pan) { evt.stopPropagation(); } }, true);

  document.addEventListener('wheel', function (evt) {
    const cy = cyAt(evt.target);
    if (!cy) { return; }
    evt.preventDefault();
    evt.stopPropagation();
    if (evt.ctrlKey || evt.metaKey || evt.altKey) {
      const r = cy.container().getBoundingClientRect();
      cy.zoom({
        level: Math.max(cy.minZoom(), Math.min(cy.maxZoom(), cy.zoom() * Math.exp(-evt.deltaY * 0.0015))),
        renderedPosition: { x: evt.clientX - r.left, y: evt.clientY - r.top },
      });
      return;
    }
    const sideways = evt.shiftKey && !evt.deltaX;
    cy.panBy({ x: -(sideways ? evt.deltaY : evt.deltaX), y: sideways ? 0 : -evt.deltaY });
  }, { capture: true, passive: false });

  document.addEventListener('contextmenu', function (evt) {
    if (cyAt(evt.target)) { evt.preventDefault(); }
  }, true);

  document.addEventListener('keydown', function (evt) {
    if (evt.key !== ' ' || space) { return; }
    // Space pans only while the pointer is over a panel, so it still scrolls the page elsewhere
    if (document.querySelector('.ea-graph-canvas:hover')) { space = true; evt.preventDefault(); }
  });
  document.addEventListener('keyup', function (evt) { if (evt.key === ' ') { space = false; } });
  window.addEventListener('blur', function () { space = false; pan = null; });
})();
