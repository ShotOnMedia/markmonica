(() => {
  if (!document.querySelector('link[href="/static/event-experience.css"]')) {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = '/static/event-experience.css';
    document.head.appendChild(link);
  }
  const preview = document.querySelector('[data-mini-preview]');
  if (!preview) return;
  const accent = document.querySelector('[data-accent-picker]');
  const value = document.querySelector('[data-accent-value]');
  const themes = document.querySelectorAll('input[name="theme"]');
  const updateAccent = () => { if (!accent) return; preview.style.setProperty('--preview-accent', accent.value); if (value) value.textContent = accent.value.toUpperCase(); };
  const updateTheme = () => { const selected = document.querySelector('input[name="theme"]:checked'); preview.dataset.theme = selected ? selected.value : 'classic'; };
  accent?.addEventListener('input', updateAccent);
  themes.forEach(input => input.addEventListener('change', updateTheme));
  updateAccent(); updateTheme();
})();
