/* Help where the work is done (initiative 27), in the browser.
 *
 * The ? key opens the help of the screen the reader is on: it presses the help button beside
 * the screen's title. Never while the reader is typing, never while a dialog or a side panel —
 * the help's own among them — is open over the screen, and never when another key is held, so
 * the character still reaches a text box, the keyboard stays in the panel that holds it, and no
 * browser shortcut is taken. A checkbox, a radio, a switch or a button takes no characters, so
 * ? still opens the help from one of them.
 *
 * A link to a section lands on it. The application's links change the address without the
 * browser's own scroll to a fragment, and a screen is drawn after its address changes, so the
 * section the fragment names is waited for and brought into view.
 *
 * What a reader has been shown and has closed is the browser's record (`help-seen`). Every
 * change to it is a patch merged into the record as it stands at that moment (`merge`), so a
 * change made while an answer was on its way is never written over by it. */
(function () {
  // ---------------------------------------------------------------- the ? key
  const TAKES_NO_TEXT = ['checkbox', 'radio', 'button', 'submit', 'reset', 'range', 'color', 'file', 'image'];

  function typing(el) {
    if (!el) { return false; }
    const tag = (el.tagName || '').toLowerCase();
    if (tag === 'input') { return TAKES_NO_TEXT.indexOf((el.type || 'text').toLowerCase()) < 0; }
    if (tag === 'textarea' || tag === 'select') { return true; }
    if (el.isContentEditable) { return true; }
    return (el.getAttribute && el.getAttribute('role') === 'combobox');
  }

  function panelOpen() {
    // The help's own panel is kept mounted while shut, so a panel counts only when it is drawn.
    const panels = document.querySelectorAll('.mantine-Modal-content, .mantine-Drawer-content');
    return Array.prototype.some.call(panels, function (p) { return p.getClientRects().length > 0; });
  }

  document.addEventListener('keydown', function (ev) {
    if (ev.key !== '?' || ev.ctrlKey || ev.metaKey || ev.altKey || ev.defaultPrevented) { return; }
    if (typing(ev.target) || panelOpen()) { return; }
    const button = document.querySelector('#page .ea-help-button');
    if (!button) { return; }
    ev.preventDefault();
    button.click();
  });

  // ------------------------------------------------------- a link to a section
  const WAIT_MS = 8000;   // for the screen the address names to be drawn
  const HOLD_MS = 1500;   // and for what stands above the section to finish drawing
  const STEP_MS = 100;
  let landing = 0;        // the latest landing asked for; an earlier one gives way to it
  let touched = 0;        // the reader's own scrolling, clicking or typing; a landing yields to it
  ['wheel', 'touchstart', 'keydown', 'mousedown'].forEach(function (name) {
    window.addEventListener(name, function () { touched += 1; }, {capture: true, passive: true});
  });

  function land() {
    const mine = ++landing;
    const since = touched;
    let id = (window.location.hash || '').slice(1);
    try { id = decodeURIComponent(id); } catch (e) { /* an id as written */ }
    if (!id) { return; }
    const started = Date.now();
    let landedAt = null;   // when the section was first brought into view
    let top = null;        // and where it then stood
    function step() {
      if (mine !== landing || touched !== since) { return; }
      const target = document.getElementById(id);
      if (!target) {
        if (Date.now() - started < WAIT_MS) { setTimeout(step, STEP_MS); }
        return;
      }
      const now = target.getBoundingClientRect().top;
      if (landedAt === null || Math.abs(now - top) > 4) {
        target.scrollIntoView({block: 'start'});
        top = target.getBoundingClientRect().top;
        if (landedAt === null) { landedAt = Date.now(); }
      }
      if (Date.now() - landedAt < HOLD_MS) { setTimeout(step, STEP_MS); }
    }
    // After the click that changed the address has finished: a Mantine link puts the page
    // back at its top once it has told the application the address changed.
    setTimeout(step, 0);
  }
  ['load', 'popstate', 'hashchange', '_dashprivate_pushstate'].forEach(function (name) {
    window.addEventListener(name, land);
  });

  // ------------------------------------------------------------- the record
  function fresh() { return {v: 1, welcome: false, tips: true, screens: []}; }  // SEEN_DEFAULT

  function read(seen) {
    // As the server reads it (`seen_state`): a record from elsewhere, or none, starts afresh.
    const out = fresh();
    if (seen && typeof seen === 'object' && !Array.isArray(seen)) {
      out.welcome = Boolean(seen.welcome);
      out.tips = seen.tips !== false;
      out.screens = Array.isArray(seen.screens)
        ? seen.screens.filter(function (s) { return typeof s === 'string'; })
        : [];
    }
    return out;
  }

  function merge(seen, patch) {
    const out = read(seen);
    if (!patch || typeof patch !== 'object') { return out; }
    if (patch.op === 'reset') { return fresh(); }
    if (patch.op === 'tips-off') { out.tips = false; }
    if (patch.op === 'shown' && typeof patch.screen === 'string') {
      if (patch.welcome) { out.welcome = true; }
      if (out.screens.indexOf(patch.screen) < 0) { out.screens.push(patch.screen); }
    }
    return out;
  }

  function pressed(clicks) {
    // Which of the welcome's, a tip's or the Guide's buttons was pressed, if one was: its
    // action. The callback also runs when a screen draws or removes those buttons, and none
    // of that is a press (`pressed` in screen_help.py).
    const context = window.dash_clientside && window.dash_clientside.callback_context;
    const trigger = context && context.triggered_id;
    if (!trigger || typeof trigger !== 'object') { return null; }
    const spec = (context.inputs_list && context.inputs_list[0]) || [];
    for (let i = 0; i < spec.length; i += 1) {
      const id = spec[i] && spec[i].id;
      if (id && id.type === trigger.type && id.action === trigger.action && (clicks || [])[i]) {
        return trigger.action;
      }
    }
    return null;
  }

  window.eaHelp = {merge: merge, pressed: pressed};
})();
