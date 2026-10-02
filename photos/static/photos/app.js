(function () {
  var root = document.documentElement;

  // Волна от точки нажатия на любой кнопке
  document.addEventListener('pointerdown', function (e) {
    var btn = e.target.closest('.btn, .icon-btn, .tab');
    if (!btn || btn.disabled) return;
    var r = btn.getBoundingClientRect();
    var size = Math.max(r.width, r.height) * 2.2;
    var dot = document.createElement('span');
    dot.className = 'ripple';
    dot.style.width = dot.style.height = size + 'px';
    dot.style.left = (e.clientX - r.left - size / 2) + 'px';
    dot.style.top = (e.clientY - r.top - size / 2) + 'px';
    btn.appendChild(dot);
    setTimeout(function () { dot.remove(); }, 650);
  });
  var reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Тема: по умолчанию как на устройстве. Если человек сам переключил тему,
  // запоминаем выбор. Если он вернул ту же тему, что в системе, снова следуем системе.
  var systemDark = matchMedia('(prefers-color-scheme: dark)');
  function systemTheme() { return systemDark.matches ? 'dark' : 'light'; }

  function applyTheme(theme) {
    root.dataset.theme = theme;
    try {
      if (theme === systemTheme()) localStorage.removeItem('theme');
      else localStorage.setItem('theme', theme);
    } catch (e) {}
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = theme === 'dark' ? '#0A0A0B' : '#F3F3F5';
  }

  function savedTheme() {
    try { return localStorage.getItem('theme'); } catch (e) { return null; }
  }

  // Система переключилась (например, вечером включился тёмный режим) — сайт следом,
  // если человек не выбирал тему сам
  systemDark.addEventListener('change', function () {
    if (savedTheme()) return;
    var next = systemTheme();
    if (document.startViewTransition && !reduceMotion) document.startViewTransition(function () { applyTheme(next); });
    else applyTheme(next);
  });
  applyTheme(savedTheme() || systemTheme());

  var toggle = document.getElementById('themeToggle');
  if (toggle) toggle.addEventListener('click', function () {
    var next = root.dataset.theme === 'dark' ? 'light' : 'dark';
    if (reduceMotion) return applyTheme(next);
    if (document.startViewTransition) return document.startViewTransition(function () { applyTheme(next); });
    root.classList.add('theme-fade');
    applyTheme(next);
    setTimeout(function () { root.classList.remove('theme-fade'); }, 450);
  });

  // Кнопки «Копировать» (через делегирование: работает и для кнопок, добавленных позже)
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-copy]');
    if (!btn) return;
    var input = document.getElementById(btn.dataset.copy);
    if (!input) return;
    var label = btn.querySelector('span:not(.ripple)'), use = btn.querySelector('use');
    var done = function () {
      var old = label ? label.textContent : '', oldIcon = use.getAttribute('href');
      if (label) label.textContent = 'Скопировано';
      use.setAttribute('href', '#i-check');
      btn.classList.remove('is-done'); void btn.offsetWidth; btn.classList.add('is-done');
      setTimeout(function () { if (label) label.textContent = old; use.setAttribute('href', oldIcon); btn.classList.remove('is-done'); }, 1500);
    };
    if (navigator.clipboard) navigator.clipboard.writeText(input.value).then(done, function () { input.select(); });
    else { input.select(); document.execCommand('copy'); done(); }
  });

  // Фото крупно: нажатие на фото на странице поста
  var lb = document.getElementById('lightbox');
  if (lb) {
    var stage = lb.querySelector('.lb-stage');
    var closeLb = function () {
      if (!lb.open) return;
      if (reduceMotion) { lb.close(); return; }
      lb.classList.add('closing');
      setTimeout(function () { lb.classList.remove('closing'); lb.close(); stage.innerHTML = ''; }, 200);
    };
    document.addEventListener('click', function (e) {
      var z = e.target.closest('[data-zoom]');
      if (!z) return;
      var src = z.querySelector('img, .shot');
      if (!src) return;
      var media = src.cloneNode(true);
      media.removeAttribute('loading');
      media.className = 'lb-media' + (media.tagName === 'IMG' ? '' : ' shot');
      if (media.tagName !== 'IMG') {   // картинка-заглушка в превью: считаем размер по пропорциям
        var ar = (src.style.aspectRatio || '1/1').split('/'), r = parseFloat(ar[0]) / parseFloat(ar[1] || 1);
        media.style.maxHeight = 'none';
        media.style.width = 'min(calc(100vw - 24px), calc((100svh - 24px) * ' + r + '))';
      }
      stage.innerHTML = '';
      stage.appendChild(media);
      lb.showModal();
    });
    lb.querySelector('.lb-close').addEventListener('click', closeLb);
    stage.addEventListener('click', function () { if (!dragged) closeLb(); });
    lb.addEventListener('cancel', function (e) { e.preventDefault(); closeLb(); });   // Esc

    // Смахнуть вниз или вверх, чтобы закрыть (на телефоне)
    var startY = null, dragged = false;
    stage.addEventListener('pointerdown', function (e) { startY = e.clientY; dragged = false; });
    stage.addEventListener('pointermove', function (e) {
      if (startY === null) return;
      var dy = e.clientY - startY, m = stage.firstChild;
      if (Math.abs(dy) > 8) dragged = true;
      if (m) { m.style.transition = 'none'; m.style.transform = 'translateY(' + dy + 'px)'; m.style.opacity = String(1 - Math.min(Math.abs(dy) / 400, .6)); }
    });
    var endDrag = function (e) {
      if (startY === null) return;
      var dy = e.clientY - startY, m = stage.firstChild;
      startY = null;
      if (m) { m.style.transition = ''; m.style.transform = ''; m.style.opacity = ''; }
      if (Math.abs(dy) > 90) closeLb();
      setTimeout(function () { dragged = false; }, 0);
    };
    stage.addEventListener('pointerup', endDrag);
    stage.addEventListener('pointercancel', endDrag);
  }

  // Окно загрузки
  var dialog = document.getElementById('uploadDialog');
  var addBtn = document.querySelector('.add-btn');
  function openUpload() {
    if (!dialog || dialog.open) return;
    dialog.classList.remove('closing');
    dialog.showModal();
    if (addBtn) addBtn.setAttribute('aria-expanded', 'true');
  }
  function closeUpload() {
    if (!dialog || !dialog.open) return;
    if (reduceMotion) { dialog.close(); return; }
    dialog.classList.add('closing');
    setTimeout(function () { dialog.classList.remove('closing'); dialog.close(); }, 220);
  }
  if (dialog) {
    dialog.addEventListener('close', function () { if (addBtn) addBtn.setAttribute('aria-expanded', 'false'); });
    dialog.addEventListener('cancel', function (e) { e.preventDefault(); closeUpload(); });   // Esc
    dialog.addEventListener('click', function (e) { if (e.target === dialog) closeUpload(); }); // тап по фону
    if (dialog.hasAttribute('data-autoopen')) openUpload();
  }
  document.addEventListener('click', function (e) {
    if (e.target.closest('[data-open-upload]')) openUpload();
    if (e.target.closest('[data-close-upload]')) closeUpload();
  });
  // Если тащат файл на страницу — сразу открываем окно загрузки
  window.addEventListener('dragenter', function (e) {
    if (e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types, 'Files') !== -1) openUpload();
  });

  // Загрузка: перетаскивание, выбор файла и вставка из буфера (Ctrl+V)
  var drop = document.querySelector('.drop');
  if (drop) {
    var input = drop.querySelector('input[type=file]');
    var show = function (file) {
      var old = drop.querySelector('.preview');
      if (old) old.remove();
      if (!file) { drop.classList.remove('has-file'); var u = drop.closest('.uploader'); if (u) u.classList.remove('picked'); return; }
      var isVideo = /^video\//.test(file.type);
      var el = document.createElement(isVideo ? 'video' : 'img');
      el.className = 'preview';
      if (isVideo) { el.muted = true; el.playsInline = true; el.autoplay = true; el.loop = true; } else { el.alt = ''; }
      el.src = URL.createObjectURL(file);
      drop.appendChild(el);
      drop.classList.add('has-file');
      var up = drop.closest('.uploader'); if (up) up.classList.add('picked');
    };
    var form = drop.closest('form'), submit = document.getElementById('submitBtn');
    var errBox = document.createElement('p');
    errBox.className = 'client-error'; errBox.hidden = true; errBox.setAttribute('role', 'alert');
    drop.insertAdjacentElement('afterend', errBox);
    function sizeError(file) {
      if (!file) return '';
      var mb = file.size / 1048576, video = /^video\//.test(file.type);
      if (video && mb > 200) return 'Видео больше 200 МБ. Обрежь его или сожми.';
      if (!video && mb > 20) return 'Фото больше 20 МБ.';
      return '';
    }
    input.addEventListener('change', function () {
      var msg = sizeError(input.files[0]);
      errBox.textContent = msg; errBox.hidden = !msg;
    });

    // Отправка с прогрессом: большое видео грузится долго, пусть будет видно сколько осталось
    if (form && submit) form.addEventListener('submit', function (e) {
      var msg = sizeError(input.files[0]);
      if (msg) { e.preventDefault(); errBox.textContent = msg; errBox.hidden = false; return; }
      if (!window.XMLHttpRequest || !window.FormData) return;   // старый браузер — обычная отправка
      e.preventDefault();
      submit.classList.add('is-loading');
      submit.textContent = 'Загружаем…';
      var xhr = new XMLHttpRequest();
      xhr.open('POST', form.action);
      xhr.upload.addEventListener('progress', function (ev) {
        if (ev.lengthComputable) {
          var pct = Math.round(ev.loaded / ev.total * 100);
          submit.textContent = pct < 100 ? 'Загружаем… ' + pct + '%' : 'Обрабатываем…';
          submit.style.setProperty('--progress', pct + '%');
        }
      });
      xhr.onload = function () {
        if (xhr.status < 400 && xhr.responseURL) { window.location.href = xhr.responseURL; return; }
        document.open(); document.write(xhr.responseText); document.close();   // страница с ошибкой
      };
      xhr.onerror = function () {
        submit.classList.remove('is-loading');
        submit.textContent = 'Опубликовать';
        submit.style.removeProperty('--progress');
        errBox.textContent = 'Не получилось отправить файл. Проверь интернет и попробуй ещё раз.';
        errBox.hidden = false;
      };
      xhr.send(new FormData(form));
    });
    ['dragenter', 'dragover'].forEach(function (ev) { drop.addEventListener(ev, function () { drop.classList.add('is-over'); }); });
    ['dragleave', 'drop'].forEach(function (ev) { drop.addEventListener(ev, function () { drop.classList.remove('is-over'); }); });
    input.addEventListener('change', function () { show(input.files[0]); });
    document.addEventListener('paste', function (e) {
      var file = Array.prototype.map.call(e.clipboardData.items, function (it) { return it.getAsFile(); })
        .filter(function (f) { return f && /^image\//.test(f.type); })[0];
      if (!file) return;
      var dt = new DataTransfer();
      dt.items.add(file);
      input.files = dt.files;
      openUpload();
      show(file);
    });
  }
})();
