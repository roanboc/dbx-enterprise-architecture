/* Names for the controls the component libraries render without one.

   A file input inside an upload area, and the occasional button a library draws with an
   icon and no text, reach the page with nothing a screen reader can announce — there is
   no property to pass one through. Everything the application draws itself carries its
   own name; this covers what it does not draw.

   The pass runs once the page settles and again whenever a callback replaces part of it. */
(function () {
  function named(el) {
    return !!(
      (el.getAttribute('aria-label') || '').trim() ||
      el.getAttribute('aria-labelledby') ||
      (el.getAttribute('title') || '').trim() ||
      (el.textContent || '').trim() ||
      (el.id && document.querySelector('label[for="' + CSS.escape(el.id) + '"]'))
    );
  }

  function nameUploads(root) {
    root.querySelectorAll('input[type="file"]').forEach(function (input) {
      if (named(input)) { return; }
      var region = input.closest('[id]');
      var text = region ? (region.textContent || '').replace(/\s+/g, ' ').trim() : '';
      input.setAttribute('aria-label', text.slice(0, 80) || 'Choose files to upload');
    });
  }

  function nameIconButtons(root) {
    root.querySelectorAll('button').forEach(function (button) {
      if (named(button)) { return; }
      var tip = button.getAttribute('data-tooltip') || button.getAttribute('aria-describedby');
      var described = tip ? document.getElementById(tip) : null;
      var text = described ? (described.textContent || '').trim() : '';
      button.setAttribute('aria-label', text || 'Button');
    });
  }

  function pass() {
    nameUploads(document);
    nameIconButtons(document);
  }

  document.addEventListener('DOMContentLoaded', pass);
  var observer = new MutationObserver(function () {
    window.clearTimeout(observer._t);
    observer._t = window.setTimeout(pass, 150);
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
})();
