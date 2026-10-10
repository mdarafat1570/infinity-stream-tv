(() => {
  'use strict';
  const configElement = document.getElementById('site-config');
  let site;
  try { site = JSON.parse(configElement.textContent); } catch { return; }
  const phone = site.settings.whatsapp_phone;
  let period = 'monthly';
  const urlFor = message => `https://wa.me/${phone}?text=${encodeURIComponent(message)}`;
  const planMessage = (name, selectedPeriod) => `Hello Infinity Stream TV, I would like to know more about the ${name} (${selectedPeriod} billing). Please share the current price, available content, supported devices, connection limits, and activation details.`;
  const messages = {
    trial: 'Hello Infinity Stream TV, is a free trial currently available? Please share eligibility, duration, supported devices, and how I can request one.',
    general: 'Hello Infinity Stream TV, I would like to learn about your available plans, current pricing, supported devices, and content availability.',
    support: 'Hello Infinity Stream TV, I would like some help with my device or subscription. Please let me know what details you need.',
    reseller: 'Hello Infinity Stream TV, I am interested in your reseller program. Please share eligibility, current pricing, account limits, and onboarding details.',
    privacy: 'Hello Infinity Stream TV, I have a question about privacy or information I submitted through the website.',
    refund: 'Hello Infinity Stream TV, I would like to discuss the cancellation or refund terms for my subscription.'
  };
  if (site.settings.trial_enabled && Number(site.settings.trial_hours) > 0) {
    messages.trial = `Hello Infinity Stream TV, I would like to request the ${site.settings.trial_hours}-hour free trial. Please confirm eligibility, limits, supported devices, and setup instructions.`;
  }
  function refreshWhatsAppLinks() {
    document.querySelectorAll('[data-whatsapp]').forEach(link => {
      const kind = link.dataset.whatsapp;
      let message = messages[kind] || messages.general;
      if (kind === 'plan') {
        const plan = site.plans.find(item => item.slug === link.dataset.plan);
        if (plan) message = planMessage(plan.name, period);
      } else if (kind === 'country') {
        message = `Hello Infinity Stream TV, please confirm available content, plans, pricing, and device support in ${link.dataset.country}.`;
      } else if (kind === 'device') {
        message = `Hello Infinity Stream TV, I would like to check compatibility and setup instructions for ${link.dataset.device}. Please let me know which model or app details you need.`;
      } else if (kind === 'content-row') {
        message = `Hello Infinity Stream TV, I would like to ask about ${link.dataset.contentLabel} ${link.dataset.contentType}. Please share current availability, pricing and device setup.`;
      }
      link.href = urlFor(message);
    });
  }
  refreshWhatsAppLinks();
  const menuToggle = document.querySelector('.menu-toggle');
  const mobileNav = document.getElementById('mobile-nav');
  function closeMenu() {
    if (!menuToggle || !mobileNav) return;
    menuToggle.setAttribute('aria-expanded', 'false');
    menuToggle.setAttribute('aria-label', 'Open navigation');
    mobileNav.hidden = true;
  }
  menuToggle?.addEventListener('click', () => {
    const opened = menuToggle.getAttribute('aria-expanded') !== 'true';
    menuToggle.setAttribute('aria-expanded', String(opened));
    menuToggle.setAttribute('aria-label', opened ? 'Close navigation' : 'Open navigation');
    mobileNav.hidden = !opened;
  });
  mobileNav?.addEventListener('click', event => { if (event.target.closest('a')) closeMenu(); });
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && menuToggle?.getAttribute('aria-expanded') === 'true') { closeMenu(); menuToggle.focus(); } });
  document.addEventListener('click', event => { if (!event.target.closest('.site-header')) closeMenu(); });
  window.matchMedia('(min-width: 971px)').addEventListener('change', event => { if (event.matches) closeMenu(); });
  function selectPeriod(selected) {
    if (!site.billing_periods.some(item => item.slug === selected)) return;
    period = selected;
    document.querySelectorAll('[data-period]').forEach(button => {
      const active = button.dataset.period === period;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    document.querySelectorAll('[data-price]').forEach(container => {
      const plan = site.plans.find(item => item.slug === container.dataset.price);
      const details = plan?.periods?.[period];
      if (!details) return;
      const title = container.querySelector('strong');
      const label = container.querySelector('span');
      if (details.price != null) {
        let amount;
        try { amount = new Intl.NumberFormat('en', { style: 'currency', currency: details.currency }).format(details.price); }
        catch { amount = `${details.currency} ${details.price}`; }
        title.textContent = amount;
        label.textContent = details.label;
      } else {
        title.textContent = 'Let’s find your plan';
        label.textContent = `Ask about ${period} pricing`;
      }
    });
    refreshWhatsAppLinks();
  }
  document.querySelectorAll('[data-period]').forEach(button => button.addEventListener('click', () => selectPeriod(button.dataset.period)));
  const query = new URLSearchParams(window.location.search);
  if (query.has('period')) selectPeriod(query.get('period'));
  function filterCategory(slug, updateUrl = false) {
    if (slug !== 'all' && !site.categories.some(category => category.slug === slug)) slug = 'all';
    document.querySelectorAll('[data-category-filter]').forEach(button => {
      const active = button.dataset.categoryFilter === slug;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    document.querySelectorAll('[data-category]').forEach(card => { card.hidden = slug !== 'all' && card.dataset.category !== slug; });
    if (updateUrl) {
      const next = new URL(window.location.href);
      if (slug === 'all') next.searchParams.delete('category'); else next.searchParams.set('category', slug);
      window.history.replaceState(null, '', next);
    }
  }
  if (document.body.dataset.page === 'channels') {
    filterCategory(query.get('category') || 'all');
    document.querySelectorAll('[data-category-filter]').forEach(button => button.addEventListener('click', () => filterCategory(button.dataset.categoryFilter, true)));
  }
  const form = document.querySelector('[data-enquiry-form]');
  if (form) {
    const country = query.get('country');
    if (country && country.length <= 80 && !form.elements.country.value) form.elements.country.value = country;
    const selectedPlan = query.get('plan');
    if (selectedPlan && site.plans.some(plan => plan.slug === selectedPlan) && form.elements.source_page.value !== 'reseller') form.elements.plan.value = selectedPlan;
    const contactInput = form.elements.contact;
    const contactMethod = form.elements.contact_method;
    const updateContact = () => {
      contactInput.type = contactMethod.value === 'email' ? 'email' : 'tel';
      contactInput.autocomplete = contactMethod.value === 'email' ? 'email' : 'tel';
      contactInput.placeholder = contactMethod.value === 'email' ? 'you@example.com' : '+880 1…';
    };
    updateContact();
    contactMethod.addEventListener('change', updateContact);
    form.addEventListener('submit', event => {
      if (document.body.dataset.static !== 'true') return;
      event.preventDefault();
      if (!form.reportValidity()) return;
      const feedback = form.querySelector('.form-feedback');
      if (form.elements.website.value) { feedback.textContent = 'Please try again without the website field.'; return; }
      const values = Object.fromEntries(new FormData(form));
      const normalizedPhone = values.contact.trim().replace(/[\s().-]/g, '');
      const contactValid = values.contact_method === 'email' ? /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.contact.trim()) : /^\+?[1-9][0-9]{6,14}$/.test(normalizedPhone);
      const textValid = [values.name, values.country].every(value => value.trim().length >= 2);
      if (!contactValid || !textValid || values.message.trim().length < 10) {
        feedback.textContent = !contactValid ? 'Please enter a valid phone number with country code, or select Email and enter an email address.' : 'Please complete your name, country, and a message of at least 10 characters.';
        if (!contactValid) contactInput.focus(); else form.elements.message.focus();
        return;
      }
      const plan = site.plans.find(item => item.slug === values.plan);
      const message = `Hello Infinity Stream TV,\nName: ${values.name.trim()}\nCountry: ${values.country.trim()}\nPreferred contact: ${values.contact_method}\nContact: ${values.contact.trim()}\nEnquiry: ${plan?.name || values.plan || 'General'}\n\n${values.message.trim()}`;
      const url = urlFor(message);
      window.open(url, '_blank', 'noopener,noreferrer');
      feedback.replaceChildren(document.createTextNode('Your WhatsApp draft is ready. Review and send it there. '));
      const review = document.createElement('a');
      review.href = url; review.target = '_blank'; review.rel = 'noopener noreferrer'; review.textContent = 'Open the draft';
      feedback.append(review);
    });
  }

  // Sitewide scroll-reveal: a lightweight, generic IntersectionObserver that
  // fades/raises a broad set of repeating blocks into view once, the first
  // time each scrolls into the viewport. Progressive enhancement: the
  // `.js-reveal-ready` hook class is only added here, so the page never
  // relies on JS running to show its content (see the matching CSS).
  document.documentElement.classList.add('js-reveal-ready');
  const revealSelectors = [
    '.section', '.page-intro', '.step-card', '.category-card', '.plan-card',
    '.device-card', '.country-card', '.why-item', '.info-panel', '.contact-card',
  ];
  const revealTargets = document.querySelectorAll(revealSelectors.join(','));
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (revealTargets.length) {
    if (prefersReducedMotion || !('IntersectionObserver' in window)) {
      revealTargets.forEach(el => el.classList.add('is-visible'));
    } else {
      const revealObserver = new IntersectionObserver(entries => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
            revealObserver.unobserve(entry.target);
          }
        });
      }, { threshold: 0.15 });
      revealTargets.forEach(el => revealObserver.observe(el));
    }
  }

  // Netflix-style content rows: horizontally scrollable tracks with
  // Prev/Next arrow buttons. The track itself is natively scrollable and
  // keyboard-focusable (tabindex + overflow-x), so arrow buttons are a
  // pointer-friendly enhancement rather than the only way to scroll.
  // RTL-safe: the scroll direction is read from the page's own `dir`
  // attribute rather than assumed, the same way the hero banner mirrors its
  // Prev/Next buttons in CSS instead of hardcoding a direction in JS.
  document.querySelectorAll('[data-content-row]').forEach(row => {
    const track = row.querySelector('[data-row-track]');
    const prevBtn = row.querySelector('[data-row-prev]');
    const nextBtn = row.querySelector('[data-row-next]');
    if (!track) return;
    const isRtl = getComputedStyle(row).direction === 'rtl';

    function maxScroll() {
      return track.scrollWidth - track.clientWidth;
    }
    function currentScroll() {
      // Normalize to an always-positive "distance scrolled from the start",
      // regardless of the browser/direction scrollLeft sign convention.
      return isRtl ? -track.scrollLeft : track.scrollLeft;
    }
    function updateArrows() {
      const scrollable = maxScroll() > 1;
      const atStart = currentScroll() <= 1;
      const atEnd = currentScroll() >= maxScroll() - 1;
      row.classList.toggle('content-row-fits', !scrollable);
      if (prevBtn) {
        prevBtn.hidden = !scrollable;
        prevBtn.disabled = !scrollable || atStart;
      }
      if (nextBtn) {
        nextBtn.hidden = !scrollable;
        nextBtn.disabled = !scrollable || atEnd;
      }
    }
    function scrollByCards(direction) {
      // direction: 1 for "next" (forward in reading order), -1 for "prev".
      const card = track.querySelector('[data-row-card]');
      const step = card ? card.getBoundingClientRect().width + 16 : track.clientWidth * 0.8;
      const signedStep = isRtl ? -step * direction : step * direction;
      track.scrollBy({ left: signedStep, behavior: 'smooth' });
    }
    prevBtn?.addEventListener('click', () => scrollByCards(-1));
    nextBtn?.addEventListener('click', () => scrollByCards(1));
    track.addEventListener('keydown', event => {
      if (event.key === 'ArrowRight') { scrollByCards(isRtl ? -1 : 1); event.preventDefault(); }
      else if (event.key === 'ArrowLeft') { scrollByCards(isRtl ? 1 : -1); event.preventDefault(); }
    });
    track.addEventListener('scroll', updateArrows, { passive: true });
    window.addEventListener('resize', updateArrows);
    updateArrows();
  });
})();
