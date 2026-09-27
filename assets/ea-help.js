/* Help where the work is done (initiative 27), in the browser.
 *
 * The ? key opens the help of the screen the reader is on: it presses the help button beside
 * the screen's title. Never while the reader is typing, never while a dialog or a side panel —
 * the help's own among them — is open over the screen, and never when another key is held, so
 * the character still reaches a text box, the keyboard stays in the panel that holds it, and no
 * browser shortcut is taken. A checkbox, a radio, a switch or a button takes no characters, so
 * ? still opens the help from one of them. */
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
})();
