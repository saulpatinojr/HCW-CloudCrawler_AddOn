/* Cloud Crawler pane shell. Vanilla, no storage, no analytics; every dynamic string goes through text nodes.
 * Posts {type:'hcw-addon', id:'cloud-crawler', state} to each site origin from /api/health.siteOrigins when framed.
 * States: loading (on load) -> ready (health ok) | unavailable (health failed); working during an upload, then ready.
 * The upload path is disabled until the evidence engine is adopted from the upstream App. */
(function () {
  'use strict';
  var ADDON_ID = 'cloud-crawler';
  var ENGINE_NOTE = 'The evidence engine arrives with the first release of the upstream App. Until then this lab accepts no uploads.';

  var state = { siteOrigins: [], health: null };

  var $ = function (id) { return document.getElementById(id); };
  var text = function (el, value) { el.textContent = value == null ? '' : String(value); return el; };

  // ----- theme: ?theme=dark|light on the frame URL wins; otherwise prefers-color-scheme through theme.css -----
  (function theme() {
    var params = new URLSearchParams(window.location.search);
    var t = params.get('theme');
    if (t === 'dark') document.documentElement.classList.add('dark');
    if (t === 'light') document.documentElement.classList.add('light');
  })();

  // ----- pane protocol -----
  var framed = window.parent && window.parent !== window;
  function post(paneState) {
    if (!framed) return;
    state.siteOrigins.forEach(function (origin) {
      try { window.parent.postMessage({ type: 'hcw-addon', id: ADDON_ID, state: paneState }, origin); } catch (e) { /* ignore */ }
    });
  }

  function setStatus(words) { text($('status'), words); }
  function unavailable() {
    setStatus('Unavailable');
    $('unavailable').hidden = false;
    $('step-upload').hidden = true;
    post('unavailable');
  }

  function describeUploads(health) {
    $('file').disabled = true;
    $('run').disabled = true;
    if (health.turnstile && health.turnstile.required && !health.turnstile.siteKey) {
      text($('run-note'), 'Uploads are not available until human verification is configured.');
    } else {
      text($('run-note'), ENGINE_NOTE);
    }
  }

  function boot() {
    setStatus('Checking…');
    fetch('/api/health', { credentials: 'omit', headers: { accept: 'application/json' } })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) {
        var h = res.body || {};
        state.siteOrigins = Array.isArray(h.siteOrigins) ? h.siteOrigins.filter(function (o) { return typeof o === 'string' && /^https?:\/\/[^\s/]+$/.test(o); }) : [];
        post('loading');
        if (!res.ok || h.ok !== true || h.id !== ADDON_ID) { unavailable(); return; }
        state.health = h;
        describeUploads(h);
        setStatus('Ready');
        post('ready');
      })
      .catch(function () { unavailable(); });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
