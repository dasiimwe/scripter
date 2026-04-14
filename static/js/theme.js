// Theme selector — binds .theme-chip buttons, persists choice to localStorage.
// The initial attribute is set by an inline <script> in <head> to prevent FOUC.
(function () {
  const KEY = 'scripter.theme';
  const VALID = new Set(['operator', 'datasheet']);
  const DEFAULT = 'datasheet';

  function current() {
    const stored = localStorage.getItem(KEY);
    return VALID.has(stored) ? stored : DEFAULT;
  }

  function apply(theme) {
    if (!VALID.has(theme)) theme = DEFAULT;
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(KEY, theme);
    document.querySelectorAll('.theme-chip').forEach(btn => {
      btn.setAttribute('aria-pressed', btn.dataset.theme === theme ? 'true' : 'false');
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    apply(current());
    document.querySelectorAll('.theme-chip').forEach(btn => {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        apply(btn.dataset.theme);
      });
    });
  });
})();
