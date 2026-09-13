/* P134 client behavior. This is presentation/validation only; server-side gates remain authoritative. */
(function () {
  const imageInput = document.getElementById('ecosystemImage');
  const preview = document.getElementById('ecosystemImagePreview');
  const imageStatus = document.getElementById('ecosystemImageStatus');
  const saveImage = document.getElementById('saveEcosystemImage');
  const MAX = 5 * 1024 * 1024;
  const ALLOWED = new Set(['image/jpeg', 'image/png', 'image/webp']);

  function validateImage(file) {
    if (!file) throw new Error('Selecione uma imagem.');
    if (!ALLOWED.has(file.type)) throw new Error('Formato não permitido. Use JPG, PNG ou WebP.');
    if (file.size <= 0 || file.size > MAX) throw new Error('A imagem deve ter até 5 MB.');
    return file;
  }

  imageInput?.addEventListener('change', () => {
    try {
      const file = validateImage(imageInput.files?.[0]);
      const url = URL.createObjectURL(file);
      preview.hidden = false;
      preview.innerHTML = '<img alt="Pré-visualização" style="max-width:100%;max-height:180px;border-radius:12px" src="' + url + '">';
      imageStatus.textContent = 'Imagem validada localmente. Ela ainda não interfere na operação.';
      imageStatus.className = 'muted ok';
    } catch (e) {
      imageInput.value = '';
      preview.hidden = true;
      imageStatus.textContent = e.message;
      imageStatus.className = 'muted danger';
    }
  });

  saveImage?.addEventListener('click', () => {
    try {
      const file = validateImage(imageInput?.files?.[0]);
      // Do not store executable/remote references. Persistence of binary data belongs
      // to the authenticated storage/API layer; this UI only records presentation intent.
      localStorage.setItem('ct_image_kind', document.getElementById('ecosystemImageKind')?.value || 'profile');
      localStorage.setItem('ct_image_name', file.name.slice(0, 120));
      imageStatus.textContent = 'Preferência de imagem registrada. Persistência segura do arquivo deve passar pelo storage do ecossistema.';
      imageStatus.className = 'muted ok';
    } catch (e) {
      imageStatus.textContent = e.message;
      imageStatus.className = 'muted danger';
    }
  });
})();
