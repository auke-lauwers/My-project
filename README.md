# SYSTEMERGE — landing page

Static landing page for a done-for-you outbound (cold email lead gen) offer.
No build step, no dependencies — open `index.html` or serve the folder.

```
index.html            # all copy and structure
assets/styles.css     # design tokens + styles
assets/main.js        # nav, CTA scroll, VSL + Calendly loaders, reveal animations
assets/fonts/         # self-hosted Inter, Playfair Display, IBM Plex Mono (232KB)
```

Local preview:

```bash
python3 -m http.server 8000   # then open http://localhost:8000
```

## Before it goes live

Five placeholders, each marked with an HTML comment in `index.html`.

| What | Where | How |
|---|---|---|
| **Calendly** | `data-calendly-url=""` | Paste your scheduling link. The widget lazy-loads when the section nears the viewport. Empty = styled placeholder. |
| **VSL** | `data-vsl-src=""` | Paste a YouTube/Vimeo/Loom **embed** URL. The player only loads after a click, so no third-party script runs on page load. |
| **Contact email** | `[data-contact-email]` | Replace `hello@systemerge.com` in both the `mailto:` href and the link text. |
| **Client logos** | `<!-- CLIENT LOGOS -->` block | Ships commented out, as specified. Drop files into `assets/logos/`, uncomment, update each `src`/`alt`. |
| **Scarcity month** | automatic | Fills with the current month via JS. To pin a month, replace `<span data-current-month>` with plain text. |

## Design system

Implements the **Resend** style reference — "black velvet with violet neon."
Every value is a CSS custom property in the `:root` block at the top of
`assets/styles.css`.

The canvas is pure `#000000` throughout — no gradients, glows or chromatic
washes, and no light/dark alternation. Depth comes entirely from 1px `#292d30`
hairlines; there is not a single drop shadow in the stylesheet.

**Rules the stylesheet holds to:**

- Buttons are ghost — transparent fill, hairline border, white label. Never filled, never colorful
- Radius scale is exactly two values: 16px cards, 6px buttons/badges/inputs, plus 24px on the one large panel. The announcement badge is the single pill, per its component spec
- Iris Violet `#9281f7` belongs to code strings and identifiers only. It is never a heading colour and never lands on a button
- Status hues (green/blue/violet-glow/amber) appear only in the status indicator row
- The hero is an editorial serif at -0.01em; section headlines are a geometric sans with -0.05em tracking — the compressed tracking is the signature

**Font substitutions.** Domaine, aBC Favorit and Commit Mono are commercial. The
reference names substitutes for each, and those are what's used: Playfair
Display for the Domaine hero, Inter for aBC Favorit headlines and body, IBM Plex
Mono for Commit Mono. All self-hosted, so the page makes no third-party font
request. To switch to the real faces, add their `@font-face` blocks and repoint
`--font-display` / `--font-sans` / `--font-mono`.

**Hero cube.** The reference's WebGL cube is done in CSS 3D instead — six black
faces with hairline edges, a 26s rotation, no glow and no colour. It costs
nothing, needs no library, and holds still under `prefers-reduced-motion`.

**Terminal window.** The system uses code windows as its product-proof surface,
and that is the only place the violet legitimately belongs. The one on the page
shows a sending setup with the `from:`/`reply_to:` split that keeps your main
domain clean. It is **illustrative, not real campaign data** — no metrics or
results are claimed. Delete the block if you'd rather not show a sample.

### Three deliberate deviations

1. **The display step is capped at 68px, not 96px.** The reference's 96px hero
   carries a three-word statement. Ours is a full sentence, and at 96px it wrapped
   to seven lines and pushed the CTA off-screen. The type role is unchanged.

2. **Ghost buttons use Iron `#6e727a` for the border, not Graphite `#292d30`.**
   A ghost button's border is its only affordance, and Graphite on black measures
   **1.51:1** — effectively invisible. Iron is the palette's own "low-emphasis
   borders" token and clears the 3:1 non-text threshold at 4.35:1. Cards and
   dividers still use Graphite as specified.

3. **Code comments use Ash Gray, not Charcoal `#464a4d`.** Charcoal is
   **2.35:1** on black. The reference describes it as "text that should
   disappear into the surface," which is fine for decoration but not for lines
   that carry meaning.

The reference also contradicts itself on the primary action: the Primary Button
component and the Do's list both insist buttons stay ghost and never filled,
while the Agent Prompt Guide lists "#3b9eff (filled action)". Two of three say
ghost, so ghost it is. If you'd rather trade fidelity for conversion punch, a
white-filled CTA is a two-line change to `.btn` — the reference permits
"white-text-on-black" as the alternative.

### Added labels

The system pairs a technical eyebrow with each section headline. These short
mono labels aren't in the supplied copy — *The problem, What we run, Build vs
buy, How it works, Qualification, Answers, Book the call*. Your headline and
body copy is verbatim.

## Conversion wiring

- Every **Book the strategy call** / **Book the call** button targets `#book`
  and smooth-scrolls to the Calendly section. They work without JS too.
- Nav: **How it works** → `#process`, **FAQ** → `#faq`.
- FAQ uses native `<details>`, so answers are open to search engines and work
  with JS disabled.

## Accessibility & performance

- Skip link, labeled landmarks, visible focus rings, `aria-expanded` on the
  mobile menu, Escape to close, 44px tap target.
- All text/background pairs meet WCAG AA (see deviations 2 and 3).
- `prefers-reduced-motion` disables reveal animations, smooth scrolling and the
  cube rotation.
- Reveal animations are gated behind a `.js` class set inline in `<head>`, so
  the page is fully visible with scripts disabled.
- No frameworks and no third-party requests on load. Calendly and the video
  player load lazily / on click.
- Verified with no horizontal overflow at 1920, 1440, 1180, 1024, 820, 768,
  480, 390 and 320px.
