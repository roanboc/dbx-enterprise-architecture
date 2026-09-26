/* The ? key opens the help of the screen the reader is on (initiative 27): it presses the help
 * button beside the screen's title. Never while the reader is typing, and never when another
 * key is held, so the character still reaches a text box and no browser shortcut is taken. */
(function () {
  function typing(el) {
    if (!el) { return false; }
    const tag = (el.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') { return true; }
    if (el.isContentEditable) { return true; }
    return (el.getAttribute && el.getAttribute('role') === 'combobox');
  }
  document.addEventListener('keydown', function (ev) {
    if (ev.key !== '?' || ev.ctrlKey || ev.metaKey || ev.altKey || ev.defaultPrevented) { return; }
    if (typing(ev.target) || document.querySelector('.mantine-Modal-root .mantine-Modal-content')) { return; }
    const button = document.querySelector('#page .ea-help-button');
    if (!button) { return; }
    ev.preventDefault();
    button.click();
  });
})();
