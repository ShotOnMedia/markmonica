(() => {
  const gallery=document.querySelector('[data-guest-gallery]'),lightbox=document.querySelector('[data-guest-lightbox]');if(!gallery||!lightbox)return;
  const stage=lightbox.querySelector('[data-guest-lightbox-stage]'),caption=lightbox.querySelector('[data-guest-lightbox-caption]'),close=lightbox.querySelector('[data-guest-lightbox-close]'),prev=lightbox.querySelector('[data-guest-lightbox-prev]'),next=lightbox.querySelector('[data-guest-lightbox-next]'),items=Array.from(gallery.querySelectorAll('[data-guest-memory]'));let index=-1;
  items.forEach((item,i)=>item.addEventListener('click',()=>open(i)));close.addEventListener('click',hide);prev.addEventListener('click',()=>show(index-1));next.addEventListener('click',()=>show(index+1));lightbox.addEventListener('click',e=>{if(e.target===lightbox)hide();});document.addEventListener('keydown',e=>{if(lightbox.hidden)return;if(e.key==='Escape')hide();if(e.key==='ArrowLeft')show(index-1);if(e.key==='ArrowRight')show(index+1);});
  function open(i){lightbox.hidden=false;document.body.classList.add('guest-lightbox-open');show(i);close.focus();}
  function show(i){
    if(!items.length)return;stopVideo();index=(i+items.length)%items.length;const item=items[index],name=item.dataset.uploader||'Guest';stage.replaceChildren();
    if(item.dataset.type==='video'&&item.dataset.playUrl){const video=document.createElement('video');video.src=item.dataset.playUrl;video.poster=item.dataset.previewUrl;video.controls=true;video.playsInline=true;video.preload='metadata';video.autoplay=true;video.setAttribute('controlsList','nodownload');stage.appendChild(video);video.play().catch(()=>{});caption.textContent=`Video shared by ${name}`;}
    else{const img=document.createElement('img');img.src=item.dataset.previewUrl;img.alt=`Memory shared by ${name}`;stage.appendChild(img);caption.textContent=`Shared by ${name}`;}
    prev.hidden=next.hidden=items.length<2;
  }
  function stopVideo(){const video=stage.querySelector('video');if(video){video.pause();video.removeAttribute('src');video.load();}}
  function hide(){stopVideo();lightbox.hidden=true;document.body.classList.remove('guest-lightbox-open');stage.replaceChildren();}
})();
