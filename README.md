# SYSTEMERGE — landing page

Static landing page for a done-for-you outbound (cold email lead gen) offer.
No build step, no dependencies — open `index.html` or serve the folder.

```
index.html          # all copy and structure
assets/styles.css   # design tokens + styles
assets/main.js      # nav, CTA scroll, VSL + Calendly loaders, reveal animations
```

Local preview:

```bash
python3 -m http.server 8000   # then open http://localhost:8000
```

## Before it goes live

Five placeholders to fill in. Each is marked with an HTML comment in `index.html`.

| What | Where | How |
|---|---|---|
| **Calendly** | `index.html` → `data-calendly-url=""` | Paste your scheduling link, e.g. `https://calendly.com/systemerge/strategy-call`. The widget then lazy-loads when the section nears the viewport. Empty = styled placeholder. |
| **VSL** | `index.html` → `data-vsl-src=""` | Paste a YouTube/Vimeo/Loom **embed** URL, e.g. `https://www.youtube.com/embed/XXXXXXXXXXX`. The player only loads after a click, so no third-party script runs on page load. |
| **Contact email** | `index.html` → `[data-contact-email]` | Replace `hello@systemerge.com` in both the `href="mailto:"` and the link text. |
| **Client logos** | `index.html` → `<!-- CLIENT LOGOS -->` block | The strip ships commented out, as specified. Drop logo files into `assets/logos/`, uncomment the block, and update the `src`/`alt` on each `<li>`. |
| **Scarcity month** | automatic | "A few client spots open for *[month]*" fills with the current month via JS. To pin a specific month, replace `<span data-current-month>` with plain text. |

## Design system

Every color, font size, radius, and spacing value is a CSS custom property in the
`:root` block at the top of `assets/styles.css`. Nothing below that block
hardcodes a color, so the whole page can be re-skinned by editing those values.

Current direction: near-black surfaces, off-white type, a single electric-lime
accent used sparingly (status dot, checkmarks, step numbers, open FAQ chevron),
with off-white pill buttons carrying the primary CTAs.

> The reference at `styles.refero.design` was unreachable from the build
> environment (blocked by the network egress proxy), so these tokens are a
> stand-in. Swap the `:root` values to match it exactly.

## Conversion wiring

- Every **Book the strategy call** / **Book the call** button targets `#book`
  and smooth-scrolls to the Calendly section. They work without JS too.
- Nav: **How it works** → `#process`, **FAQ** → `#faq`.
- FAQ uses native `<details>`, so answers are open to search engines and work
  with JS disabled.

## Accessibility & performance

- Skip link, labeled landmarks, visible focus rings, `aria-expanded` on the
  mobile menu, Escape to close.
- `prefers-reduced-motion` disables reveal animations and smooth scrolling.
- No frameworks. The only third-party requests are the Inter webfont, plus
  Calendly and the video player — and those two load lazily / on click.
