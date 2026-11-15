"""Build six SYSTEMERGE logo concepts as outlined SVG.

Letterforms are drawn from the font outlines (no live text), shaped with
HarfBuzz so the fonts' own kerning applies. Every concept is emitted in four
variants: dark-ground, light-ground, single-colour (currentColor), and the
mark alone.
"""
import io, math, os, sys
import uharfbuzz as hb
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.boundsPen import BoundsPen

FONTS, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)

PALETTES = {
    "dark":  {"fg": "#ffffff", "acc": "#a881fe"},
    "light": {"fg": "#0b0b0b", "acc": "#6419ff"},
    "mono":  {"fg": "currentColor", "acc": "currentColor"},
}

class Face:
    def __init__(self, name):
        tt = TTFont(os.path.join(FONTS, name)); tt.flavor = None
        buf = io.BytesIO(); tt.save(buf); data = buf.getvalue()
        self.tt = TTFont(io.BytesIO(data))
        self.upem = self.tt["head"].unitsPerEm
        self.hb = hb.Font(hb.Face(data))
        self.gs = self.tt.getGlyphSet()
        self.order = self.tt.getGlyphOrder()
        self.cap = getattr(self.tt["OS/2"], "sCapHeight", 0) or 0.7 * self.upem

    def word(self, text, size, track=0.0, x0=0.0, y0=0.0):
        """Outline `text` at `size` px with its baseline at y0.
        Returns (path_d, glyph ink boxes, overall ink box)."""
        buf = hb.Buffer(); buf.add_str(text); buf.guess_segment_properties()
        hb.shape(self.hb, buf, {"kern": True, "liga": False})
        s = size / self.upem
        x, parts, boxes = 0, [], []
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            g = self.order[info.codepoint]
            ox = x0 + (x + pos.x_offset) * s
            pen = SVGPathPen(self.gs)
            self.gs[g].draw(TransformPen(pen, (s, 0, 0, -s, ox, y0 - pos.y_offset * s)))
            parts.append(pen.getCommands())
            bp = BoundsPen(self.gs); self.gs[g].draw(bp)
            if bp.bounds:
                a, b, c, d = bp.bounds
                boxes.append((ox + a * s, y0 - d * s, ox + c * s, y0 - b * s))
            x += pos.x_advance + track * self.upem
        ink = (min(b[0] for b in boxes), min(b[1] for b in boxes),
               max(b[2] for b in boxes), max(b[3] for b in boxes))
        return " ".join(p for p in parts if p), boxes, ink

    def capheight(self, size): return self.cap * size / self.upem


def svg(elements, box, pad, title):
    x0, y0, x1, y1 = box
    vb = f"{x0-pad:.2f} {y0-pad:.2f} {x1-x0+2*pad:.2f} {y1-y0+2*pad:.2f}"
    w, h = x1 - x0 + 2 * pad, y1 - y0 + 2 * pad
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" '
            f'width="{w:.0f}" height="{h:.0f}" role="img" aria-label="{title}">'
            f'<title>{title}</title>{"".join(elements)}</svg>\n')

def union(*bs):
    return (min(b[0] for b in bs), min(b[1] for b in bs),
            max(b[2] for b in bs), max(b[3] for b in bs))

def write(slug, variant, content):
    with open(os.path.join(OUT, f"{slug}-{variant}.svg"), "w") as f:
        f.write(content)

def emit(slug, title, lockup, mark):
    """lockup(pal) / mark(pal) -> (elements, box). Writes all four variants."""
    for v, pal in PALETTES.items():
        els, box = lockup(pal)
        write(slug, v, svg(els, box, 8, f"SYSTEMERGE — {title}"))
    els, box = mark(PALETTES["mono"])
    write(slug, "mark", svg(els, box, 4, f"SYSTEMERGE {title} mark"))
    els, box = mark(PALETTES["dark"])
    write(slug, "mark-dark", svg(els, box, 4, f"SYSTEMERGE {title} mark"))

TEXT = "SYSTEMERGE"
SYSTEM, EMERGE = (0, 5), (4, 9)   # glyph index spans; they share E,M (4..5)

