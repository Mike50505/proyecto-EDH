(() => {
  const storageKey = 'edh.appearance.v1';
  const systemDark = window.matchMedia('(prefers-color-scheme: dark)');
  let savedTheme = null;
  try { savedTheme = localStorage.getItem(storageKey); } catch (_) { /* Storage may be disabled. */ }
  if (savedTheme !== 'light' && savedTheme !== 'dark') savedTheme = null;

  const currentTheme = () => savedTheme || (systemDark.matches ? 'dark' : 'light');

  const applyTheme = () => {
    const dark = currentTheme() === 'dark';
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    document.querySelectorAll('[data-theme-toggle]').forEach(button => {
      button.setAttribute('aria-pressed', String(dark));
      button.setAttribute('aria-label', dark ? 'Activar modo claro' : 'Activar modo oscuro');
      button.title = dark ? 'Activar modo claro' : 'Activar modo oscuro';
      button.querySelector('.theme-icon').textContent = dark ? '☀︎' : '☾';
      button.querySelector('[data-theme-label]').textContent = dark ? 'Modo claro' : 'Modo oscuro';
    });
  };

  applyTheme();
  systemDark.addEventListener('change', () => { if (!savedTheme) applyTheme(); });
  document.addEventListener('DOMContentLoaded', () => {
    applyTheme();
    document.querySelectorAll('[data-theme-toggle]').forEach(button => button.addEventListener('click', () => {
      savedTheme = currentTheme() === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem(storageKey, savedTheme); } catch (_) { /* Storage may be disabled. */ }
      applyTheme();
    }));
  });
})();
