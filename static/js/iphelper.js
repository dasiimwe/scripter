/* IP Helper — detects IPv4 / IPv6 addresses in form inputs, shows a link,
   opens a popover with subnet math. Option E(b): "Use" replaces only the
   detected substring, not the whole field. */
(function () {
  'use strict';

  // Lax detectors: find candidates. The server's ipaddress module is the
  // authority for validity. If the server returns {valid:false} the link hides.
  var IPV4_RE = /(\b(?:\d{1,3}\.){3}\d{1,3}(?:\s*\/\s*\d{1,3}|\s+(?:\d{1,3}\.){3}\d{1,3})?\b)/;
  var IPV6_RE = /((?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}(?:\/\d{1,3})?|::(?:[0-9a-fA-F]{1,4}(?::[0-9a-fA-F]{1,4})*)?(?:\/\d{1,3})?|(?:[0-9a-fA-F]{1,4}:){1,}:(?:[0-9a-fA-F]{1,4})?(?:\/\d{1,3})?)/;

  function detect(text) {
    if (!text) return null;
    var v4 = text.match(IPV4_RE);
    if (v4) {
      var raw = v4[0];
      var parts = raw.split(/\s+|\//);
      return {
        raw: raw,
        address: parts[0],
        mask: parts.length > 1 ? parts.slice(1).join('/') : '',
        index: v4.index,
        length: raw.length,
      };
    }
    var v6 = text.match(IPV6_RE);
    if (v6) {
      var raw6 = v6[0];
      var slash = raw6.indexOf('/');
      return {
        raw: raw6,
        address: slash >= 0 ? raw6.slice(0, slash) : raw6,
        mask: slash >= 0 ? raw6.slice(slash + 1) : '',
        index: v6.index,
        length: raw6.length,
      };
    }
    return null;
  }

  function el(tag, attrs, children) {
    var n = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      if (k === 'class') n.className = attrs[k];
      else if (k === 'text') n.textContent = attrs[k];
      else n.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) {
      if (c == null) return;
      n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    });
    return n;
  }

  function formatHosts(str) {
    if (!str) return '—';
    if (str.length <= 12) return Number(str).toLocaleString();
    var d = Number(str);
    return str + ' (~' + d.toExponential(2) + ')';
  }

  function copyToClipboard(text, btn) {
    var done = function (ok) {
      var orig = btn.textContent;
      btn.textContent = ok ? 'copied' : 'copy failed';
      setTimeout(function () { btn.textContent = orig; }, 1200);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(
        function () { done(true); },
        function () { done(false); }
      );
    } else {
      done(false);
    }
  }

  function replaceInInput(input, match, value) {
    var cur = input.value;
    var before = cur.slice(0, match.index);
    var after  = cur.slice(match.index + match.length);
    input.value = before + value + after;
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function renderPanel(state, data) {
    var rows = [];
    function row(label, value, useable) {
      if (value == null || value === '') return;
      var copy = el('button', { type: 'button', class: 'ip-action' }, ['copy']);
      copy.addEventListener('click', function () { copyToClipboard(String(value), copy); });
      var kids = [
        el('td', { class: 'lbl' }, [label]),
        el('td', { class: 'val' }, [String(value)]),
        el('td', { class: 'actions' }, [copy]),
      ];
      if (useable) {
        var use = el('button', { type: 'button', class: 'ip-action' }, ['use']);
        use.addEventListener('click', function () {
          replaceInInput(state.input, state.match, String(value));
          state.close();
        });
        kids[2].appendChild(use);
      }
      rows.push(el('tr', null, kids));
    }

    row('Host address',   data.host_address,   true);
    row('Host w/ CIDR',   data.host_cidr,      true);
    row('Classification', data.classification, false);
    row('Network',        data.network,        true);
    row('Network CIDR',   data.cidr,           true);
    if (data.version === 4) {
      row('Netmask',      data.netmask,        true);
      row('Wildcard',     data.wildcard,       true);
      row('Broadcast',    data.broadcast,      true);
    } else {
      row('Prefix length','/' + data.prefix_length, true);
    }
    row('First host',     data.first_host,     true);
    row('Last host',      data.last_host,      true);
    row('Usable hosts',   formatHosts(data.num_hosts),     false);
    row('Total addresses',formatHosts(data.num_addresses), false);

    return el('table', { class: 'ip-table' }, rows);
  }

  function openPanel(state) {
    closeAllPanels();
    var url = state.scope.dataset.ipHelperUrl;
    var params = new URLSearchParams({ address: state.match.address });
    if (state.maskOverride) params.set('mask', state.maskOverride);
    else if (state.match.mask) params.set('mask', state.match.mask);

    var panel = el('div', { class: 'ip-panel' });
    var head = el('div', { class: 'ip-head' }, [
      el('span', { class: 'ip-title' }, ['IP Helper · ' + state.match.raw]),
    ]);
    var closeBtn = el('button', { type: 'button', class: 'ip-close', 'aria-label': 'Close' }, ['×']);
    closeBtn.addEventListener('click', function () { state.close(); });
    head.appendChild(closeBtn);
    panel.appendChild(head);

    var maskRow = el('div', { class: 'ip-mask' });
    maskRow.appendChild(el('label', null, ['Override mask:']));
    var maskInput = el('input', {
      type: 'text',
      placeholder: '/24 or 255.255.255.0 or /64',
      value: state.maskOverride || state.match.mask || '',
    });
    var apply = el('button', { type: 'button', class: 'btn btn-ghost' }, ['Apply']);
    apply.addEventListener('click', function () {
      state.maskOverride = maskInput.value.trim();
      openPanel(state);
    });
    maskRow.appendChild(maskInput);
    maskRow.appendChild(apply);
    panel.appendChild(maskRow);

    var body = el('div', { class: 'ip-body' }, [
      el('div', { class: 'ip-loading' }, ['calculating…']),
    ]);
    panel.appendChild(body);

    state.link.insertAdjacentElement('afterend', panel);
    state.panel = panel;
    openStates.push(state);

    fetch(url + '?' + params.toString())
      .then(function (r) { return r.json(); })
      .then(function (data) {
        while (body.firstChild) body.removeChild(body.firstChild);
        if (!data.valid) {
          body.appendChild(el('div', { class: 'ip-error' }, ['Not a valid network: ' + (data.error || 'unknown error')]));
        } else {
          body.appendChild(renderPanel(state, data));
        }
      })
      .catch(function (e) {
        while (body.firstChild) body.removeChild(body.firstChild);
        body.appendChild(el('div', { class: 'ip-error' }, ['Request failed: ' + e.message]));
      });
  }

  var openStates = [];
  function closeAllPanels() {
    openStates.forEach(function (s) {
      if (s.panel && s.panel.parentNode) s.panel.parentNode.removeChild(s.panel);
      s.panel = null;
    });
    openStates = [];
  }
  document.addEventListener('click', function (e) {
    if (e.target.closest('.ip-link') || e.target.closest('.ip-panel')) return;
    closeAllPanels();
  });

  function attach(input) {
    if (input.dataset.ipHelperWired) return;
    input.dataset.ipHelperWired = '1';
    var scope = input.closest('[data-ip-helper-scope]');
    if (!scope) return;
    var wrap = input.parentNode;
    var link = el('a', { href: '#', class: 'ip-link', style: 'display:none' });
    wrap.insertBefore(link, input);

    var state = {
      input: input, scope: scope, link: link, match: null, panel: null, maskOverride: '',
      close: function () {
        if (state.panel && state.panel.parentNode) state.panel.parentNode.removeChild(state.panel);
        state.panel = null;
        openStates = openStates.filter(function (s) { return s !== state; });
      },
    };

    link.addEventListener('click', function (e) {
      e.preventDefault();
      if (!state.match) return;
      state.maskOverride = '';
      openPanel(state);
    });

    var timer = null;
    function refresh() {
      if (timer) clearTimeout(timer);
      timer = setTimeout(function () {
        var m = detect(input.value);
        state.match = m;
        if (m) {
          link.textContent = 'IP detected: ' + m.raw + ' — open helper';
          link.style.display = '';
        } else {
          link.style.display = 'none';
          if (state.panel) state.close();
        }
      }, 250);
    }
    input.addEventListener('input', refresh);
    refresh();
  }

  function watch() {
    document.querySelectorAll('[data-ip-helper-scope]').forEach(function (scope) {
      scope.querySelectorAll('input[type="text"], input:not([type]), textarea').forEach(attach);
    });
  }

  if (document.readyState !== 'loading') watch();
  else document.addEventListener('DOMContentLoaded', watch);

  document.body.addEventListener('htmx:afterSwap', watch);
})();