# ── 1. Junction ────────────────────────────────────────────────────────────
# The name is a merge: SYSTEM and EMERGE overlap on their shared "EM". Two
# rules — one under each word — stack where the words overlap.
arch_b = Face("archivo-x-black.woff2")
def junction_lockup(pal, size=100):
    d, boxes, ink = arch_b.word(TEXT, size, track=0.01)
    t = size * 0.085; gap = size * 0.12
    ya = ink[3] + gap; yb = ya + t + t * 0.6
    ax0, ax1 = boxes[SYSTEM[0]][0], boxes[SYSTEM[1]][2]
    bx0, bx1 = boxes[EMERGE[0]][0], boxes[EMERGE[1]][2]
    els = [f'<path fill="{pal["fg"]}" d="{d}"/>',
           f'<rect fill="{pal["fg"]}" x="{ax0:.2f}" y="{ya:.2f}" width="{ax1-ax0:.2f}" height="{t:.2f}"/>',
           f'<rect fill="{pal["acc"]}" x="{bx0:.2f}" y="{yb:.2f}" width="{bx1-bx0:.2f}" height="{t:.2f}"/>']
    return els, union(ink, (ax0, ya, bx1, yb + t))
def junction_mark(pal, size=100):
    # The junction itself, isolated: "EM" over its two overlapping rule ends.
    d, boxes, ink = arch_b.word("EM", size, track=0.01)
    t = size * 0.085; gap = size * 0.12
    ya = ink[3] + gap; yb = ya + t * 1.6
    x0, x1 = ink[0], ink[2]; mid = (x0 + x1) / 2
    els = [f'<path fill="{pal["fg"]}" d="{d}"/>',
           f'<rect fill="{pal["fg"]}" x="{x0:.2f}" y="{ya:.2f}" width="{x1-x0:.2f}" height="{t:.2f}"/>',
           f'<rect fill="{pal["acc"]}" x="{x0:.2f}" y="{yb:.2f}" width="{x1-x0:.2f}" height="{t:.2f}"/>']
    return els, union(ink, (x0, ya, x1, yb + t))
emit("01-junction", "Junction", junction_lockup, junction_mark)

# ── 2. Merge ───────────────────────────────────────────────────────────────
# Two lanes converge into one: many sends become one booked call.
arch_m = Face("archivo-x-medium.woff2")
def merge_glyph(pal, h, x0=0.0, y0=0.0):
    sw = h * 0.17; w = h * 1.35; mx = x0 + w * 0.52; my = y0 + h / 2
    top = (f'M{x0:.2f} {y0+sw/2:.2f} C{x0+w*0.30:.2f} {y0+sw/2:.2f} {mx-w*0.22:.2f} {my:.2f} '
           f'{mx:.2f} {my:.2f} L{x0+w:.2f} {my:.2f}')
    bot = (f'M{x0:.2f} {y0+h-sw/2:.2f} C{x0+w*0.30:.2f} {y0+h-sw/2:.2f} {mx-w*0.22:.2f} {my:.2f} '
           f'{mx+sw*0.2:.2f} {my:.2f}')
    els = [f'<path d="{bot}" fill="none" stroke="{pal["acc"]}" stroke-width="{sw:.2f}"/>',
           f'<path d="{top}" fill="none" stroke="{pal["fg"]}" stroke-width="{sw:.2f}"/>']
    return els, (x0, y0, x0 + w, y0 + h), w
def merge_lockup(pal, size=100):
    cap = arch_m.capheight(size); h = cap * 1.15
    mels, mbox, mw = merge_glyph(pal, h, 0, -cap - (h - cap) / 2)
    d, boxes, ink = arch_m.word(TEXT, size, track=0.04, x0=mw + size * 0.42)
    return mels + [f'<path fill="{pal["fg"]}" d="{d}"/>'], union(mbox, ink)
def merge_mark(pal):
    els, box, _ = merge_glyph(pal, 100); return els, box
emit("02-merge", "Merge", merge_lockup, merge_mark)

