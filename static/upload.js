(() => {
  const root = document.querySelector('[data-upload-root]');
  if (!root) return;

  const slug = root.dataset.eventSlug;
  const picker = document.getElementById('media-picker');
  const pickButton = document.getElementById('pick-media');
  const guestName = document.getElementById('guest-name');
  const list = document.getElementById('upload-list');

  pickButton.addEventListener('click', () => picker.click());
  picker.addEventListener('change', async () => {
    const files = Array.from(picker.files || []);
    picker.value = '';
    for (const file of files) {
      await uploadFile(file);
    }
  });

  function contentTypeFor(file) {
    if (file.type) return file.type;
    const ext = (file.name.split('.').pop() || '').toLowerCase();
    const types = {
      jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', webp: 'image/webp',
      gif: 'image/gif', heic: 'image/heic', heif: 'image/heif',
      mp4: 'video/mp4', mov: 'video/quicktime', m4v: 'video/x-m4v', webm: 'video/webm'
    };
    return types[ext] || 'application/octet-stream';
  }

  function rowFor(file) {
    const row = document.createElement('div');
    row.className = 'upload-row';
    row.innerHTML = `
      <div class="upload-row-top">
        <span class="upload-filename"></span>
        <span class="upload-state">Preparing…</span>
      </div>
      <div class="upload-progress"><span></span></div>
      <button class="upload-retry" type="button" hidden>Retry</button>
    `;
    row.querySelector('.upload-filename').textContent = file.name;
    list.prepend(row);
    return row;
  }

  async function uploadFile(file, existingRow = null) {
    const row = existingRow || rowFor(file);
    const state = row.querySelector('.upload-state');
    const bar = row.querySelector('.upload-progress span');
    const retry = row.querySelector('.upload-retry');
    retry.hidden = true;
    retry.onclick = null;
    bar.style.width = '0%';

    try {
      const contentType = contentTypeFor(file);
      state.textContent = 'Preparing…';
      const init = await fetch(`/api/events/${encodeURIComponent(slug)}/uploads`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          filename: file.name,
          content_type: contentType,
          size_bytes: file.size,
          guest_name: guestName.value.trim() || null,
        }),
      });
      if (!init.ok) throw new Error(await apiError(init));
      const session = await init.json();

      state.textContent = 'Uploading…';
      await putWithProgress(session.upload_url, file, session.content_type, progress => {
        bar.style.width = `${progress}%`;
        state.textContent = `Uploading ${progress}%`;
      });

      state.textContent = 'Finishing…';
      const confirm = await fetch(`/api/events/${encodeURIComponent(slug)}/uploads/confirm`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({media_id: session.media_id}),
      });
      if (!confirm.ok) throw new Error(await apiError(confirm));

      bar.style.width = '100%';
      row.classList.add('upload-complete');
      state.textContent = 'Uploaded ✓';
    } catch (error) {
      row.classList.add('upload-failed');
      state.textContent = error.message || 'Upload failed';
      retry.hidden = false;
      retry.onclick = () => {
        row.classList.remove('upload-failed', 'upload-complete');
        uploadFile(file, row);
      };
    }
  }

  function putWithProgress(url, file, contentType, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('PUT', url, true);
      xhr.setRequestHeader('Content-Type', contentType);
      xhr.upload.onprogress = event => {
        if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100));
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) resolve();
        else reject(new Error(`Storage upload failed (${xhr.status})`));
      };
      xhr.onerror = () => reject(new Error('Network error while uploading. Tap retry.'));
      xhr.onabort = () => reject(new Error('Upload cancelled.'));
      xhr.send(file);
    });
  }

  async function apiError(response) {
    try {
      const body = await response.json();
      return body.detail || `Request failed (${response.status})`;
    } catch (_) {
      return `Request failed (${response.status})`;
    }
  }
})();
