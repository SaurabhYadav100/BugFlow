// BugFlow behaviour that Bootstrap doesn't provide: sidebar toggle, modal prefill, bulk select, auto-submit filters.
(function () {
  var toggle = document.getElementById('menuToggle');
  if (toggle) toggle.addEventListener('click', function () {
    // phones: slide the menu in/out; desktop: collapse/expand it
    document.body.classList.toggle(window.innerWidth < 992 ? 'nav-open' : 'nav-collapsed');
  });

  // Prefill Bootstrap modals from the button that opened them:
  // <button data-bs-toggle="modal" data-bs-target="#assignModal" data-action="/url" data-label="BUG-1" data-assignee="3">
  document.addEventListener('show.bs.modal', function (e) {
    var btn = e.relatedTarget, modal = e.target;
    if (!btn) return;
    var form = modal.querySelector('form');
    if (btn.dataset.action && form) form.action = btn.dataset.action;
    modal.querySelectorAll('[data-fill]').forEach(function (el) {
      var v = btn.dataset[el.dataset.fill];
      if (v === undefined) return;
      if (['INPUT', 'SELECT', 'TEXTAREA'].indexOf(el.tagName) > -1) el.value = v; else el.textContent = v;
    });
  });

  // Bulk select on the issue list
  var all = document.querySelector('[data-select-all]');
  var rows = document.querySelectorAll('[data-select-row]');
  var bulk = document.getElementById('bulkBar');
  function refresh() {
    var n = document.querySelectorAll('[data-select-row]:checked').length;
    if (bulk) { bulk.classList.toggle('d-none', n === 0); bulk.querySelector('[data-count]').textContent = n; }
  }
  if (all) all.addEventListener('change', function () { rows.forEach(function (r) { r.checked = all.checked; }); refresh(); });
  rows.forEach(function (r) { r.addEventListener('change', refresh); });

  // Live filter: <input data-filter="#list"> hides the [data-filter-item] elements inside #list that do not match
  document.querySelectorAll('input[data-filter]').forEach(function (input) {
    input.addEventListener('input', function () {
      var q = input.value.trim().toLowerCase();
      var target = document.querySelector(input.dataset.filter);

      if (!target) return;
      var items = target.querySelectorAll('[data-filter-item]');

      items.forEach(function (el) {

        var text = (el.dataset.filterText || el.textContent).toLowerCase();

        el.classList.toggle('d-none', q !== '' && text.indexOf(q) === -1);
           
      });
    });
  });

  // Filters submit as soon as a dropdown changes
  document.querySelectorAll('select[data-autosubmit]').forEach(function (s) {
    s.addEventListener('change', function () { s.form.submit(); });
  });
})();

