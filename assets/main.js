/* =============================================================================
   SYSTEMERGE — landing page behavior
   ========================================================================== */

(function () {
  "use strict";

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------------------------------------------------------------- month --
     Fills "A few client spots open for <month>" with the current month so the
     scarcity line never goes stale. Replace with static text to pin a month.
  -------------------------------------------------------------------------- */
  var monthSlots = document.querySelectorAll("[data-current-month]");
  if (monthSlots.length) {
    var month = new Date().toLocaleString("en-US", { month: "long" });
    monthSlots.forEach(function (el) { el.textContent = month; });
  }

  var yearSlots = document.querySelectorAll("[data-current-year]");
  yearSlots.forEach(function (el) {
    el.textContent = String(Math.max(2026, new Date().getFullYear()));
  });

  /* --------------------------------------------------------------- header --
     Adds a hairline border once the page has scrolled off the top.
  -------------------------------------------------------------------------- */
  var header = document.querySelector(".site-header");
  var onScroll = function () {
    header.classList.toggle("is-stuck", window.scrollY > 8);
  };
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  /* ----------------------------------------------------------- mobile nav -- */
  var toggle = document.querySelector(".nav-toggle");
  var mobileNav = document.getElementById("mobile-nav");
  var setNav = function () {};

  if (toggle && mobileNav) {
    setNav = function (open) {
      toggle.setAttribute("aria-expanded", String(open));
      toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
      mobileNav.hidden = !open;
    };

    toggle.addEventListener("click", function () {
      setNav(toggle.getAttribute("aria-expanded") !== "true");
    });

    mobileNav.addEventListener("click", function (e) {
      if (e.target.closest("a")) setNav(false);
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && toggle.getAttribute("aria-expanded") === "true") {
        setNav(false);
        toggle.focus();
      }
    });
  }

  /* ------------------------------------------------------------ book CTAs --
     Every "Book the strategy call" button scrolls to the booking section.
     The href="#book" already works without JS; this just guarantees a smooth
     scroll and keeps focus somewhere sensible for keyboard users.
  -------------------------------------------------------------------------- */
  var booking = document.getElementById("book");

  document.querySelectorAll("[data-book]").forEach(function (btn) {
    btn.addEventListener("click", function (e) {
      if (!booking) return;
      e.preventDefault();

      // Collapse the mobile menu BEFORE measuring the scroll target. Closing it
      // afterwards removes ~230px of layout above the target and lands the
      // scroll well past the section.
      var wasOpen = mobileNav && !mobileNav.hidden;
      if (wasOpen) setNav(false);

      var go = function () {
        booking.scrollIntoView({
          behavior: reduceMotion ? "auto" : "smooth",
          block: "start"
        });
        history.replaceState(null, "", "#book");
      };
      if (wasOpen) requestAnimationFrame(go); else go();
    });
  });

  /* ------------------------------------------------------------------ VSL --
     Swaps the placeholder for the real embed on click, so no third-party
     player loads (or tracks) until the visitor actually asks for the video.
  -------------------------------------------------------------------------- */
  var vsl = document.querySelector("[data-vsl]");

  if (vsl) {
    var playBtn = vsl.querySelector("[data-vsl-play]");
    var src = (vsl.getAttribute("data-vsl-src") || "").trim();

    if (playBtn) {
      playBtn.addEventListener("click", function () {
        if (!src) return; // No embed configured yet — leave the placeholder up.

        var frame = document.createElement("iframe");
        frame.src = src + (src.indexOf("?") === -1 ? "?" : "&") + "autoplay=1";
        frame.title = "SYSTEMERGE — how it works";
        frame.allow = "accelerometer; autoplay; clipboard-write; encrypted-media; picture-in-picture";
        frame.allowFullscreen = true;

        vsl.replaceChildren(frame);
      });
    }
  }

  /* ------------------------------------------------------------- Calendly --
     Loads the Calendly widget only when a URL is configured and the booking
     section is close to the viewport, keeping the initial page load light.
  -------------------------------------------------------------------------- */
  var calendly = document.querySelector("[data-calendly]");
  var calendlyUrl = calendly ? (calendly.getAttribute("data-calendly-url") || "").trim() : "";

  if (calendly && calendlyUrl) {
    var mountCalendly = function () {
      var css = document.createElement("link");
      css.rel = "stylesheet";
      css.href = "https://assets.calendly.com/assets/external/widget.css";
      document.head.appendChild(css);

      var holder = document.createElement("div");
      holder.className = "calendly-inline-widget";
      holder.style.minWidth = "320px";
      holder.style.height = "700px";
      holder.setAttribute("data-url", calendlyUrl + (calendlyUrl.indexOf("?") === -1 ? "?" : "&") +
        "hide_gdpr_banner=1&background_color=0b0b0b&text_color=f5f5f5&primary_color=a881fe");

      calendly.replaceChildren(holder);
      calendly.classList.add("is-live");

      var script = document.createElement("script");
      script.src = "https://assets.calendly.com/assets/external/widget.js";
      script.async = true;
      document.body.appendChild(script);
    };

    if ("IntersectionObserver" in window) {
      var calObserver = new IntersectionObserver(function (entries) {
        if (entries[0].isIntersecting) {
          calObserver.disconnect();
          mountCalendly();
        }
      }, { rootMargin: "400px" });
      calObserver.observe(calendly);
    } else {
      mountCalendly();
    }
  }

  /* ---------------------------------------------------------- ROI calculator --
     Pure arithmetic on the visitor's own inputs. Nothing is transmitted, and
     no figure here represents a SYSTEMERGE price.
  -------------------------------------------------------------------------- */
  var roi = document.getElementById("roi");

  /* ------------------------------------------------- external calculator --
     When an embed URL is configured, frame it and hide the built-in
     calculator so only one is ever on the page. The iframe is sandboxed and
     its height is driven by postMessage from the embedded app, with the
     origin checked before any message is trusted.
  -------------------------------------------------------------------------- */
  var embed = document.querySelector("[data-roi-embed]");
  var embedUrl = embed ? (embed.getAttribute("data-roi-embed-url") || "").trim() : "";

  if (embed && embedUrl) {
    var builtIn = document.querySelector("[data-roi-builtin]");
    if (builtIn) builtIn.hidden = true;
    embed.setAttribute("data-active", "");

    var frameWrap = embed.querySelector("[data-roi-frame]");
    var link = embed.querySelector("[data-roi-embed-link]");
    if (link) link.href = embedUrl;

    var frame = document.createElement("iframe");
    frame.src = embedUrl;
    frame.title = "ROI calculator";
    frame.loading = "lazy";
    frame.setAttribute("sandbox", "allow-scripts allow-same-origin allow-forms");
    frameWrap.appendChild(frame);

    var embedOrigin = "";
    try { embedOrigin = new URL(embedUrl).origin; } catch (e) {}

    window.addEventListener("message", function (e) {
      if (!embedOrigin || e.origin !== embedOrigin) return;
      var d = e.data, h = 0;
      if (typeof d === "number") h = d;
      else if (d && typeof d === "object") h = d.height || d.frameHeight || d.scrollHeight || 0;
      if (h > 400 && h < 8000) {
        var cur = parseInt(frameWrap.style.height, 10) || 0;
        if (Math.abs(h - cur) > 2) frameWrap.style.height = h + "px";
      }
    });
  }

  if (roi && !(embed && embedUrl)) {
    var money = new Intl.NumberFormat(undefined, {
      style: "currency", currency: "USD", maximumFractionDigits: 0
    });

    var num = function (id) { return document.getElementById(id); };
    var fields = {
      calls: num("roi-calls"), callsRange: num("roi-calls-range"),
      close: num("roi-close"), closeRange: num("roi-close-range"),
      value: num("roi-value"), cost: num("roi-cost")
    };
    var out = {
      clients:   roi.querySelector("[data-roi-clients]"),
      revenue:   roi.querySelector("[data-roi-revenue]"),
      spend:     roi.querySelector("[data-roi-spend]"),
      net:       roi.querySelector("[data-roi-net]"),
      multiple:  roi.querySelector("[data-roi-multiple]"),
      breakeven: roi.querySelector("[data-roi-breakeven]"),
      state:     roi.querySelector("[data-roi-state]")
    };

    // Clamp to the input's own min/max so typed values can't produce nonsense.
    var read = function (el, fallback) {
      var v = parseFloat(el.value);
      if (!isFinite(v)) return fallback;
      var min = parseFloat(el.min), max = parseFloat(el.max);
      if (isFinite(min) && v < min) v = min;
      if (isFinite(max) && v > max) v = max;
      return v;
    };

    var recalc = function () {
      var calls = read(fields.calls, 20);
      var close = read(fields.close, 20) / 100;
      var value = read(fields.value, 10000);
      var cost  = read(fields.cost, 300);

      var clients = calls * close;
      var revenue = clients * value;
      var spend   = calls * cost;
      var net     = revenue - spend;

      // Whole numbers read as "4", fractions keep one decimal ("4.5").
      out.clients.textContent = Number.isInteger(clients)
        ? String(clients)
        : (clients < 10 ? clients.toFixed(1) : String(Math.round(clients)));
      out.revenue.textContent = money.format(revenue);
      out.spend.textContent   = money.format(spend);
      out.net.textContent     = money.format(net);

      if (spend > 0) {
        var mult = revenue / spend;
        out.multiple.textContent = mult.toFixed(1) + "×";
        out.state.setAttribute("data-state", mult >= 1 ? "gain" : "loss");
      } else {
        out.multiple.textContent = "—";
        out.state.setAttribute("data-state", "gain");
      }

      // The close rate at which revenue exactly covers spend.
      if (value > 0) {
        var be = (cost / value) * 100;
        out.breakeven.textContent = be <= 100
          ? "Breaks even at a " + (be < 1 ? be.toFixed(2) : be.toFixed(1)) + "% close rate."
          : "A client is worth less than a call costs at these numbers.";
      } else {
        out.breakeven.textContent = "Enter what a client is worth to see the break-even point.";
      }
    };

    // Keep each slider and its number box in step, then recalculate.
    var pair = function (a, b) {
      if (!a || !b) return;
      a.addEventListener("input", function () { b.value = a.value; recalc(); });
      b.addEventListener("input", function () { a.value = b.value; recalc(); });
    };
    pair(fields.callsRange, fields.calls);
    pair(fields.closeRange, fields.close);

    [fields.value, fields.cost].forEach(function (el) {
      if (el) el.addEventListener("input", recalc);
    });
    // Re-clamp once the field loses focus, so a typed 900 settles to the max.
    Object.keys(fields).forEach(function (k) {
      if (fields[k]) fields[k].addEventListener("change", function () {
        fields[k].value = read(fields[k], fields[k].value);
        recalc();
      });
    });

    recalc();
  }

  /* ---------------------------------------------------------- reveal-on-scroll */
  var revealables = document.querySelectorAll(".reveal");

  if (reduceMotion || !("IntersectionObserver" in window)) {
    revealables.forEach(function (el) { el.classList.add("is-visible"); });
  } else {
    var revealObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          revealObserver.unobserve(entry.target);
        }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });

    revealables.forEach(function (el) { revealObserver.observe(el); });
  }
})();
