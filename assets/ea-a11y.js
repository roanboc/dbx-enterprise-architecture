/* What a keyboard or a screen reader needs that the markup alone does not give it: names for
   the controls the component libraries render without one, and a skip link that moves the
   keyboard and not only the view.

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

/* "Skip to the page" hands the keyboard to the page itself.

   Followed as a plain link it only scrolls: the focus falls to the document, a screen reader
   says nothing about where the reader now is, and whether the next Tab starts from the page
   or from the top of the header is up to the browser. So the keyboard goes to the page's
   title instead, and the next Tab reaches the page's first control in every browser. The
   title, and not the container the link points at: a screen reader announces what takes the
   focus by its role and its name, and a container with no role of its own is named from
   everything inside it — the whole page read out on every skip — where the title is heard as
   "Browse, heading level 1", which is where the reader now is. The title is the page's first
   line, so nothing on the page comes before it in the tab order. A page with no title yet,
   still being drawn, gives the keyboard to the main landmark around it, which a screen reader
   announces by its role and never names from its contents.

   What takes the focus is made focusable for that moment and plain again once the focus
   moves on — a click on the title must not pull the tab order back to the page's top — and
   the address is left as it was, since there is nowhere to go back to. Nothing scrolls
   either: the link is only on screen at the top of the window, where the page already shows
   below the header, and scrolling the title to the window's top would put it under the
   header pinned there. Without this script the link still does what a plain link does. */
(function () {
  document.addEventListener('click', function (ev) {
    if (ev.defaultPrevented || ev.button !== 0 || ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.altKey) {
      return;
    }
    var link = ev.target && ev.target.closest ? ev.target.closest('a.ea-skip-link') : null;
    var page = link ? document.getElementById((link.getAttribute('href') || '').slice(1)) : null;
    if (!page) { return; }
    var target = page.querySelector('h1') || page.closest('main') || page;
    ev.preventDefault();
    target.setAttribute('tabindex', '-1');
    target.addEventListener('blur', function done() {
      target.removeAttribute('tabindex');
      target.removeEventListener('blur', done);
    });
    target.focus({ preventScroll: true });
  });
})();
