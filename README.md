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

Lives at `#roi`, linked from the nav. Four inputs — qualified calls per month,
close rate, average client value, and cost per qualified call — produce new
clients, revenue, cost, net, a return multiple, and the break-even close rate.

Three things it deliberately does **not** do:

- **It quotes no price.** Cost per call is the visitor's own input, labelled as
  their estimate, with a note that the real figure is set on the call. Nothing
  on the page presents a SYSTEMERGE rate.
- **It sends nothing.** All arithmetic runs in the browser. There is no form
  post, no analytics call, no storage.
- **It doesn't only sell.** When the numbers don't clear, the result switches to
  a muted state and reports the loss honestly — which is the same promise the
  hero makes ("we'll tell you on the first call if the economics don't work").

Verified against hand-computed values, including a loss case, a divide-by-zero
guard on client value, and clamping of out-of-range typed input.

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
