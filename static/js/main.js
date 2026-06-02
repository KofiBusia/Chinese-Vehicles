/* ============================================================
   AutoPower Dealership — Main JavaScript
   ============================================================ */

document.addEventListener('DOMContentLoaded', () => {

  // ── Navbar scroll behaviour ──────────────────────────────────
  const nav = document.getElementById('mainNav');
  if (nav) {
    const onScroll = () => {
      nav.classList.toggle('scrolled', window.scrollY > 40);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  // ── Mobile menu ──────────────────────────────────────────────
  const burger  = document.getElementById('navHamburger');
  const overlay = document.getElementById('navOverlay');
  const overlayClose = document.getElementById('overlayClose');

  if (burger && overlay) {
    const openMenu = () => {
      burger.classList.add('open');
      overlay.classList.add('open');
      document.body.style.overflow = 'hidden';
    };
    const closeMenu = () => {
      burger.classList.remove('open');
      overlay.classList.remove('open');
      document.body.style.overflow = '';
    };
    burger.addEventListener('click', openMenu);
    if (overlayClose) overlayClose.addEventListener('click', closeMenu);
    overlay.querySelectorAll('.nav-link').forEach(l => l.addEventListener('click', closeMenu));
  }

  // ── Flash auto-dismiss ───────────────────────────────────────
  document.querySelectorAll('.flash').forEach(el => {
    const delay = el.classList.contains('flash-info') || el.classList.contains('flash-success')
      ? 30000   // finance / referral messages: 30 s
      : 6000;   // errors / warnings: 6 s
    setTimeout(() => el.remove(), delay);
  });

  // ── Scroll reveal animations ─────────────────────────────────
  const revealObserver = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        e.target.classList.add('visible');
        revealObserver.unobserve(e.target);
      }
    });
  }, { threshold: 0.12 });

  document.querySelectorAll('.reveal').forEach(el => revealObserver.observe(el));

  // ── Image gallery / lightbox ─────────────────────────────────
  const lightbox   = document.getElementById('lightbox');
  const lbImg      = document.getElementById('lightboxImg');
  const lbClose    = document.getElementById('lightboxClose');
  const lbPrev     = document.getElementById('lightboxPrev');
  const lbNext     = document.getElementById('lightboxNext');
  const mainImg    = document.getElementById('detailMainImg');
  const thumbs     = document.querySelectorAll('.gallery-thumb');

  let galleryImages = [];
  let currentIndex  = 0;

  if (thumbs.length > 0) {
    galleryImages = Array.from(thumbs).map(t => t.src);
  }

  // Thumbnail click → update main image
  thumbs.forEach((thumb, i) => {
    thumb.addEventListener('click', () => {
      if (mainImg) mainImg.src = thumb.src;
      thumbs.forEach(t => t.classList.remove('active'));
      thumb.classList.add('active');
      currentIndex = i;
    });
  });

  // Gallery nav buttons
  const galleryPrev = document.getElementById('galleryPrev');
  const galleryNext = document.getElementById('galleryNext');
  if (galleryPrev && galleryNext && thumbs.length) {
    galleryPrev.addEventListener('click', () => {
      currentIndex = (currentIndex - 1 + galleryImages.length) % galleryImages.length;
      thumbs[currentIndex].click();
    });
    galleryNext.addEventListener('click', () => {
      currentIndex = (currentIndex + 1) % galleryImages.length;
      thumbs[currentIndex].click();
    });
  }

  // Open lightbox on main image click
  if (mainImg && lightbox) {
    mainImg.addEventListener('click', () => openLightbox(currentIndex));
  }

  function openLightbox(idx) {
    if (!lightbox || galleryImages.length === 0) return;
    currentIndex = idx;
    lbImg.src = galleryImages[currentIndex];
    lightbox.classList.add('open');
    document.body.style.overflow = 'hidden';
  }
  function closeLightbox() {
    lightbox && lightbox.classList.remove('open');
    document.body.style.overflow = '';
  }
  function lbNavigate(dir) {
    currentIndex = (currentIndex + dir + galleryImages.length) % galleryImages.length;
    lbImg.src = galleryImages[currentIndex];
  }

  if (lbClose) lbClose.addEventListener('click', closeLightbox);
  if (lbPrev)  lbPrev.addEventListener('click', () => lbNavigate(-1));
  if (lbNext)  lbNext.addEventListener('click', () => lbNavigate(1));
  if (lightbox) lightbox.addEventListener('click', e => { if (e.target === lightbox) closeLightbox(); });

  document.addEventListener('keydown', e => {
    if (!lightbox || !lightbox.classList.contains('open')) return;
    if (e.key === 'Escape')    closeLightbox();
    if (e.key === 'ArrowLeft')  lbNavigate(-1);
    if (e.key === 'ArrowRight') lbNavigate(1);
  });

  // ── Loan page: dynamic product selector ─────────────────────
  const productTypeEl = document.getElementById('product_type');
  const vehicleGroup  = document.getElementById('vehicleGroup');
  const solarGroup    = document.getElementById('solarGroup');
  const productNameEl = document.getElementById('product_name');
  const productPriceEl = document.getElementById('product_price_display');
  const loanAmountEl  = document.getElementById('loan_amount');
  const depositEl     = document.getElementById('deposit_amount');

  function updateProductGroups() {
    if (!productTypeEl) return;
    const val = productTypeEl.value;
    if (vehicleGroup) vehicleGroup.style.display = val === 'vehicle' ? '' : 'none';
    if (solarGroup)   solarGroup.style.display   = val === 'solar'   ? '' : 'none';
  }

  if (productTypeEl) {
    productTypeEl.addEventListener('change', updateProductGroups);
    updateProductGroups();
  }

  // Auto-fill loan amount when product selected
  function onProductSelect(selectEl) {
    if (!selectEl) return;
    selectEl.addEventListener('change', () => {
      const opt = selectEl.options[selectEl.selectedIndex];
      const price = parseFloat(opt.dataset.price || 0);
      if (productNameEl) productNameEl.value = opt.text.split(' — ')[0];
      if (productPriceEl) productPriceEl.textContent = price > 0 ? `$${price.toLocaleString('en-US', {minimumFractionDigits: 2})}` : '';
      if (loanAmountEl && price > 0) {
        const deposit = parseFloat(depositEl?.value || 0);
        loanAmountEl.value = Math.max(0, price - deposit).toFixed(2);
        updateLoanPreview();
      }
    });
  }
  onProductSelect(document.getElementById('vehicle_id'));
  onProductSelect(document.getElementById('solar_id'));

  // Deposit changes recalculate loan
  if (depositEl) {
    depositEl.addEventListener('input', () => {
      const vSel = document.getElementById('vehicle_id');
      const sSel = document.getElementById('solar_id');
      const sel  = vehicleGroup?.style.display !== 'none' ? vSel : sSel;
      if (!sel) return;
      const opt   = sel.options[sel.selectedIndex];
      const price = parseFloat(opt?.dataset.price || 0);
      const dep   = parseFloat(depositEl.value || 0);
      if (loanAmountEl && price > 0) {
        loanAmountEl.value = Math.max(0, price - dep).toFixed(2);
        updateLoanPreview();
      }
    });
  }

  function updateLoanPreview() {
    const loan   = parseFloat(loanAmountEl?.value || 0);
    const term   = parseInt(document.getElementById('loan_term')?.value || 12);
    const rate   = (window.LOAN_ANNUAL_RATE || 7.0) / 100 / 12;
    const ghs    = window.USD_TO_GHS || 15.5;
    let monthly  = 0;
    if (loan > 0 && term > 0) {
      monthly = (loan * rate * Math.pow(1+rate, term)) / (Math.pow(1+rate, term) - 1);
    }
    const fmt = (usd) => usd.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    const dual = (usd) => `$${fmt(usd)}<br><span style="font-size:.8em;opacity:.65;">GH₵ ${fmt(usd * ghs)}</span>`;

    const previewMonthly = document.getElementById('previewMonthly');
    const previewTotal   = document.getElementById('previewTotal');
    const previewLoan    = document.getElementById('previewLoan');
    const previewTerm    = document.getElementById('previewTerm');
    if (previewMonthly) previewMonthly.innerHTML = monthly > 0 ? dual(monthly)       : '—';
    if (previewTotal)   previewTotal.innerHTML   = monthly > 0 ? dual(monthly * term) : '—';
    if (previewLoan)    previewLoan.innerHTML    = loan > 0    ? dual(loan)            : '—';
    if (previewTerm)    previewTerm.textContent  = term ? `${term} months` : '—';
  }

  document.getElementById('loan_term')?.addEventListener('change', updateLoanPreview);
  document.getElementById('loan_amount')?.addEventListener('input', updateLoanPreview);
  updateLoanPreview();

  // ── Admin: file upload preview ───────────────────────────────
  function setupFilePreview(inputId, previewId, kind) {
    const input   = document.getElementById(inputId);
    const preview = document.getElementById(previewId);
    if (!input || !preview) return;

    input.addEventListener('change', () => {
      const newFiles = Array.from(input.files);
      newFiles.forEach(file => {
        const reader = new FileReader();
        const wrap   = document.createElement('div');
        wrap.className = 'upload-preview-item';

        if (kind === 'image') {
          reader.onload = e => {
            wrap.innerHTML = `<img src="${e.target.result}" alt="preview"><button type="button" class="remove-preview" title="Remove">✕</button>`;
            wrap.querySelector('.remove-preview').addEventListener('click', () => wrap.remove());
            preview.appendChild(wrap);
          };
          reader.readAsDataURL(file);
        } else {
          wrap.innerHTML = `<div class="video-preview-name">🎬 ${file.name}</div><button type="button" class="remove-preview">✕</button>`;
          wrap.querySelector('.remove-preview').addEventListener('click', () => wrap.remove());
          preview.appendChild(wrap);
        }
      });
    });
  }

  setupFilePreview('imageInput', 'imagePreview', 'image');
  setupFilePreview('videoInput', 'videoPreview', 'video');

  // ── Admin: delete existing media ─────────────────────────────
  document.querySelectorAll('.delete-media-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (!confirm('Delete this media?')) return;
      const path = btn.dataset.path;
      const kind = btn.dataset.kind;
      const id   = btn.dataset.id;
      const type = btn.dataset.type; // vehicle | solar
      const url  = `/admin/${type}/${id}/delete-media`;

      try {
        const res = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path, kind })
        });
        if (res.ok) {
          btn.closest('.media-thumb')?.remove();
        }
      } catch (err) {
        alert('Failed to delete media. Please try again.');
      }
    });
  });

  // ── Admin: confirm delete ────────────────────────────────────
  document.querySelectorAll('.confirm-delete').forEach(form => {
    form.addEventListener('submit', e => {
      if (!confirm('Are you sure you want to delete this? This cannot be undone.')) {
        e.preventDefault();
      }
    });
  });

  // ── Counter animation for stats ──────────────────────────────
  const counters = document.querySelectorAll('.stat-number[data-target]');
  const counterObserver = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      const el     = entry.target;
      const target = parseInt(el.dataset.target);
      const suffix = el.dataset.suffix || '';
      const prefix = el.dataset.prefix || '';
      let current  = 0;
      const step   = Math.max(1, Math.floor(target / 60));
      const timer  = setInterval(() => {
        current = Math.min(current + step, target);
        el.textContent = prefix + current.toLocaleString() + suffix;
        if (current >= target) clearInterval(timer);
      }, 20);
      counterObserver.unobserve(el);
    });
  }, { threshold: 0.5 });
  counters.forEach(c => counterObserver.observe(c));

  // ── WhatsApp floating button ─────────────────────────────────
  const waBtn = document.getElementById('whatsappBtn');
  if (waBtn) {
    setTimeout(() => waBtn.classList.add('visible'), 2000);
  }

  // ── Currency toggle (GHS default) ────────────────────────────
  const currBtn = document.getElementById('currencyToggle');
  if (currBtn) {
    const applyPref = (pref) => {
      if (pref === 'usd') {
        document.body.classList.add('show-usd');
        currBtn.textContent = 'GH₵';
        currBtn.title = 'Switch to GHS display';
      } else {
        document.body.classList.remove('show-usd');
        currBtn.textContent = 'USD';
        currBtn.title = 'Switch to USD display';
      }
    };
    const saved = localStorage.getItem('currencyPref') || 'ghs';
    applyPref(saved);
    currBtn.addEventListener('click', () => {
      const next = document.body.classList.contains('show-usd') ? 'ghs' : 'usd';
      localStorage.setItem('currencyPref', next);
      applyPref(next);
    });
  }

});
