/* Network graph panels: the Cytoscape instance behind a panel id, and the gestures the
 * toolbar offers on top of the ones Cytoscape already handles (drag to pan, wheel to zoom).
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

  // A plain drag pans the panel, as it does on the generated views; Ctrl (Command on a
  // Mac) frees the nodes so the same drag moves one.
  function setGrabbable(on) {
    instances().forEach(function (cy) { cy.autoungrabify(!on); });
  }
  document.addEventListener('keydown', function (evt) {
    if (evt.key === 'Control' || evt.key === 'Meta') { setGrabbable(true); }
  });
  document.addEventListener('keyup', function (evt) {
    if (evt.key === 'Control' || evt.key === 'Meta') { setGrabbable(false); }
  });
  window.addEventListener('blur', function () { setGrabbable(false); });
})();