# ── 3. Funnel ──────────────────────────────────────────────────────────────
# An S drawn from three bars that narrow like a funnel: contacted, replied,
# booked. The narrowest — the booked call — carries the accent.
unb = Face("unbounded-700.woff2")
def funnel_glyph(pal, h, x0=0.0, y0=0.0):
    """A squared S (Microgramma-style) whose three bars narrow like a funnel:
    visible widths 10u, 8u, 6u. Every turn is an explicit arc — the rounded
    top-left corner is what stops it reading as a 5."""
    u = h / 10; sw = 2 * u; r = 1.5
    X = lambda v: f"{x0+v*u:.2f}"; Y = lambda v: f"{y0+v*u:.2f}"; R = f"{r*u:.2f}"
    body = (f"M{X(10)} {Y(1)} H{X(1+r)} A{R} {R} 0 0 0 {X(1)} {Y(1+r)} V{Y(5-r)} "
            f"A{R} {R} 0 0 0 {X(1+r)} {Y(5)} H{X(7-r)} A{R} {R} 0 0 1 {X(7)} {Y(5+r)} V{Y(9-r)}")
    # The narrowest stage — the booked call — from a clean horizontal seam.
    tail = f"M{X(7)} {Y(9-r)} A{R} {R} 0 0 1 {X(7-r)} {Y(9)} H{X(2)}"
    st = f'fill="none" stroke-width="{sw:.2f}" stroke-linecap="butt"'
    els = [f'<path d="{body}" stroke="{pal["fg"]}" {st}/>',
           f'<path d="{tail}" stroke="{pal["acc"]}" {st}/>']
    return els, (x0, y0, x0 + 10 * u, y0 + 10 * u), 10 * u
def funnel_lockup(pal, size=92):
    d, boxes, ink = unb.word("systemerge", size, track=-0.01)
    h = ink[3] - ink[1]
    mels, mbox, mw = funnel_glyph(pal, h, 0, ink[1])
    d, boxes, ink = unb.word("systemerge", size, track=-0.01, x0=mw + size * 0.36)
    return mels + [f'<path fill="{pal["fg"]}" d="{d}"/>'], union(mbox, ink)
def funnel_mark(pal):
    els, box, _ = funnel_glyph(pal, 100); return els, box
emit("03-funnel", "Funnel", funnel_lockup, funnel_mark)

# ── 4. Booked ──────────────────────────────────────────────────────────────
# A week on the calendar with one slot taken — the literal deliverable.
syne = Face("syne-800.woff2")
def booked_glyph(pal, h, x0=0.0, y0=0.0, filled=(1, 2)):
    n, gap = 3, h * 0.10; c = (h - gap * (n - 1)) / n; sw = c * 0.16; r = c * 0.22
    els = []
    for row in range(n):
        for col in range(n):
            x = x0 + col * (c + gap); y = y0 + row * (c + gap)
            if (row, col) == filled:
                els.append(f'<rect fill="{pal["acc"]}" x="{x:.2f}" y="{y:.2f}" width="{c:.2f}" height="{c:.2f}" rx="{r:.2f}"/>')
            else:
                els.append(f'<rect fill="none" stroke="{pal["fg"]}" stroke-width="{sw:.2f}" '
                           f'x="{x+sw/2:.2f}" y="{y+sw/2:.2f}" width="{c-sw:.2f}" height="{c-sw:.2f}" rx="{r-sw/2:.2f}"/>')
    return els, (x0, y0, x0 + h, y0 + h), h
def booked_lockup(pal, size=96):
    d, boxes, ink = syne.word(TEXT, size, track=0.0)
    h = (ink[3] - ink[1]) * 1.55
    mels, mbox, mw = booked_glyph(pal, h, 0, ink[1] - (h - (ink[3] - ink[1])) / 2)
    d, boxes, ink = syne.word(TEXT, size, track=0.0, x0=mw + size * 0.36)
    return mels + [f'<path fill="{pal["fg"]}" d="{d}"/>'], union(mbox, ink)
def booked_mark(pal):
    els, box, _ = booked_glyph(pal, 100); return els, box
emit("04-booked", "Booked", booked_lockup, booked_mark)

# ── 5. Twin Arc ────────────────────────────────────────────────────────────
# A geometric S in two halves that meet at the spine. A sliver of gap keeps
# the two-ness legible even in a single colour.
sg = Face("space-grotesk-700.woff2")
def arc_path(cx, cy, r, a0, a1, ccw):
    """SVG arc from angle a0 to a1 (maths degrees, y-up) on circle (cx, cy)."""
    P = lambda a: (cx + r * math.cos(math.radians(a)), cy - r * math.sin(math.radians(a)))
    (sx, sy), (ex, ey) = P(a0), P(a1)
    sweep = abs(a1 - a0); large = 1 if sweep > 180 else 0
    return f'M{sx:.2f} {sy:.2f} A{r:.2f} {r:.2f} 0 {large} {0 if ccw else 1} {ex:.2f} {ey:.2f}'
