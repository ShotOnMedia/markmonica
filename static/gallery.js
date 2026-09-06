(() => {
  const gallery = document.querySelector('[data-gallery]');
  if (!gallery) return;

  const tiles = [...gallery.querySelectorAll('[data-media-tile]')];
  const filters = [...gallery.querySelectorAll('[data-filter]')];
  const viewButtons = [...gallery.querySelectorAll('[data-view]')];
  const mediaGrid = gallery.querySelector('[data-media-grid]');
  const selectedCount = gallery.querySelector('[data-selected-count]');
  const selectVisible = gallery.querySelector('[data-select-visible]');
  const clearSelection = gallery.querySelector('[data-clear-selection]');
  const downloadSelected = gallery.querySelector('[data-download-selected]');
  const toolbar = gallery.querySelector('[data-selection-toolbar]');
  let activeFilter = 'all';
  let activeView = localStorage.getItem('markmonica-gallery-view') === 'list' ? 'list' : 'grid';
  let lightboxIndex = -1;

  const selectedTiles = () => tiles.filter(tile => tile.querySelector('[data-media-select]').checked);
  const visibleTiles = () => tiles.filter(tile => !tile.hidden);
  const lightboxItems = () => visibleTiles().map(tile => tile.querySelector('[data-lightbox-item]')).filter(Boolean);

  function refreshSelection() {
    const count = selectedTiles().length;
    selectedCount.textContent = `${count} selected`;
    downloadSelected.disabled = count === 0;
    clearSelection.disabled = count === 0;
    toolbar.classList.toggle('has-selection', count > 0);
    tiles.forEach(tile => tile.classList.toggle('is-selected', tile.querySelector('[data-media-select]').checked));
  }

  function applyFilter(filter) {
    activeFilter = filter;
    filters.forEach(button => button.classList.toggle('is-active', button.dataset.filter === filter));
    tiles.forEach(tile => { tile.hidden = filter !== 'all' && tile.dataset.mediaType !== filter; });
    const visible = visibleTiles();
    const selectedVisible = visible.filter(tile => tile.querySelector('[data-media-select]').checked);
    selectVisible.textContent = visible.length && selectedVisible.length === visible.length ? 'Clear visible' : 'Select visible';
  }

  function applyView(view) {
    activeView = view === 'list' ? 'list' : 'grid';
    mediaGrid.classList.toggle('media-list', activeView === 'list');
    viewButtons.forEach(button => {
      const active = button.dataset.view === activeView;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    localStorage.setItem('markmonica-gallery-view', activeView);
  }

  filters.forEach(button => button.addEventListener('click', () => applyFilter(button.dataset.filter)));
  viewButtons.forEach(button => button.addEventListener('click', () => applyView(button.dataset.view)));
  tiles.forEach(tile => {
    const checkbox = tile.querySelector('[data-media-select]');
    checkbox.addEventListener('change', () => { refreshSelection(); applyFilter(activeFilter); });
  });

  selectVisible.addEventListener('click', () => {
    const visible = visibleTiles();
    const shouldSelect = visible.some(tile => !tile.querySelector('[data-media-select]').checked);
    visible.forEach(tile => { tile.querySelector('[data-media-select]').checked = shouldSelect; });
    refreshSelection(); applyFilter(activeFilter);
  });

  clearSelection.addEventListener('click', () => {
    tiles.forEach(tile => { tile.querySelector('[data-media-select]').checked = false; });
    refreshSelection(); applyFilter(activeFilter);
  });

  async function saveOriginal(tile) {
    const response = await fetch(tile.dataset.originalUrl, { credentials: 'same-origin' });
    if (!response.ok) throw new Error(`Download failed (${response.status})`);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url; link.download = tile.dataset.filename || 'memory';
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  downloadSelected.addEventListener('click', async () => {
    const selected = selectedTiles();
    if (!selected.length) return;
    const originalText = downloadSelected.textContent;
    downloadSelected.disabled = true;
    try {
      for (let index = 0; index < selected.length; index += 1) {
        downloadSelected.textContent = `Downloading ${index + 1} of ${selected.length}…`;
        await saveOriginal(selected[index]);
        await new Promise(resolve => setTimeout(resolve, 250));
      }
    } catch (error) {
      window.alert(`One or more downloads could not be completed. ${error.message}`);
    } finally {
      downloadSelected.textContent = originalText; refreshSelection();
    }
  });

  const lightbox = document.createElement('div');
  lightbox.className = 'gallery-lightbox';
  lightbox.hidden = true;
  lightbox.innerHTML = '<button type="button" class="lightbox-close" aria-label="Close">×</button><button type="button" class="lightbox-nav lightbox-prev" aria-label="Previous">‹</button><div class="lightbox-stage"><img alt=""><div class="lightbox-caption"></div></div><button type="button" class="lightbox-nav lightbox-next" aria-label="Next">›</button>';
  document.body.appendChild(lightbox);
  const lightboxImage = lightbox.querySelector('img');
  const lightboxCaption = lightbox.querySelector('.lightbox-caption');

  function showLightbox(index) {
    const items = lightboxItems();
    if (!items.length) return;
    lightboxIndex = (index + items.length) % items.length;
    const item = items[lightboxIndex];
    lightboxImage.src = item.href;
    lightboxImage.alt = item.dataset.lightboxTitle || '';
    lightboxCaption.textContent = item.dataset.lightboxTitle || '';
    lightbox.hidden = false;
    document.body.classList.add('lightbox-open');
  }

  function closeLightbox() {
    lightbox.hidden = true;
    lightboxImage.removeAttribute('src');
    document.body.classList.remove('lightbox-open');
    lightboxIndex = -1;
  }

  gallery.addEventListener('click', event => {
    const item = event.target.closest('[data-lightbox-item]');
    if (!item) return;
    event.preventDefault();
    const items = lightboxItems();
    showLightbox(items.indexOf(item));
  });
  lightbox.querySelector('.lightbox-close').addEventListener('click', closeLightbox);
  lightbox.querySelector('.lightbox-prev').addEventListener('click', () => showLightbox(lightboxIndex - 1));
  lightbox.querySelector('.lightbox-next').addEventListener('click', () => showLightbox(lightboxIndex + 1));
  lightbox.addEventListener('click', event => { if (event.target === lightbox) closeLightbox(); });
  document.addEventListener('keydown', event => {
    if (lightbox.hidden) return;
    if (event.key === 'Escape') closeLightbox();
    if (event.key === 'ArrowLeft') showLightbox(lightboxIndex - 1);
    if (event.key === 'ArrowRight') showLightbox(lightboxIndex + 1);
  });

  refreshSelection(); applyFilter('all'); applyView(activeView);
})();
