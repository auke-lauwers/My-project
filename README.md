# SYSTEMERGE — landing page

Static landing page for a done-for-you outbound (cold email lead gen) offer.
No build step, no dependencies — open `index.html` or serve the folder.

```
index.html            # all copy and structure
assets/styles.css     # design tokens + styles
assets/main.js        # nav, CTA scroll, VSL + Calendly loaders, reveal animations
assets/sphere.svg     # generated particle sphere (hero brand graphic)
assets/fonts/         # self-hosted Inter + IBM Plex Mono (168KB total)
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

Implements the **Ameba** style reference — "midnight control room, electric blue
pulse inside frosted glass panels." Every value is a CSS custom property in the
`:root` block at the top of `assets/styles.css`.

**Two registers.** Dark atmospheric bands (Midnight Ink `#00052e`, centered
content) carry the hero, pain points, capabilities, risk reversal, FAQ and
booking. Light product bands (Paper `#ffffff`, left-aligned) carry build-vs-buy,
process and qualification. A single gradient transition marks the handoff from
dark to light, used once, as the reference specifies.

Switching a section between registers is one class — `band-dark` or
`band-light`. Those classes only reassign role tokens (`--text`, `--text-muted`,
`--hairline`, `--eyebrow`, `--panel`); no rule below the token block
re-specifies a color per band.

**Rules the stylesheet holds to:**

- Signal Blue `#0428cb` fills the one CTA and nothing else structural
- Arc Cyan `#34fcff` is atmospheric only — glow, status dots, eyebrows on dark. Never a border, button, or body text
- No shadows anywhere; separation is hairline borders plus the radial glow
- Radii cap at 8px (cards, buttons) and 4px (tags) — no pills
- Display type is Inter 300 with negative tracking, per-step as specified
- IBM Plex Mono at 0.085em tracking is reserved for system/metadata chrome — eyebrows, step numbers, micro-labels

**Font substitutions.** F37 Bolton and Open Sauce Sans are commercial, and the
reference names Inter as an approved substitute for both. Inter (variable,
300–700) and IBM Plex Mono are self-hosted from `assets/fonts/`, so the page
makes no third-party font request. To switch to the real faces, add their
`@font-face` blocks and repoint `--font-display` / `--font-body`.

**Particle sphere.** `assets/sphere.svg` is generated, not hand-drawn — 1500
points placed by golden-angle spiral on a sphere and projected orthographically,
which is what produces the dense rim and sparse center. Depth drives dot size,
opacity and color (Arc Cyan toward the viewer, Signal Blue behind). Regenerate
by editing the constants at the top of the generator snippet in the commit
history, or just replace the file.

### Two deliberate deviations

1. **Muted text uses Mist `#8185a0`, not Fog `#6b6b83`.** The reference
   specifies Fog for hero subtext and muted copy on dark, but Fog against
   Midnight Ink measures **3.82:1** — below the 4.5:1 WCAG AA floor for body
   text. Mist is the neighbouring palette step and clears it at **5.46:1**. Fog
   is retained for hairlines and non-text chrome. Revert the two lines flagged
   in the `:root` block for strict fidelity at the cost of the contrast failure.

2. **Signal Blue is the primary CTA fill.** The reference contradicts itself
   here: the color table says "do not promote it to the primary CTA color,"
   while both the Primary CTA Button component spec ("Background #0428cb") and
   the Do's list ("reserve Signal Blue exclusively for the single filled CTA")
   say the opposite. Two of three call it the CTA, so that's the reading used.

Also note the reference's surface tokens list `#00052` — a five-digit value that
isn't valid hex. It's an extraction artifact for `#00052e`, and that's what the
stylesheet uses.

### Added labels

The system's "two-tier entry" (technical eyebrow above an editorial headline)
needs an eyebrow per section. These short mono labels aren't in the supplied
copy — *The problem, What we run, Build vs buy, How it works, Qualification,
Risk reversal, Answers, Book the call*. Your headline and body copy is verbatim.
The two floating hero cards are likewise illustrative; delete them if you'd
rather the hero carried no example messages.

## Conversion wiring

- Every **Book the strategy call** / **Book the call** button targets `#book`
  and smooth-scrolls to the Calendly section. They work without JS too.
- Nav: **How it works** → `#process`, **FAQ** → `#faq`.
- FAQ uses native `<details>`, so answers are open to search engines and work
  with JS disabled.

## Accessibility & performance

- Skip link, labeled landmarks, visible focus rings, `aria-expanded` on the
  mobile menu, Escape to close, 44px tap target.
- All text/background pairs meet WCAG AA (see deviation 1 above).
- `prefers-reduced-motion` disables reveal animations and smooth scrolling.
- Reveal animations are gated behind a `.js` class set inline in `<head>`, so
  the page is fully visible with scripts disabled.
- No frameworks and no third-party requests on load. Calendly and the video
  player load lazily / on click.
