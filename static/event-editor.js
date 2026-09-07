(() => {
  const editor = document.querySelector('[data-event-editor]');
  const preview = document.querySelector('[data-mini-preview]');
  if (!editor || !preview) return;
  const eventId = editor.dataset.eventId;
  const accent = document.querySelector('[data-accent-picker]');
  const value = document.querySelector('[data-accent-value]');
  const themes = document.querySelectorAll('input[name="theme"]');
  const input = document.querySelector('[data-cover-input]');
  const choose = document.querySelector('[data-cover-choose]');
  const remove = document.querySelector('[data-cover-remove]');
  const coverPreview = document.querySelector('[data-cover-preview]');
  const status = document.querySelector('[data-cover-status]');
  const miniCover = document.querySelector('[data-mini-cover]');
  const updateAccent = () => { if (!accent) return; preview.style.setProperty('--preview-accent', accent.value); if (value) value.textContent = accent.value.toUpperCase(); };
  const updateTheme = () => { const selected = document.querySelector('input[name="theme"]:checked'); preview.dataset.theme = selected ? selected.value : 'classic'; };
  accent?.addEventListener('input', updateAccent); themes.forEach(i => i.addEventListener('change', updateTheme)); updateAccent(); updateTheme();
  choose?.addEventListener('click', () => input?.click());
  input?.addEventListener('change', async () => { const file=input.files?.[0]; input.value=''; if (!file) return; await uploadCover(file); });
  remove?.addEventListener('click', async () => {
    if (!confirm('Remove this event cover photo?')) return;
    setBusy(true,'Removing…');
    try { const r=await fetch(`/api/events/${eventId}/cover`,{method:'DELETE'}); if(!r.ok)throw new Error(await apiError(r)); renderCover(null); status.textContent='Cover removed'; }
    catch(e){status.textContent=e.message||'Could not remove cover';}
    finally{setBusy(false);}
  });
  async function uploadCover(file){
    if(!['image/jpeg','image/png','image/webp'].includes(file.type)){status.textContent='Choose a JPG, PNG or WebP image';return;}
    if(file.size>15*1024*1024){status.textContent='Cover must be 15 MB or smaller';return;}
    const local=URL.createObjectURL(file); renderCover(local); setBusy(true,'Uploading…');
    try{
      const init=await fetch(`/api/events/${eventId}/cover`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:file.name,content_type:file.type,size_bytes:file.size})});
      if(!init.ok)throw new Error(await apiError(init)); const session=await init.json();
      const put=await fetch(session.upload_url,{method:'PUT',headers:{'Content-Type':session.content_type},body:file}); if(!put.ok)throw new Error(`Storage upload failed (${put.status})`);
      status.textContent='Finishing…'; const confirmResponse=await fetch(`/api/events/${eventId}/cover/confirm`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({object_key:session.object_key,content_type:session.content_type,size_bytes:file.size})});
      if(!confirmResponse.ok)throw new Error(await apiError(confirmResponse)); const result=await confirmResponse.json(); renderCover(`${result.cover_url}?v=${Date.now()}`); status.textContent='Cover updated ✓';
    }catch(e){status.textContent=e.message||'Cover upload failed'; location.reload();}
    finally{URL.revokeObjectURL(local);setBusy(false);}
  }
  function renderCover(src){
    [coverPreview,miniCover].forEach((box,index)=>{if(!box)return;let img=box.querySelector('img');if(src){if(!img){img=document.createElement('img');box.prepend(img);}img.src=src;box.hidden=false;if(index===0)box.classList.add('has-image');}else{img?.remove();if(index===1)box.hidden=true;if(index===0)box.classList.remove('has-image');}});
    const empty=coverPreview?.querySelector('.cover-empty');if(empty)empty.hidden=!!src;if(choose)choose.textContent=src?'Replace cover':'Choose cover photo';if(remove)remove.hidden=!src;
  }
  function setBusy(busy,text=''){if(choose)choose.disabled=busy;if(remove)remove.disabled=busy;if(text&&status)status.textContent=text;}
  async function apiError(response){try{const body=await response.json();return body.detail||`Request failed (${response.status})`;}catch(_){return `Request failed (${response.status})`;}}
})();
