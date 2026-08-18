# SYSTEMERGE — landing page

Static landing page for a done-for-you outbound (cold email lead gen) offer.
No build step, no dependencies — open `index.html` or serve the folder.

```
index.html            # all copy and structure
assets/styles.css     # design tokens + styles
assets/main.js        # nav, CTA scroll, VSL + Calendly loaders, ROI calculator, reveals
assets/fonts/         # self-hosted Inter + Space Grotesk (~85KB)
```

Local preview:

```bash
python3 -m http.server 8000   # then open http://localhost:8000
```

## Before it goes live

| What | Where | How |
|---|---|---|
| **Calendly** | `data-calendly-url=""` | Paste your scheduling link. The widget lazy-loads when the section nears the viewport. Empty = styled placeholder. |
| **VSL** | `data-vsl-src=""` | Paste a YouTube/Vimeo/Loom **embed** URL. The player only loads after a click, so no third-party script runs on page load. |
| **Contact email** | `[data-contact-email]` | Replace `hello@systemerge.com` in both the `mailto:` href and the link text. |
| **Client logos** | `<!-- CLIENT LOGOS -->` block | Ships commented out, as specified. Drop files into `assets/logos/`, uncomment, update each `src`/`alt`. |
| **Scarcity month** | automatic | Fills with the current month via JS. To pin a month, replace `<span data-current-month>` with plain text. |
| **ROI defaults** | `#roi` inputs | The `value=""` on each input is the starting figure a visitor sees. Change them to whatever is typical for your market. |

## ROI calculator

Lives at `#roi`, linked from the nav, with two modes:

- **60-Day Pilot** — 42 weekdays of sending, one-off cost, single ROI figure.
- **Retainer** — 21 weekdays a month, monthly cost, plus a cumulative
  12-month trajectory table.

Every figure is a **slider**: daily send volume, emails per person, reply rate,
positive response rate, call booking / show / close rates, average deal size,
retention, and cost. Six offer-variable toggles lift the positive response rate
proportionally. All read-outs sit beside their label so the value is never
hidden under the thumb, and the results panel is sticky on desktop so you can
see the numbers move while dragging.

The funnel rounds at each stage — whole replies produce whole leads produce
whole calls — which is what makes the projections reconcile.

Three things it deliberately does **not** do:

- **It quotes no price.** Cost is the visitor's own slider, labelled as their
  estimate, with a note that the real figure is set on the call.
- **It sends nothing.** All arithmetic runs in the browser.
- **It doesn't only sell.** When the numbers don't clear, the headline result
  switches to a muted state and says so plainly.

Verified against the supplied reference figures in both modes: pilot returns
210,000 / 105,000 / 1,575 / 394 / 79 / 63 / 13 / $390,000 / 39.0x, and retainer
returns 52,500 / 26,250 / 394 / 99 / 20 / 16 / 3 / $90,000 / 28.6x with a
12-month trajectory ending at 630,000 emails and $1,080,000.

## Design system

Implements the **Uizard** style reference — "violet aurora over obsidian."
Every value is a CSS custom property in the `:root` block of `assets/styles.css`.

The canvas is Obsidian `#0b0b0b` throughout. There are no alternating bands —
variation comes from card presence and the hero bloom alone, exactly as the
reference specifies.

**Rules the stylesheet holds to:**

- Violet Glow `#a881fe` is reserved for the primary action, the sparkle indicator and the hero glow. Nothing else.
- Signal Blue `#1e90ff` is the nav utility action only, and never shares a surface with the violet.
- Cards are 1px Graphite hairlines at 16px radius — outlines, not panels. No drop shadows on cards.
- The radius scale stays plural: 16px cards, 12px buttons, 8px inputs, 9999px pills.
- The violet outer glow belongs to the primary CTA and nothing else.
- Section headers stand alone — no eyebrow, no subtitle.

**Font substitutions.** Satoshi and Clash Grotesk are commercial; the reference
names Inter and Space Grotesk Bold as substitutes, and both are self-hosted, so
the page makes no third-party font request.

### Three deliberate deviations

1. **The primary CTA label is Carbon `#212121`, not white.** The reference
   specifies white on `#a881fe`, which measures **2.90:1** — below AA, on the
   page's most important control. Carbon reaches 5.55:1, and the reference's own
   prompt guide already pairs `#212121` with a filled action.

2. **The nav utility button uses the same Carbon label.** White on Signal Blue
   is **3.24:1**, which fails for 14px text. Carbon reaches 4.98:1.

3. **Form inputs use a `#606060` border, not Graphite `#2e2e2e`.** Graphite is
   1.45:1 on Obsidian. That's fine for a card outline, where the content carries
   the boundary, but a form control's border *is* its affordance and needs 3:1.
   `#606060` is the nearest neutral that clears it, at 3.13:1.

## Conversion wiring

- Every **Book the strategy call** / **Book the call** button targets `#book`
  and smooth-scrolls there. They work without JS too.
- Nav: **How it works** → `#process`, **FAQ** → `#faq`, **ROI Calculator** → `#roi`.
- FAQ uses native `<details>`, so answers are open to search engines and work
  with JS disabled.

## Accessibility & performance

- Skip link, labeled landmarks, visible focus rings, `aria-expanded` on the
  mobile menu, Escape to close, 44px tap target.
- Calculator inputs are properly labelled; results are in an `aria-live` region
  so screen readers hear them update.
- All text/background pairs meet WCAG AA (see the three deviations above).
- `prefers-reduced-motion` disables reveal animations and smooth scrolling.
- Reveal animations are gated behind a `.js` class set inline in `<head>`, so
  the page is fully visible with scripts disabled.
- No frameworks and no third-party requests on load.
- Verified with no horizontal overflow at 1920, 1440, 1180, 1024, 820, 768,
  480, 390 and 320px.
