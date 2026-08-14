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

  if (toggle && mobileNav) {
    var setNav = function (open) {
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
      booking.scrollIntoView({
        behavior: reduceMotion ? "auto" : "smooth",
        block: "start"
      });
      history.replaceState(null, "", "#book");
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
        "hide_gdpr_banner=1&background_color=00052e&text_color=ffffff&primary_color=0428cb");

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
