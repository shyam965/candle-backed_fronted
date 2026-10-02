/* AK Royal Flames — progressive enhancement on top of HTMX. No inline scripts (CSP: script-src 'self'). */
(function () {
  "use strict";

  var TOAST_CLASSES = {
    success: "bg-emerald-700 text-white",
    error: "bg-red-700 text-white",
    info: "bg-royal-800 text-white",
  };

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function csrfToken() { var m = $('meta[name="csrf-token"]'); return m ? m.content : ""; }

  /* ---------- Toasts (FR-UI-003: top-centre, 3 s) ---------- */
  function showToast(item) {
    var region = document.getElementById("toasts");
    if (!region || !item || !item.message) return;
    var duration = parseInt(region.getAttribute("data-duration") || "3000", 10);
    var type = TOAST_CLASSES[item.type] ? item.type : "success";
    var el = document.createElement("div");
    el.className = "pointer-events-auto w-full max-w-sm rounded-xl px-4 py-3 text-sm font-medium shadow-[var(--shadow-lift)] animate-toast-in " + TOAST_CLASSES[type];
    el.setAttribute("role", type === "error" ? "alert" : "status");
    el.textContent = item.message;
    region.appendChild(el);
    setTimeout(function () {
      el.style.transition = "opacity 200ms";
      el.style.opacity = "0";
      setTimeout(function () { el.remove(); }, 220);
    }, duration);
  }
  window.akrfToast = showToast;

  function initFlash() {
    var data = document.getElementById("flash-data");
    if (!data) return;
    try { JSON.parse(data.textContent || "[]").forEach(showToast); } catch (e) { /* ignore malformed */ }
  }

  /* ---------- HTMX wiring ---------- */
  document.addEventListener("htmx:configRequest", function (evt) {
    evt.detail.headers["X-CSRF-Token"] = csrfToken();
  });

  document.addEventListener("toast", function (evt) {
    var detail = evt.detail || {};
    (detail.items || [detail]).forEach(showToast);
  });

  document.addEventListener("openWhatsApp", function (evt) {
    var url = evt.detail && evt.detail.url;
    if (url && /^https:\/\/(wa\.me|api\.whatsapp\.com)\//.test(url)) {
      window.open(url, "_blank", "noopener,noreferrer");
    }
  });

  document.addEventListener("redirectAfter", function (evt) {
    var d = evt.detail || {};
    if (typeof d.url === "string" && d.url.charAt(0) === "/" && d.url.charAt(1) !== "/") {
      setTimeout(function () { window.location.assign(d.url); }, d.delay || 0);
    }
  });

  /* Admin order status: confirm irreversible moves, restore the select on cancel or error (D-30, K-17). */
  var CONFIRM_STATUSES = { Cancelled: "cancel this order", Delivered: "mark this order as delivered" };
  document.addEventListener("htmx:confirm", function (evt) {
    var select = evt.detail.elt;
    if (!select || !select.matches || !select.matches("[data-status-select]")) return;
    var action = CONFIRM_STATUSES[select.value];
    if (!action) return;
    evt.preventDefault();
    if (window.confirm("Are you sure you want to " + action + "? This cannot be undone.")) {
      evt.detail.issueRequest(true);
    } else {
      select.value = select.getAttribute("data-current");
    }
  });
  document.addEventListener("htmx:responseError", function (evt) {
    var select = evt.detail.elt;
    if (select && select.matches && select.matches("[data-status-select]")) select.value = select.getAttribute("data-current");
  });

  var inflight = 0;
  function progress(on) {
    var bar = document.getElementById("progress-bar");
    if (!bar) return;
    inflight = Math.max(0, inflight + (on ? 1 : -1));
    bar.classList.toggle("is-active", inflight > 0);
  }
  document.addEventListener("htmx:beforeRequest", function () { progress(true); });
  document.addEventListener("htmx:afterRequest", function () { progress(false); });

  document.addEventListener("htmx:sendError", function () {
    showToast({ type: "error", message: "Network error. Please check your connection and try again." });
  });

  document.addEventListener("htmx:afterSwap", function (evt) {
    var target = evt.detail.target;
    if (target && target.id === "modal" && typeof target.showModal === "function") {
      if (!target.open) target.showModal();
      var focusable = target.querySelector("[autofocus], button, a, select, input");
      if (focusable) focusable.focus();
    }
    var invalid = target && target.querySelector('[aria-invalid="true"]');
    if (invalid) {
      invalid.scrollIntoView({ behavior: "smooth", block: "center" });
      invalid.focus({ preventScroll: true });
    }
    init(target);
  });

  /* ---------- Toggles: menus, search bar, sidebar ---------- */
  function setOpen(trigger, target, open) {
    var cls = target.getAttribute("data-toggle-class");
    if (cls) { target.classList.toggle(cls, !open); } else { target.hidden = !open; }
    $$('[data-toggle="#' + target.id + '"]').forEach(function (t) { t.setAttribute("aria-expanded", open ? "true" : "false"); });
    $$('[data-overlay-for="#' + target.id + '"]').forEach(function (overlay) { overlay.hidden = !open; });
    if (open) {
      var field = target.querySelector("input[type=search], input");
      if (field && !cls) field.focus();
    }
  }
  function isOpen(target) {
    var cls = target.getAttribute("data-toggle-class");
    return cls ? !target.classList.contains(cls) : !target.hidden;
  }
  document.addEventListener("click", function (evt) {
    var trigger = evt.target.closest("[data-toggle]");
    if (trigger) {
      var target = $(trigger.getAttribute("data-toggle"));
      if (target) setOpen(trigger, target, !isOpen(target));
      return;
    }
    var closer = evt.target.closest("[data-close]");
    if (closer) {
      var t = $(closer.getAttribute("data-close"));
      if (t) setOpen(null, t, false);
    }
    var dismiss = evt.target.closest("[data-dismiss]");
    if (dismiss) {
      var box = $(dismiss.getAttribute("data-dismiss"));
      if (box) box.innerHTML = "";
      return;
    }
    var back = evt.target.closest("[data-back]");
    if (back && window.history.length > 1 && document.referrer.indexOf(window.location.origin) === 0) {
      evt.preventDefault();
      window.history.back();
      return;
    }
    var modalClose = evt.target.closest("[data-modal-close]");
    if (modalClose) {
      var dlg = modalClose.closest("dialog");
      if (dlg) dlg.close();
    }
  });
  document.addEventListener("keydown", function (evt) {
    if (evt.key !== "Escape") return;
    $$("[data-toggle]").forEach(function (trigger) {
      var target = $(trigger.getAttribute("data-toggle"));
      if (target && isOpen(target) && trigger.getAttribute("aria-expanded") === "true") {
        setOpen(trigger, target, false);
        trigger.focus();
      }
    });
  });
  document.addEventListener("close", function (evt) {
    if (evt.target && evt.target.id === "modal") evt.target.innerHTML = "";
  }, true);

  /* ---------- Broken images fall back to a placeholder ---------- */
  document.addEventListener("error", function (evt) {
    var img = evt.target;
    if (img && img.tagName === "IMG" && img.hasAttribute("data-fallback")) {
      img.removeAttribute("data-fallback");
      var ph = document.createElement("div");
      ph.className = "flex h-full w-full items-center justify-center bg-gradient-to-br from-flame-50 to-royal-50 text-flame-600";
      ph.setAttribute("role", "img");
      ph.setAttribute("aria-label", img.alt || "Image unavailable");
      ph.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="h-8 w-8" aria-hidden="true"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.07-2.14-.22-4.05 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.15.43-2.29 1-3a2.5 2.5 0 0 0 2.5 2.5z"/></svg>';
      img.replaceWith(ph);
    }
  }, true);

  /* ---------- Inline errors clear when the field is edited (FR-UI-016) ---------- */
  document.addEventListener("input", function (evt) {
    var field = evt.target;
    var errId = field.getAttribute && field.getAttribute("data-clear-error");
    if (errId) {
      var err = document.getElementById(errId);
      if (err && !err.hasAttribute("data-live")) { err.hidden = true; err.textContent = ""; }
      field.classList.remove("input-error");
      field.removeAttribute("aria-invalid");
    }
    var form = field.form;
    var alertSel = form && form.getAttribute("data-clear-on-input");
    if (alertSel) { var box = $(alertSel, form); if (box) box.remove(); }
    var digits = field.getAttribute && field.getAttribute("data-digits");
    if (digits) {
      var cleaned = field.value.replace(/\D/g, "").slice(0, parseInt(digits, 10));
      if (cleaned !== field.value) field.value = cleaned;
    }
  });

  /* ---------- Image inputs: preview + client-side type/size checks (FR-UI-104) ---------- */
  var IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];
  document.addEventListener("change", function (evt) {
    var input = evt.target;
    if (!input.matches || !input.matches('input[type="file"][data-preview]')) return;
    var errorEl = $(input.getAttribute("data-error"));
    var preview = $(input.getAttribute("data-preview"));
    var placeholder = $(input.getAttribute("data-placeholder"));
    var file = input.files && input.files[0];
    function fail(message) {
      input.value = "";
      if (errorEl) { errorEl.textContent = message; errorEl.hidden = false; }
      input.setAttribute("aria-invalid", "true");
    }
    if (errorEl) { errorEl.hidden = true; errorEl.textContent = ""; }
    input.removeAttribute("aria-invalid");
    if (!file) return;
    if (IMAGE_TYPES.indexOf(file.type) === -1) { fail("Only JPG, PNG and WebP images are allowed"); return; }
    var max = parseInt(input.getAttribute("data-max-bytes") || "0", 10);
    if (max && file.size > max) { fail("Image must be under " + input.getAttribute("data-max-label") + " MB"); return; }
    if (preview) {
      preview.src = URL.createObjectURL(file);
      preview.hidden = false;
      if (placeholder) placeholder.hidden = true;
    }
  });

  /* ---------- Live password checks on registration (FR-UI-017) ---------- */
  function liveRegister(form) {
    var pw = form.querySelector('[name="password"]');
    var cf = form.querySelector('[name="confirm_password"]');
    var pwErr = document.getElementById("f-password-error");
    var cfErr = document.getElementById("f-confirm_password-error");
    function check() {
      if (pw && pwErr) {
        var short = pw.value.length > 0 && pw.value.length < 6;
        pwErr.textContent = short ? "Password must be at least 6 characters" : "";
        pwErr.hidden = !short;
      }
      if (pw && cf && cfErr) {
        var mismatch = cf.value.length > 0 && cf.value !== pw.value;
        cfErr.textContent = mismatch ? "Passwords do not match" : "";
        cfErr.hidden = !mismatch;
      }
    }
    if (pwErr) pwErr.setAttribute("data-live", "");
    if (cfErr) cfErr.setAttribute("data-live", "");
    form.addEventListener("input", check);
  }

  /* ---------- Quantity steppers (FR-UI-044) ---------- */
  function stepper(root) {
    var input = root.querySelector("input[type=number]");
    var dec = root.querySelector('[data-step="-1"]');
    var inc = root.querySelector('[data-step="1"]');
    if (!input) return;
    function sync() {
      var min = parseInt(input.min || "1", 10), max = parseInt(input.max || "1", 10);
      var v = parseInt(input.value || String(min), 10);
      if (isNaN(v)) v = min;
      v = Math.min(Math.max(v, min), max);
      input.value = String(v);
      if (dec) dec.disabled = v <= min;
      if (inc) inc.disabled = v >= max;
    }
    root.addEventListener("click", function (evt) {
      var b = evt.target.closest("[data-step]");
      if (!b) return;
      input.value = String(parseInt(input.value || "1", 10) + parseInt(b.getAttribute("data-step"), 10));
      sync();
    });
    input.addEventListener("change", sync);
    sync();
  }

  /* ---------- Banner slider (FR-UI-031) ---------- */
  function slider(root) {
    var slides = $$("[data-slide]", root);
    var dots = $$("[data-slider-dot]", root);
    if (!slides.length) return;
    var index = 0, timer = null;
    var interval = parseInt(root.getAttribute("data-interval") || "4000", 10);
    function show(i) {
      index = (i + slides.length) % slides.length;
      slides.forEach(function (s, n) {
        var active = n === index;
        s.classList.toggle("opacity-100", active);
        s.classList.toggle("opacity-0", !active);
        s.classList.toggle("pointer-events-none", !active);
        s.setAttribute("aria-hidden", active ? "false" : "true");
        $$("a, button", s).forEach(function (el) { el.tabIndex = active ? 0 : -1; });
      });
      dots.forEach(function (d, n) {
        d.setAttribute("aria-current", n === index ? "true" : "false");
        d.classList.toggle("bg-white", n === index);
        d.classList.toggle("bg-white/50", n !== index);
      });
    }
    function start() { if (slides.length > 1 && !timer) timer = setInterval(function () { show(index + 1); }, interval); }
    function stop() { if (timer) { clearInterval(timer); timer = null; } }
    root.addEventListener("click", function (evt) {
      if (slides.length < 2) return;
      if (evt.target.closest("[data-slider-prev]")) { stop(); show(index - 1); start(); }
      else if (evt.target.closest("[data-slider-next]")) { stop(); show(index + 1); start(); }
      else {
        var dot = evt.target.closest("[data-slider-dot]");
        if (dot) { stop(); show(parseInt(dot.getAttribute("data-slider-dot"), 10)); start(); }
      }
    });
    root.addEventListener("mouseenter", stop);
    root.addEventListener("mouseleave", start);
    root.addEventListener("focusin", stop);
    root.addEventListener("focusout", start);
    show(0);
    start();
  }

  /* ---------- Wishlist (FR-UI-056, D-43: per-browser localStorage) ---------- */
  var WISHLIST_KEY = "akrf_wishlist";
  function readWishlist() {
    try { var v = JSON.parse(localStorage.getItem(WISHLIST_KEY) || "[]"); return Array.isArray(v) ? v : []; }
    catch (e) { return []; }
  }
  function writeWishlist(list) { try { localStorage.setItem(WISHLIST_KEY, JSON.stringify(list.slice(-200))); } catch (e) { /* storage unavailable */ } }
  function paintWishlist(btn, on) {
    btn.setAttribute("aria-pressed", on ? "true" : "false");
    btn.setAttribute("aria-label", on ? "Remove from wishlist" : "Add to wishlist");
    btn.classList.toggle("text-red-600", on);
    btn.classList.toggle("text-royal-500", !on);
    var svg = btn.querySelector("svg");
    if (svg) svg.setAttribute("fill", on ? "currentColor" : "none");
  }
  document.addEventListener("click", function (evt) {
    var btn = evt.target.closest("[data-wishlist]");
    if (!btn) return;
    var id = btn.getAttribute("data-wishlist");
    var list = readWishlist();
    var on = list.indexOf(id) === -1;
    list = on ? list.concat([id]) : list.filter(function (x) { return x !== id; });
    writeWishlist(list);
    paintWishlist(btn, on);
  });

  /* ---------- Init on load and after each swap ---------- */
  function init(root) {
    root = root || document;
    $$("[data-stepper]", root).forEach(function (el) { if (!el.__akrf) { el.__akrf = 1; stepper(el); } });
    $$("[data-slider]", root).forEach(function (el) { if (!el.__akrf) { el.__akrf = 1; slider(el); } });
    $$("form[data-live-register]", root).forEach(function (el) { if (!el.__akrf) { el.__akrf = 1; liveRegister(el); } });
    var wl = readWishlist();
    $$("[data-wishlist]", root).forEach(function (btn) { paintWishlist(btn, wl.indexOf(btn.getAttribute("data-wishlist")) !== -1); });
    if (root.matches && root.matches("[data-stepper]") && !root.__akrf) { root.__akrf = 1; stepper(root); }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { initFlash(); init(document); });
  } else {
    initFlash();
    init(document);
  }
})();
