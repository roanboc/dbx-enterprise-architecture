/* The Markdown editor's Split mode, in the browser: the divider between the text and its
 * preview moves.
 *
 * Dragged with a pointer, or, once it has the focus, moved with the arrow keys (Shift for a
 * larger step), Home and End; a double-click shares the width equally again. The edit pane's
 * width is the editor's `--ea-split`, a share of its width kept between 15 and 85 per cent, and
 * the divider says where it stands through `aria-valuenow`.
 *
 * Where a reader left an editor's divider is a convenience of their browser (`ea-split`, local
 * storage, by the editor's name), never the store's; an editor drawn again finds it there. */
(function () {
  const KEY = 'ea-split';
  const MIN = 15, MAX = 85, MIDDLE = 50, STEP = 5, BIG_STEP = 15;

  function clamp(value) { return Math.min(MAX, Math.max(MIN, Math.round(value))); }

  function kept() {
    try { return JSON.parse(window.localStorage.getItem(KEY) || '{}') || {}; } catch (e) { return {}; }
  }

  function keep(editor, value) {
    if (!editor) { return; }
    try {
      const all = kept();
      all[editor] = value;
      window.localStorage.setItem(KEY, JSON.stringify(all));
    } catch (e) { /* a browser that keeps nothing still moves the divider */ }
  }

  function apply(body, value, remember) {
    const share = clamp(value);
    body.style.setProperty('--ea-split', share + '%');
    const divider = body.querySelector(':scope > .ea-md-splitter');
    if (divider) { divider.setAttribute('aria-valuenow', String(share)); }
    if (remember) { keep(body.getAttribute('data-editor'), share); }
  }

  function bodyOf(divider) {
    const body = divider && divider.parentElement;
    return body && body.classList.contains('ea-md-body') ? body : null;
  }

  // ------------------------------------------------------------------ dragging
  document.addEventListener('pointerdown', function (event) {
    const divider = event.target.closest && event.target.closest('.ea-md-splitter');
    const body = bodyOf(divider);
    if (!body || event.button !== 0) { return; }
    event.preventDefault();
    divider.focus();
    divider.setPointerCapture(event.pointerId);
    body.classList.add('ea-md-dragging');
    const box = body.getBoundingClientRect();
    function move(e) {
      if (box.width > 0) { apply(body, ((e.clientX - box.left) / box.width) * 100, false); }
    }
    function stop(e) {
      divider.removeEventListener('pointermove', move);
      divider.removeEventListener('pointerup', stop);
      divider.removeEventListener('pointercancel', stop);
      body.classList.remove('ea-md-dragging');
      apply(body, parseFloat(divider.getAttribute('aria-valuenow')) || MIDDLE, true);
      try { divider.releasePointerCapture(e.pointerId); } catch (err) { /* already released */ }
    }
    divider.addEventListener('pointermove', move);
    divider.addEventListener('pointerup', stop);
    divider.addEventListener('pointercancel', stop);
  });

  document.addEventListener('dblclick', function (event) {
    const body = bodyOf(event.target.closest && event.target.closest('.ea-md-splitter'));
    if (body) { apply(body, MIDDLE, true); }
  });

  // ------------------------------------------------------------------ the keys
  document.addEventListener('keydown', function (event) {
    const divider = event.target.closest && event.target.closest('.ea-md-splitter');
    const body = bodyOf(divider);
    if (!body || event.altKey || event.ctrlKey || event.metaKey) { return; }
    const now = parseFloat(divider.getAttribute('aria-valuenow')) || MIDDLE;
    const step = event.shiftKey ? BIG_STEP : STEP;
    const next = {
      ArrowLeft: now - step, ArrowDown: now - step,
      ArrowRight: now + step, ArrowUp: now + step,
      Home: MIN, End: MAX,
    }[event.key];
    if (next === undefined) { return; }
    event.preventDefault();
    apply(body, next, true);
  });

  // ---------------------------------------------- an editor drawn again finds its divider
  function restore(root) {
    const all = kept();
    const bodies = root.querySelectorAll ? root.querySelectorAll('.ea-md-body[data-editor]') : [];
    bodies.forEach(function (body) {
      if (body.dataset.eaSplitRestored) { return; }
      body.dataset.eaSplitRestored = '1';
      const share = all[body.getAttribute('data-editor')];
      if (typeof share === 'number') { apply(body, share, false); }
    });
  }

  let pending = false;
  new MutationObserver(function () {
    if (pending) { return; }
    pending = true;
    window.requestAnimationFrame(function () { pending = false; restore(document); });
  }).observe(document.documentElement, { childList: true, subtree: true });
})();
