/* Presentation/validation only. Server-side security and storage remain authoritative. */
(function () {
  const imageInput = document.getElementById('ecosystemImage');
  const preview = document.getElementById('ecosystemImagePreview');
  const status = document.getElementById('ecosystemImageStatus');
  const save = document.getElementById('saveEcosystemImage');
  const MAX = 5 * 1024 * 1024;
  const ALLOWED = new Set(['image/jpeg', 'image/png', 'image/webp']);
  let previewUrl = null;

  function validate(file) {
    if (!file) throw new Error('Selecione uma imagem.');
    if (!ALLOWED.has(file.type)) throw new Error('Formato não permitido.');
    if (file.size <= 0 || file.size > MAX) throw new Error('A imagem deve ter até 5 MB.');
    return file;
  }

  imageInput?.addEventListener('change', () => {
    try {
      const file = validate(imageInput.files?.[0]);
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      previewUrl = URL.createObjectURL(file);
      preview.hidden = false;
      preview.replaceChildren();
      const img = document.createElement('img');
      img.alt = 'Pré-visualização';
      img.style.maxWidth = '100%';
      img.style.maxHeight = '180px';
      img.style.borderRadius = '12px';
      img.src = previewUrl;
      preview.appendChild(img);
      status.textContent = 'Imagem validada localmente; não participa da operação.';
    } catch (error) {
      imageInput.value = '';
      preview.hidden = true;
      status.textContent = error.message;
    }
  });

  save?.addEventListener('click', () => {
    try {
      const file = validate(imageInput?.files?.[0]);
      const kind = document.getElementById('ecosystemImageKind')?.value || 'profile';
      // Binary persistence must use authenticated, server-side storage validation.
      status.textContent = `Imagem ${kind} validada. O arquivo ainda não foi persistido pelo cliente.`;
      void file;
    } catch (error) {
      status.textContent = error.message;
    }
  });
})();
