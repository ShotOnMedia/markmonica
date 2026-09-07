(() => {
  const body = document.body;
  const accent = body.dataset.accent || '';
  if (/^#[0-9a-fA-F]{6}$/.test(accent)) {
    document.documentElement.style.setProperty('--event-accent', accent);
  }
})();
