(() => {
  const gallery = document.querySelector('[data-guest-gallery]');
  const lightbox = document.querySelector('[data-guest-lightbox]');
  if (!gallery || !lightbox) return;

  const stage = lightbox.querySelector('[data-guest-lightbox-stage]');
  const caption = lightbox.querySelector('[data-guest-lightbox-caption]');
  const close = lightbox.querySelector('[data-guest-lightbox-close]');
  const prev = lightbox.querySelector('[data-guest-lightbox-prev]');
  const next = lightbox.querySelector('[data-guest-lightbox-next]');
  const items = Array.from(gallery.querySelectorAll('[data-guest-memory]'));
  let index = -1;

  items.forEach((item, i) => item.addEventListener('click', () => open(i)));
  close.addEventListener('click', hide);
  prev.addEventListener('click', () => show(index - 1));
  next.addEventListener('click', () => show(index + 1));
  lightbox.addEventListener('click', event => { if (event.target === lightbox) hide(); });
  document.addEventListener('keydown', event => {
    if (lightbox.hidden) return;
    if (event.key === 'Escape') hide();
    if (event.key === 'ArrowLeft') show(index - 1);
    if (event.key === 'ArrowRight') show(index + 1);
  });

  function open(i) {
    lightbox.hidden = false;
    document.body.classList.add('guest-lightbox-open');
    show(i);
    close.focus();
  }

  function show(i) {
    if (!items.length) return;
    index = (i + items.length) % items.length;
    const item = items[index];
    const type = item.dataset.type;
    const name = item.dataset.uploader || 'Guest';
    stage.replaceChildren();
    if (type === 'video') {
      const video = document.createElement('video');
      video.controls = true; video.autoplay = true; video.playsInline = true;
      video.src = item.dataset.playUrl;
      if (item.dataset.posterUrl) video.poster = item.dataset.posterUrl;
      stage.appendChild(video);
    } else {
      const img = document.createElement('img');
      img.src = item.dataset.originalUrl; img.alt = `Memory shared by ${name}`;
      stage.appendChild(img);
    }
    caption.textContent = `Shared by ${name}`;
    prev.hidden = next.hidden = items.length < 2;
  }

  function hide() {
    lightbox.hidden = true;
    document.body.classList.remove('guest-lightbox-open');
    stage.querySelector('video')?.pause();
    stage.replaceChildren();
  }
})();