def twin_glyph(pal, h, x0=0.0, y0=0.0):
    sw = h * 0.16; r = (h - sw) / 4; cx = x0 + r + sw / 2; gapdeg = 4
    top = arc_path(cx, y0 + sw / 2 + r, r, 18, 270 - gapdeg, ccw=True)
    bot = arc_path(cx, y0 + sw / 2 + 3 * r, r, 90 - gapdeg, -162, ccw=False)
    els = [f'<path d="{top}" fill="none" stroke="{pal["fg"]}" stroke-width="{sw:.2f}"/>',
           f'<path d="{bot}" fill="none" stroke="{pal["acc"]}" stroke-width="{sw:.2f}"/>']
    return els, (x0, y0, x0 + 2 * r + sw, y0 + h), 2 * r + sw
def twin_lockup(pal, size=100):
    d, boxes, ink = sg.word(TEXT, size, track=0.02)
    h = (ink[3] - ink[1]) * 1.22
    mels, mbox, mw = twin_glyph(pal, h, 0, ink[1] - (h - (ink[3] - ink[1])) / 2)
    d, boxes, ink = sg.word(TEXT, size, track=0.02, x0=mw + size * 0.34)
    return mels + [f'<path fill="{pal["fg"]}" d="{d}"/>'], union(mbox, ink)
def twin_mark(pal):
    els, box, _ = twin_glyph(pal, 100); return els, box
emit("05-twin-arc", "Twin Arc", twin_lockup, twin_mark)

# ── 6. Shared M ────────────────────────────────────────────────────────────
# SYSTEM and MERGE share their M. "SYSTE" sits on the top row, "ERGE" on the
# row below, and one double-height M belongs to both words. The M is set a
# lighter weight at double size so its stems match the Black letters beside
# it. Measured: 900 stem 0.150em; 400 x 2.18 = 0.144em on paper, but tall
# narrow forms read lighter, so 500 (x 2.18 = 0.166em) is the optical match.
bs_b = Face("bigshoulders-900.woff2")
bs_r = Face("bigshoulders-500.woff2")
def shared_lockup(pal, size=120, row_gap=0.18):
    cap = bs_b.capheight(size); H = cap * (2 + row_gap)
    m_size = H / (bs_r.cap / bs_r.upem)
    track = 0.03
    top_d, top_boxes, top_ink = bs_b.word("SYSTE", size, track=track, y0=cap)
    gap = size * 0.07
    m_x = top_ink[2] + gap
    m_d, _, m_ink = bs_r.word("M", m_size, x0=0, y0=H)
    m_d, _, m_ink = bs_r.word("M", m_size, x0=m_x - (m_ink[0]), y0=H)
    bot_d, _, bot_ink = bs_b.word("ERGE", size, track=track, x0=0, y0=H)
    bot_d, _, bot_ink = bs_b.word("ERGE", size, track=track, x0=m_ink[2] + gap - bot_ink[0], y0=H)
    els = [f'<path fill="{pal["fg"]}" d="{top_d}"/>',
           f'<path fill="{pal["acc"]}" d="{m_d}"/>',
           f'<path fill="{pal["fg"]}" d="{bot_d}"/>']
    return els, union(top_ink, m_ink, bot_ink)
def shared_mark(pal, size=120):
    # The name in miniature: first letter, the junction, last letter — in the
    # same zigzag as the lockup.
    cap = bs_b.capheight(size); H = cap * 2.18
    m_size = H / (bs_r.cap / bs_r.upem); g = size * 0.07
    m_d, _, mi = bs_r.word("M", m_size, y0=H)
    _, _, si = bs_b.word("S", size, y0=cap)
    s_d, _, si = bs_b.word("S", size, x0=mi[0] - g - si[2], y0=cap)
    _, _, ei = bs_b.word("E", size, y0=H)
    e_d, _, ei = bs_b.word("E", size, x0=mi[2] + g - ei[0], y0=H)
    els = [f'<path fill="{pal["fg"]}" d="{s_d}"/>',
           f'<path fill="{pal["acc"]}" d="{m_d}"/>',
           f'<path fill="{pal["fg"]}" d="{e_d}"/>']
    return els, union(si, mi, ei)
emit("06-shared-m", "Shared M", shared_lockup, shared_mark)

print("\n".join(sorted(os.listdir(OUT))))
