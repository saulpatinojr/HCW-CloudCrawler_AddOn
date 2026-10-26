/* Cloud Crawler pane. Vanilla, no storage, no analytics; every dynamic string goes through text nodes.
 * Posts {type:'hcw-addon', id:'cloud-crawler', state} to each site origin from /api/health.siteOrigins when framed.
 * States: loading (on load) -> ready (health ok) | unavailable (health failed); working during a check, then ready.
 * The only requests are to this lab's own /api, plus the human-verification script when the lab publishes a site key.
 * Files are read and checked in the browser first; one request carries them to the lab, with the verification token. */
(function () {
  'use strict';
  var ADDON_ID = 'cloud-crawler';
  var ACTION = 'cloud-crawler-upload';
  var VERIFICATION_SCRIPT = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
  var DEFAULT_LIMIT = 5 * 1024 * 1024;
  var MAX_FILES = 5;
  var NAME_OK = /^[\w .()-]{1,120}\.json$/;
  var SAMPLE_EXPORT = 'sample-resource-graph.json';
  var DECISION_SAMPLES = {
    'starter': 'decision-starter.json',
    'zone-redundancy': 'decision-zone-redundancy.json',
    'wave-one': 'decision-wave-one.json'
  };
  var KIND_LABELS = { 'arg-export': 'Resource Graph export', 'tf-state': 'Terraform state', 'tf-plan': 'Terraform plan' };
  var VERDICT_WORDS = { 'supported': 'supported', 'contradicted': 'contradicted', 'unknown': 'unknown', 'not-applicable': 'not applicable' };

  var state = {
    siteOrigins: [],
    health: null,
    files: [],            // { name, kind, doc, entries }
    decisionFile: null,   // { name, doc }
    token: null,          // the human-verification token, good for one request
    widget: null,
    busy: false,
    result: null,         // { id, ownerToken, expiresAt }
    message: null,        // the outcome of the last check, kept on screen until the visitor changes something
    detail: null,         // the stored result as the lab returns it
    reportMd: ''
  };

  var $ = function (id) { return document.getElementById(id); };
  var text = function (node, value) { node.textContent = value == null ? '' : String(value); return node; };
  var el = function (tag, cls, value) { var n = document.createElement(tag); if (cls) n.className = cls; if (value != null) n.textContent = String(value); return n; };
  var clear = function (node) { while (node.firstChild) node.removeChild(node.firstChild); };

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
    ['step-evidence', 'step-decision', 'step-run'].forEach(function (id) { $(id).hidden = true; });
    post('unavailable');
  }

  // ----- requests to this lab -----
  function api(path, options) {
    options = options || {};
    var headers = options.headers || {};
    if (state.result && state.result.ownerToken && !headers['x-owner-token']) headers['x-owner-token'] = state.result.ownerToken;
    return fetch(path, { method: options.method || 'GET', headers: headers, body: options.body, credentials: 'omit' });
  }
  function readJson(response) { return response.json().catch(function () { return null; }); }

  // What the lab says went wrong, in words; it names fields, positions and reasons, never the visitor's own content.
  function errorMessage(body, status) {
    var e = body && body.error;
    if (!e || typeof e.message !== 'string') {
      if (status === 413) return 'The upload is larger than the limit.';
      return 'The request could not be completed.';
    }
    var d = e.details || {};
    var more = [];
    if (Array.isArray(d.fields) && d.fields.length) more.push('check: ' + d.fields.join(', '));
    if (typeof d.claimIndex === 'number') more.push('claim ' + (d.claimIndex + 1) + (d.reason ? ' (' + String(d.reason).replace(/_/g, ' ') + ')' : ''));
    else if (typeof d.evidenceIndex === 'number') more.push('file ' + (d.evidenceIndex + 1) + (d.reason ? ': ' + d.reason : ''));
    else if (typeof d.reason === 'string') more.push(d.reason.replace(/_/g, ' '));
    if (Array.isArray(d.codes) && d.codes.length) more.push('code: ' + d.codes.join(', '));
    if (typeof d.maxRows === 'number') more.push('limit ' + d.maxRows + ' rows');
    if (typeof d.retryAfterSeconds === 'number') more.push('try again in ' + d.retryAfterSeconds + ' seconds');
    return e.message + (more.length ? ' (' + more.join('; ') + ')' : '');
  }

  // ----- human verification (the widget renders only when the lab publishes a site key) -----
  function verificationNeeded() {
    return !!(state.health && state.health.turnstile && state.health.turnstile.required);
  }
  function uploadsAvailable() {
    var v = state.health && state.health.turnstile;
    return !(v && v.required && !v.siteKey);
  }
  function setupVerification(health) {
    var container = $('verification');
    clear(container);
    var v = health.turnstile;
    if (!v || !v.required) { text($('run-note'), ''); return; }
    if (!v.siteKey) { text($('run-note'), 'Uploads are not available until human verification is configured.'); return; }
    var script = document.createElement('script');
    script.src = VERIFICATION_SCRIPT;
    script.async = true;
    script.onload = function () {
      if (!window.turnstile) return;
      state.widget = window.turnstile.render(container, {
        sitekey: v.siteKey,
        action: ACTION,
        callback: function (token) { state.token = token; state.message = null; updateRunButton(); },
        'expired-callback': function () { state.token = null; updateRunButton(); },
        'error-callback': function () { state.token = null; updateRunButton(); }
      });
    };
    script.onerror = function () { text($('run-note'), 'Human verification could not load; reload to try again.'); };
    document.head.appendChild(script);
  }
  function resetVerification() {
    state.token = null;
    if (state.widget != null && window.turnstile) { try { window.turnstile.reset(state.widget); } catch (e) { /* ignore */ } }
  }

  // ----- the evidence files -----
  function detectKind(doc) {
    if (Array.isArray(doc)) return 'arg-export';
    if (doc && typeof doc === 'object') {
      if (Array.isArray(doc.data)) return 'arg-export';
      if (doc.version === 4 && Array.isArray(doc.resources)) return 'tf-state';
      if (typeof doc.format_version === 'string' && Array.isArray(doc.resource_changes)) return 'tf-plan';
    }
    return null;
  }
  function entriesOf(kind, doc) {
    if (kind === 'arg-export') return Array.isArray(doc) ? doc.length : doc.data.length;
    return kind === 'tf-state' ? doc.resources.length : doc.resource_changes.length;
  }
  function limitBytes() {
    return (state.health && state.health.limits && state.health.limits.maxUploadBytes) || DEFAULT_LIMIT;
  }
  function addEvidence(name, content) {
    var doc;
    try { doc = JSON.parse(content.replace(/^﻿/, '')); } catch (e) {
      text($('file-note'), name + ' is not valid JSON, so it was not added.');
      return;
    }
    var kind = detectKind(doc);
    if (!kind) {
      text($('file-note'), name + ' is not a Resource Graph export or a Terraform state or plan, so it was not added.');
      return;
    }
    if (state.files.length >= MAX_FILES) { text($('file-note'), 'Up to ' + MAX_FILES + ' files at a time.'); return; }
    state.files.push({ name: name, kind: kind, doc: doc, entries: entriesOf(kind, doc) });
    text($('file-note'), '');
    state.message = null;
    renderFiles();
    updateRunButton();
  }
  function readFile(file, done) {
    if (file.size > limitBytes()) {
      text($('file-note'), file.name + ' is larger than the ' + Math.round(limitBytes() / 1048576) + ' MB limit, so it was not added.');
      return;
    }
    var reader = new FileReader();
    reader.onload = function () { done(file.name, String(reader.result || '')); };
    reader.onerror = function () { text($('file-note'), file.name + ' could not be read.'); };
    reader.readAsText(file);
  }
  function renderFiles() {
    var list = $('file-list');
    clear(list);
    state.files.forEach(function (f, i) {
      var li = el('li');
      li.appendChild(el('strong', null, f.name));
      li.appendChild(document.createTextNode(' · ' + KIND_LABELS[f.kind] + ' · ' + f.entries + (f.entries === 1 ? ' entry' : ' entries') + ' '));
      if (f.kind !== 'arg-export') li.appendChild(el('span', 'small', '(recorded with a fingerprint; this version does not read Terraform yet, so claims about it stay unknown) '));
      var remove = el('button', 'secondary small-button', 'Remove');
      remove.type = 'button';
      remove.addEventListener('click', function () { state.files.splice(i, 1); state.message = null; renderFiles(); updateRunButton(); });
      li.appendChild(remove);
      list.appendChild(li);
    });
  }
  function useSampleExport() {
    fetch('/api/samples/' + SAMPLE_EXPORT, { credentials: 'omit' })
      .then(function (r) { if (!r.ok) throw new Error('sample'); return r.text(); })
      .then(function (t) {
        state.files = [];
        addEvidence(SAMPLE_EXPORT, t);
        if ($('decision-choice').value === 'file') { $('decision-choice').value = 'zone-redundancy'; onDecisionChoice(); }
      })
      .catch(function () { text($('file-note'), 'The sample could not be loaded.'); });
  }

  // ----- the decision -----
  function onDecisionChoice() {
    var own = $('decision-choice').value === 'file';
    $('decision-file-wrap').hidden = !own;
    text($('decision-note'), own ? 'Choose a decision file (JSON) in the form described in the samples folder of the repository.' : '');
    state.message = null;
    updateRunButton();
  }
  function readDecisionFile(name, content) {
    var doc;
    try { doc = JSON.parse(content.replace(/^﻿/, '')); } catch (e) {
      state.decisionFile = null;
      text($('decision-note'), name + ' is not valid JSON.');
      updateRunButton();
      return;
    }
    if (!doc || typeof doc !== 'object' || Array.isArray(doc) || !Array.isArray(doc.claims)) {
      state.decisionFile = null;
      text($('decision-note'), name + ' is not a decision file: it needs a title and a list of claims.');
      updateRunButton();
      return;
    }
    state.decisionFile = { name: name, doc: doc };
    state.message = null;
    text($('decision-note'), name + ': ' + doc.claims.length + (doc.claims.length === 1 ? ' claim' : ' claims') + '.');
    updateRunButton();
  }
  function getDecision() {
    var choice = $('decision-choice').value;
    if (choice === 'file') return Promise.resolve(state.decisionFile.doc);
    return fetch('/api/samples/' + DECISION_SAMPLES[choice], { credentials: 'omit' })
      .then(function (r) { if (!r.ok) throw new Error('The decision sample could not be loaded.'); return r.json(); });
  }

  // ----- run -----
  function ready() {
    if (state.busy || !uploadsAvailable() || state.files.length === 0) return false;
    if ($('decision-choice').value === 'file' && !state.decisionFile) return false;
    return !verificationNeeded() || !!state.token;
  }
  function hint() {
    if (state.files.length === 0) return 'Add at least one evidence file, or use the sample export.';
    if ($('decision-choice').value === 'file' && !state.decisionFile) return 'Choose your decision file.';
    if (verificationNeeded() && !state.token) return 'Complete the human verification to run the check.';
    return 'Ready.';
  }
  function updateRunButton() {
    $('run').disabled = !ready();
    if (state.busy || !uploadsAvailable()) return;
    text($('run-note'), state.message || hint());
  }
  function run() {
    if (!ready()) return;
    state.busy = true;
    $('run').disabled = true;
    setStatus('Checking…');
    text($('run-note'), 'Checking…');
    post('working');
    var status = 0;
    getDecision()
      .then(function (decision) {
        var evidence = state.files.map(function (f) {
          var item = { kind: f.kind, content: f.doc };
          if (NAME_OK.test(f.name)) item.name = f.name;
          return item;
        });
        var body = JSON.stringify({ evidence: evidence, decision: decision });
        if (new Blob([body]).size > limitBytes()) throw new Error('The files and the decision together are larger than the ' + Math.round(limitBytes() / 1048576) + ' MB limit.');
        var headers = { 'content-type': 'application/json' };
        if (state.token) headers['x-turnstile-token'] = state.token;
        return api('/api/uploads', { method: 'POST', headers: headers, body: body });
      })
      .then(function (r) { status = r.status; return readJson(r); })
      .then(function (json) {
        if (status !== 201) throw new Error(errorMessage(json, status));
        state.result = { id: json.uploadId, ownerToken: json.ownerToken, expiresAt: json.expiresAt };
        return api('/api/uploads/' + encodeURIComponent(json.uploadId)).then(function (r) { status = r.status; return readJson(r); });
      })
      .then(function (detail) {
        if (status !== 200) throw new Error(errorMessage(detail, status));
        state.detail = detail;
        return api('/api/uploads/' + encodeURIComponent(state.result.id) + '/files/report.md').then(function (r) { return r.ok ? r.text() : ''; });
      })
      .then(function (md) {
        state.reportMd = md;
        render();
        state.message = 'Done. The result is below.';
      })
      .catch(function (err) {
        state.message = err && err.message ? err.message : 'The request could not be completed.';
      })
      .finally(function () {
        state.busy = false;
        resetVerification();
        setStatus('Ready');
        post('ready');
        updateRunButton();
      });
  }

  // ----- results -----
  function pct(v) { return v == null ? 'n/a' : (Math.round(v * 10) / 10) + ''; }
  function jsonText(v) { try { return JSON.stringify(v); } catch (e) { return ''; } }
  function shorten(s, n) { return s.length > n ? s.slice(0, n) + '…' : s; }
  function card(label, value, note) {
    var c = el('div', 'card');
    c.appendChild(el('h3', null, label));
    c.appendChild(el('div', 'score', value));
    if (note) c.appendChild(el('div', 'small', note));
    return c;
  }
  function render() {
    var d = state.detail;
    ['step-summary', 'step-findings', 'step-proposals', 'step-record', 'step-actions'].forEach(function (id) { $(id).hidden = false; });
    var s = d.summary;
    text($('summary-line'), d.decision.title + ': ' + (s.supported + s.contradicted) + ' checks with a clear answer, ' + s.unknown + ' unknown, ' + s.notApplicable + ' not applicable.');
    var cards = $('cards'); clear(cards);
    cards.appendChild(card('Contradicted', s.contradicted, 'What is built differs from the decision.'));
    cards.appendChild(card('Supported', s.supported, 'What is built matches the decision.'));
    cards.appendChild(card('Unknown', s.unknown, 'The files cannot say. Unknown lowers coverage, never the score.'));
    cards.appendChild(card('Not applicable', s.notApplicable, 'Outside what the claim covers.'));
    cards.appendChild(card('Score', pct(s.score), 'Severity-weighted share of supported among the clear answers.'));
    cards.appendChild(card('Coverage', s.coverage == null ? 'n/a' : Math.round(s.coverage * 100) + '%', 'Clear answers among clear plus unknown.'));

    var claimBody = $('claims').querySelector('tbody'); clear(claimBody);
    d.claims.forEach(function (c) {
      var tr = el('tr');
      [c.statement, c.detectorId, c.severity, c.contradicted, c.supported, c.unknown, c.notApplicable].forEach(function (v, i) { tr.appendChild(el('td', i >= 3 ? 'num' : null, v)); });
      claimBody.appendChild(tr);
    });
    var ev = $('evidence-list'); clear(ev);
    d.evidence.forEach(function (e) {
      var li = el('li');
      li.appendChild(el('strong', null, (e.name || KIND_LABELS[e.kind] || e.kind) + ': '));
      li.appendChild(document.createTextNode(e.note + ' (' + e.resourceCount + ' resources read, ' + e.redactedCount + ' secret-like values removed, confidence ' + e.confidence + ', fingerprint ' + shorten(e.payloadHash, 19) + ')'));
      ev.appendChild(li);
    });
    var L = d.listing;
    text($('listing-note'), L.findingsListed + ' of ' + L.findingsTotal + ' findings are listed (' + L.notApplicableNotListed + ' not-applicable are counted, not listed' + (L.findingsLeftOut ? '; ' + L.findingsLeftOut + ' more are left out to keep the result small' : '') + ').');

    var verdict = $('f-verdict'); clear(verdict);
    [['', 'All']].concat(['contradicted', 'unknown', 'supported'].map(function (v) { return [v, VERDICT_WORDS[v]]; })).forEach(function (o) {
      var opt = el('option', null, o[1]); opt.value = o[0]; verdict.appendChild(opt);
    });
    renderFindings();
    renderProposals();
    renderRecord();

    var na = d.notAnAudit;
    text($('audit-line'), na.line);
    text($('audit-text'), na.text);
    text($('expiry'), 'Kept in memory until ' + new Date(d.expiresAt).toLocaleString() + ': it expires after two hours or when you delete it.');
    text($('report'), state.reportMd);
    text($('copy-note'), '');
    $('step-summary').scrollIntoView && $('step-summary').scrollIntoView({ block: 'start' });
  }
  function renderFindings() {
    var d = state.detail; if (!d) return;
    var want = $('f-verdict').value;
    var statements = {};
    d.claims.forEach(function (c) { statements[c.claimId] = c.statement; });
    var tbody = $('findings').querySelector('tbody'); clear(tbody);
    var shown = 0;
    d.findings.forEach(function (f) {
      if (want && f.verdict !== want) return;
      shown++;
      var tr = el('tr');
      tr.appendChild(el('td', 'state state-' + f.verdict, VERDICT_WORDS[f.verdict] || f.verdict));
      tr.appendChild(el('td', null, statements[f.claimId] || ''));
      tr.appendChild(el('td', 'mono wrap', f.resourceId || '(the decision)'));
      tr.appendChild(el('td', 'mono wrap', shorten(jsonText(f.observed), 200)));
      tr.appendChild(el('td', 'mono wrap', shorten(jsonText(f.expected), 200)));
      tr.appendChild(el('td', 'small', f.unknownReason || ''));
      tbody.appendChild(tr);
    });
    text($('findings-count'), shown + ' shown');
  }
  function renderProposals() {
    var d = state.detail;
    var list = $('proposals'); clear(list);
    if (!d.proposals.length) { list.appendChild(el('li', 'small', 'Nothing to review: no claim was contradicted.')); return; }
    d.proposals.forEach(function (p) {
      var li = el('li');
      li.appendChild(el('strong', null, p.title));
      li.appendChild(el('span', 'badge', p.kind + ' · ' + p.status));
      if (p.rationale) li.appendChild(el('p', 'small', p.rationale));
      if (p.impactedResourceIds.length) {
        li.appendChild(el('p', 'small', 'Resources named (' + p.impactedResourceIds.length + '): ' + shorten(p.impactedResourceIds.slice(0, 5).join(', '), 400) + (p.impactedResourceIds.length > 5 ? ', …' : '')));
      }
      if (p.recommendedActions.length) {
        var ul = el('ul', 'small');
        p.recommendedActions.forEach(function (a) { ul.appendChild(el('li', null, a.action)); });
        li.appendChild(ul);
      }
      list.appendChild(li);
    });
  }
  function renderRecord() {
    var rec = state.detail.decision;
    text($('record-title'), rec.title + ' (status: ' + rec.status + ', version ' + rec.version + ')');
    var dl = $('record-list'); clear(dl);
    var add = function (k, v) {
      if (v == null || v === '' || (Array.isArray(v) && !v.length)) return;
      dl.appendChild(el('dt', null, k));
      var dd = el('dd');
      if (Array.isArray(v)) { var ul = el('ul'); v.forEach(function (x) { ul.appendChild(el('li', null, x)); }); dd.appendChild(ul); } else text(dd, v);
      dl.appendChild(dd);
    };
    add('Context', rec.context);
    add('Decision', rec.decision);
    add('Drivers', rec.decisionDrivers);
    add('Consequences', rec.consequences);
    add('Constraints', rec.constraints);
    add('Assumptions', rec.assumptions);
    add('Risks', rec.risks);
    add('Open questions', rec.openQuestions);
    add('Claims', rec.claims.map(function (c) { return c.statement + ' [' + c.detectorId + ', ' + c.severity + ']'; }));
  }

  // ----- actions -----
  function download(name, mediaType, file) {
    api('/api/uploads/' + encodeURIComponent(state.result.id) + '/files/' + file)
      .then(function (r) { if (!r.ok) throw new Error('download'); return r.blob(); })
      .then(function (blob) {
        var url = URL.createObjectURL(new Blob([blob], { type: mediaType }));
        var a = document.createElement('a'); a.href = url; a.download = name;
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
        text($('copy-note'), 'If the download did not start, use Copy report: downloads can be blocked inside an embedded pane.');
      })
      .catch(function () { text($('copy-note'), 'The file could not be downloaded here; use Copy report instead.'); });
  }
  function copyReport() {
    var done = function () { text($('copy-note'), 'Report copied to the clipboard as Markdown.'); };
    var fallback = function () {
      try {
        var pre = $('report'); var range = document.createRange(); range.selectNodeContents(pre);
        var sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range);
        var ok = document.execCommand('copy'); sel.removeAllRanges();
        text($('copy-note'), ok ? 'Report copied to the clipboard as Markdown.' : 'Select the report text below and copy it.');
      } catch (e) { text($('copy-note'), 'Select the report text below and copy it.'); }
    };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(state.reportMd).then(done, fallback); else fallback();
  }
  // A framed page may not be allowed to open a browser dialog (the sandbox has no allow-modals), so deleting asks a
  // second time on the button itself.
  var deleteArmed = null;
  var DELETE_LABEL = 'Delete my result now';
  function disarmDelete() {
    if (deleteArmed) clearTimeout(deleteArmed);
    deleteArmed = null;
    text($('delete'), DELETE_LABEL);
  }
  function deleteNow() {
    if (!state.result) return;
    if (!deleteArmed) {
      text($('delete'), 'Click again to delete it for good');
      deleteArmed = setTimeout(disarmDelete, 6000);
      return;
    }
    disarmDelete();
    api('/api/uploads/' + encodeURIComponent(state.result.id), { method: 'DELETE' })
      .then(function (r) {
        if (!r.ok) throw new Error('delete');
        state.result = null; state.detail = null; state.reportMd = '';
        ['step-summary', 'step-findings', 'step-proposals', 'step-record', 'step-actions'].forEach(function (id) { $(id).hidden = true; });
        state.message = 'Your result was deleted.';
        updateRunButton();
      })
      .catch(function () {
        text($('copy-note'), 'The result could not be deleted just now. Try again; it expires after two hours in any case.');
      });
  }

  // ----- wiring -----
  function wire() {
    var dz = $('dropzone');
    ['dragenter', 'dragover'].forEach(function (ev) { dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.add('active'); }); });
    ['dragleave', 'drop'].forEach(function (ev) { dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.remove('active'); }); });
    dz.addEventListener('drop', function (e) {
      var files = e.dataTransfer && e.dataTransfer.files ? Array.prototype.slice.call(e.dataTransfer.files) : [];
      files.forEach(function (f) { readFile(f, addEvidence); });
    });
    dz.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('file').click(); } });
    $('file').addEventListener('change', function () {
      Array.prototype.slice.call($('file').files).forEach(function (f) { readFile(f, addEvidence); });
      $('file').value = '';
    });
    $('decision-choice').addEventListener('change', onDecisionChoice);
    $('decision-file-wrap').addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('decision-file').click(); } });
    $('decision-file').addEventListener('change', function () {
      var f = $('decision-file').files[0];
      if (f) readFile(f, readDecisionFile);
    });
    $('use-sample').addEventListener('click', useSampleExport);
    $('run').addEventListener('click', run);
    $('f-verdict').addEventListener('change', renderFindings);
    $('download-md').addEventListener('click', function () { download('cloud-crawler-report.md', 'text/markdown', 'report.md'); });
    $('download-json').addEventListener('click', function () { download('cloud-crawler-report.json', 'application/json', 'report.json'); });
    $('copy-report').addEventListener('click', copyReport);
    $('delete').addEventListener('click', deleteNow);
  }

  function boot() {
    wire();
    setStatus('Checking…');
    fetch('/api/health', { credentials: 'omit', headers: { accept: 'application/json' } })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) {
        var h = res.body || {};
        state.siteOrigins = Array.isArray(h.siteOrigins) ? h.siteOrigins.filter(function (o) { return typeof o === 'string' && /^https?:\/\/[^\s/]+$/.test(o); }) : [];
        post('loading');
        if (!res.ok || h.ok !== true || h.id !== ADDON_ID) { unavailable(); return; }
        state.health = h;
        setupVerification(h);
        updateRunButton();
        setStatus('Ready');
        post('ready');
      })
      .catch(function () { unavailable(); });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
