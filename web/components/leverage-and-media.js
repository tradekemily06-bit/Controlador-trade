/* Presentation-only validation. Server/storage gates remain authoritative. */
(function(){
  const input=document.getElementById('ecosystemImage'),preview=document.getElementById('ecosystemImagePreview'),status=document.getElementById('ecosystemImageStatus'),save=document.getElementById('saveEcosystemImage'),kind=document.getElementById('ecosystemImageKind');
  const MAX=5*1024*1024,ALLOWED=new Set(['image/jpeg','image/png','image/webp']);
  function validate(file){if(!file)throw Error('Selecione uma imagem.');if(!ALLOWED.has(file.type))throw Error('Formato não permitido. Use JPG, PNG ou WebP.');if(file.size<=0||file.size>MAX)throw Error('A imagem deve ter até 5 MB.');return file;}
  function showPreview(url){preview.replaceChildren();const img=document.createElement('img');img.alt='Pré-visualização da imagem do ecossistema';img.style.maxWidth='100%';img.style.maxHeight='180px';img.style.borderRadius='12px';img.src=url;preview.appendChild(img);preview.hidden=false;}
  async function loadExisting(){
    try{const response=await fetch('/api/ecosystem-image?kind='+encodeURIComponent(kind?.value||'profile'),{cache:'no-store'});if(!response.ok)return;const blob=await response.blob();showPreview(URL.createObjectURL(blob));status.textContent='Imagem compartilhada carregada do ecossistema.';status.className='muted ok';}
    catch(_){}
  }
  input?.addEventListener('change',()=>{try{const f=validate(input.files?.[0]);showPreview(URL.createObjectURL(f));status.textContent='Imagem validada localmente; ainda não salva.';status.className='muted ok';}catch(e){input.value='';preview.hidden=true;status.textContent=e.message;status.className='muted danger';}});
  kind?.addEventListener('change',loadExisting);
  save?.addEventListener('click',async()=>{try{const f=validate(input?.files?.[0]);const dataUrl=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result));reader.onerror=()=>reject(new Error('Não foi possível ler a imagem.'));reader.readAsDataURL(f);});const response=await fetch('/api/ecosystem-image',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:kind?.value||'profile',data_url:dataUrl})});const payload=await response.json();if(!response.ok)throw Error(payload.error||'Falha ao salvar imagem.');status.textContent='Imagem salva no ecossistema e disponível nos outros dispositivos conectados ao mesmo runtime.';status.className='muted ok';await loadExisting();}catch(e){status.textContent=e.message;status.className='muted danger';}});
  loadExisting();
})();