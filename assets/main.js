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
     Two modes — a 60-day pilot and an ongoing retainer — driven entirely by
     sliders. Pure arithmetic on the visitor's own inputs. Nothing is
     transmitted, and no figure here represents a SYSTEMERGE price.

     The funnel rounds at each stage, matching how these projections are
     normally read: whole replies produce whole leads produce whole calls.
  -------------------------------------------------------------------------- */
  var roi = document.getElementById("roi");

  if (roi) {
    var WEEKDAYS = { pilot: 42, retainer: 21 };
    var mode = "pilot";

    var money = new Intl.NumberFormat("en-US", {
      style: "currency", currency: "USD", maximumFractionDigits: 0
    });
    var num = new Intl.NumberFormat("en-US");
    var $ = function (s) { return roi.querySelector(s); };
    var id = function (s) { return document.getElementById(s); };

    var f = {
      daily: id("roi-daily"), steps: id("roi-steps"), reply: id("roi-reply"),
      positive: id("roi-positive"), book: id("roi-book"), show: id("roi-show"),
      close: id("roi-close"), deal: id("roi-deal"), retention: id("roi-retention"),
      cost: id("roi-cost")
    };
    var vars = [].slice.call(roi.querySelectorAll("[data-var]"));
    var out = function (k) { return roi.querySelector('[data-out="' + k + '"]'); };
    var val = function (el) { return parseFloat(el.value); };

    function recalc() {
      var days = WEEKDAYS[mode];
      var daily = val(f.daily), steps = val(f.steps);
      var emails = daily * days;
      var people = Math.round(emails / steps);

      // Offer variables lift the base positive rate proportionally, capped at
      // 100% — additive points would run past any believable ceiling.
      var lift = vars.reduce(function (t, v) {
        return t + (v.checked ? parseFloat(v.getAttribute("data-var")) : 0);
      }, 0);
      var positive = Math.min(100, val(f.positive) * (1 + lift / 100));

      var replies    = Math.round(people * val(f.reply) / 100);
      var interested = Math.round(replies * positive / 100);
      var booked     = Math.round(interested * val(f.book) / 100);
      var showed     = Math.round(booked * val(f.show) / 100);
      var closed     = Math.round(showed * val(f.close) / 100);

      var ltv   = val(f.deal) * val(f.retention);
      var added = closed * ltv;
      var spend = val(f.cost);
      var cac   = closed > 0 ? spend / closed : 0;

      // Slider read-outs
      out("daily").textContent     = num.format(daily);
      out("steps").textContent     = steps;
      out("reply").textContent     = val(f.reply).toFixed(1) + "%";
      out("positive").textContent  = val(f.positive) + "%";
      out("book").textContent      = val(f.book) + "%";
      out("show").textContent      = val(f.show) + "%";
      out("close").textContent     = val(f.close) + "%";
      out("deal").textContent      = money.format(val(f.deal));
      out("retention").textContent = val(f.retention) + (val(f.retention) === 1 ? " month" : " months");
      out("cost").textContent      = money.format(spend);

      $("[data-roi-effective]").textContent = positive.toFixed(1) + "%";
      $("[data-roi-ltv]").textContent = money.format(ltv);
      $("[data-roi-reach]").textContent =
        "~" + num.format(people) + " people contacted · ~" + num.format(emails) +
        " emails over " + days + " weekdays";

      // Results
      $("[data-roi-emails]").textContent     = num.format(emails);
      $("[data-roi-people]").textContent     = num.format(people);
      $("[data-roi-replies]").textContent    = num.format(replies);
      $("[data-roi-interested]").textContent = num.format(interested);
      $("[data-roi-booked]").textContent     = num.format(booked);
      $("[data-roi-showed]").textContent     = num.format(showed);
      $("[data-roi-closed]").textContent     = num.format(closed);
      $("[data-roi-cac]").textContent        = closed > 0 ? money.format(cac) : "—";
      $("[data-roi-added]").textContent      = money.format(added);
      $("[data-roi-spend]").textContent      = money.format(spend);

      var mult = spend > 0 ? added / spend : 0;
      $("[data-roi-multiple]").textContent = spend > 0 ? mult.toFixed(1) + "×" : "—";
      $("[data-roi-state]").setAttribute("data-state", mult >= 1 ? "gain" : "loss");
      $("[data-roi-verdict]").textContent = closed === 0
        ? "At these numbers the campaign closes nobody. Raise volume or the funnel rates."
        : (mult >= 1
            ? "Every $1 returns " + money.format(mult) + " in lifetime value."
            : "This doesn't clear. You'd spend more than the clients are worth.");

      if (mode === "retainer") buildTrajectory(emails, booked, closed, ltv);
    }

    function buildTrajectory(emails, booked, closed, ltv) {
      var body = $("[data-roi-tbody]");
      var rows = "";
      for (var m = 1; m <= 12; m++) {
        rows += "<tr><td>Month " + m + "</td><td>" + num.format(emails * m) +
                "</td><td>" + num.format(booked * m) +
                "</td><td>" + num.format(closed * m) +
                "</td><td>" + money.format(closed * ltv * m) + "</td></tr>";
      }
      body.innerHTML = rows;
    }

    function setMode(next) {
      mode = next;
      roi.querySelectorAll("[data-mode]").forEach(function (b) {
        var on = b.getAttribute("data-mode") === next;
        b.classList.toggle("is-active", on);
        b.setAttribute("aria-selected", String(on));
      });
      var pilot = next === "pilot";
      $("[data-roi-window]").textContent =
        "Volume over " + WEEKDAYS[next] + " weekdays.";
      $("[data-roi-basis]").textContent =
        pilot ? "Over the 60-day pilot." : "Per month, at 21 weekdays.";
      $("[data-roi-costlabel]").textContent = pilot ? "Pilot cost" : "Monthly cost";
      var traj = $("[data-roi-traj]");
      traj.hidden = pilot;
      // It starts hidden, so its reveal observer never fires; unhiding without
      // this leaves a fully transparent table.
      if (!pilot) traj.classList.add("is-visible");
      $("#roi-panel").setAttribute("aria-labelledby", pilot ? "tab-pilot" : "tab-retainer");

      // Retainer defaults to the lighter monthly footing.
      f.daily.value = pilot ? 5000 : 2500;
      f.cost.value  = pilot ? 10000 : 3150;
      recalc();
    }

    roi.querySelectorAll("[data-mode]").forEach(function (b) {
      b.addEventListener("click", function () { setMode(b.getAttribute("data-mode")); });
    });
    Object.keys(f).forEach(function (k) { f[k].addEventListener("input", recalc); });
    vars.forEach(function (v) { v.addEventListener("change", recalc); });

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
