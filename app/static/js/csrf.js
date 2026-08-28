// csrf.js — wraps window.fetch so every mutating request automatically
// carries the double-submit CSRF token (see app/main.py's CSRFMiddleware).
//
// This exists so the existing fetch() call sites across orders.html,
// products.html, broadcast.html and alerts.html need ZERO changes, and so
// every future call site (any new template) is covered automatically just
// by loading this script — no per-call-site edits, ever.
(function () {
  const orig = window.fetch;
  function readCookie(name) {
    const m = document.cookie.match('(?:^|; )' + name + '=([^;]*)');
    return m ? decodeURIComponent(m[1]) : null;
  }
  window.fetch = function (input, init) {
    init = init || {};
    const method = (init.method || 'GET').toUpperCase();
    if (['POST', 'PUT', 'PATCH', 'DELETE'].indexOf(method) !== -1) {
      init.headers = Object.assign({}, init.headers || {}, {
        'x-csrftoken': readCookie('csrftoken') || ''
      });
    }
    return orig(input, init);
  };
})();
