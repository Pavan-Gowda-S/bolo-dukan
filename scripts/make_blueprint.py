"""Dosa Corner: L-shaped ground-floor plan as SVG (1600 x 1000 px, 80 px = 1 m).

    python scripts/make_blueprint.py static/img/blueprints/dosa-corner-floor-plan.svg

The app's floor-plan upload takes PNG/JPG: open the SVG in a browser and export it, or use the PNG next to it.
Table spots T1-T6 sit at the % positions printed at the end, so they line up with the Floor plan editor."""
import math
import sys

W, H, M = 1600, 1000, 80  # canvas, metres
BG, LINE, FAINT, ACC, WALL = "#0f3d73", "#e8f1ff", "rgba(232,241,255,.55)", "#ffd166", "#f4f8ff"
out = []
a = out.append


def text(x, y, s, size=18, weight=600, fill=LINE, anchor="middle", rot=None, ls=1.5, op=1):
    t = f' transform="rotate({rot} {x} {y})"' if rot else ""
    a(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}" '
      f'letter-spacing="{ls}" opacity="{op}" font-family="Segoe UI, Arial, sans-serif"{t}>{s}</text>')


def rect(x1, y1, x2, y2, stroke=LINE, sw=2, fill="none", dash=None, rx=0):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    a(f'<rect x="{x1}" y="{y1}" width="{x2 - x1}" height="{y2 - y1}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')


def line(x1, y1, x2, y2, stroke=LINE, sw=2, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    a(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{sw}" stroke-linecap="square"{d}/>')


def door(hx, hy, length, wall_dir, swing, sw=2):
    """Gap is drawn separately. Hinge at (hx,hy); leaf drawn open 90 deg with its swing arc."""
    # wall_dir: direction along the wall from the hinge ('+x','-x','+y','-y'); swing: side the door opens to ('+x','-x','+y','-y')
    vec = {"+x": (1, 0), "-x": (-1, 0), "+y": (0, 1), "-y": (0, -1)}
    wx, wy = vec[wall_dir]
    sx, sy = vec[swing]
    ex, ey = hx + sx * length, hy + sy * length          # open leaf end
    cx, cy = hx + wx * length, hy + wy * length          # closed position end
    line(hx, hy, ex, ey, ACC, 3)
    cross = wx * sy - wy * sx
    sweep = 1 if cross > 0 else 0
    a(f'<path d="M {ex} {ey} A {length} {length} 0 0 {sweep} {cx} {cy}" fill="none" stroke="{ACC}" stroke-width="1.5" stroke-dasharray="6 5"/>')


def gap(x1, y1, x2, y2, sw=16):  # cut a door/window opening out of a wall
    line(x1, y1, x2, y2, BG, sw + 2)


def window(x1, y1, x2, y2):
    gap(x1, y1, x2, y2)
    if y1 == y2:
        line(x1, y1 - 5, x2, y2 - 5, LINE, 2); line(x1, y1 + 5, x2, y2 + 5, LINE, 2); line(x1, y1, x2, y2, LINE, 1)
    else:
        line(x1 - 5, y1, x2 - 5, y2, LINE, 2); line(x1 + 5, y1, x2 + 5, y2, LINE, 2); line(x1, y1, x2, y2, LINE, 1)


def table_round(cx, cy, r, seats, label):
    for i in range(seats):
        ang = 2 * math.pi * i / seats - math.pi / 2
        x, y = cx + math.cos(ang) * (r + 18), cy + math.sin(ang) * (r + 18)
        a(f'<rect x="{x - 11}" y="{y - 11}" width="22" height="22" rx="5" fill="none" stroke="{FAINT}" stroke-width="2" '
          f'transform="rotate({math.degrees(ang) + 90} {x} {y})"/>')
    a(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="rgba(255,209,102,.10)" stroke="{ACC}" stroke-width="2.5"/>')
    text(cx, cy + 7, label, 20, 800, ACC, ls=1)


def table_rect(cx, cy, w, h, seats_side, label):
    x1, y1 = cx - w / 2, cy - h / 2
    for i in range(seats_side):
        x = x1 + w * (i + .5) / seats_side
        rect(x - 11, y1 - 34, x + 11, y1 - 12, FAINT, 2, rx=5)
        rect(x - 11, y1 + h + 12, x + 11, y1 + h + 34, FAINT, 2, rx=5)
    rect(x1, y1, x1 + w, y1 + h, ACC, 2.5, "rgba(255,209,102,.10)", rx=8)
    text(cx, cy + 7, label, 20, 800, ACC, ls=1)


a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
a(f'<defs><pattern id="g" width="{M}" height="{M}" patternUnits="userSpaceOnUse"><path d="M {M} 0 L 0 0 0 {M}" fill="none" stroke="rgba(255,255,255,.08)" stroke-width="1"/></pattern>'
  f'<pattern id="g2" width="{M / 4}" height="{M / 4}" patternUnits="userSpaceOnUse"><path d="M {M / 4} 0 L 0 0 0 {M / 4}" fill="none" stroke="rgba(255,255,255,.035)" stroke-width="1"/></pattern>'
  f'<pattern id="tile" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(255,255,255,.07)" stroke-width="1"/></pattern></defs>')
a(f'<rect width="{W}" height="{H}" fill="{BG}"/><rect width="{W}" height="{H}" fill="url(#g2)"/><rect width="{W}" height="{H}" fill="url(#g)"/>')

# ---------- building outline: L shape (left arm 6.25 m wide, bottom wing 5.25 m deep)
L = [(60, 60), (560, 60), (560, 520), (1540, 520), (1540, 940), (60, 940)]
pts = " ".join(f"{x},{y}" for x, y in L)
a(f'<polygon points="{pts}" fill="rgba(255,255,255,.04)"/>')
a(f'<rect x="60" y="200" width="500" height="320" fill="url(#tile)"/>')  # kitchen floor tiles
a(f'<polygon points="{pts}" fill="none" stroke="{WALL}" stroke-width="16" stroke-linejoin="miter"/>')

# interior walls
line(60, 200, 560, 200, WALL, 8)          # store | kitchen
line(60, 520, 560, 520, WALL, 8)          # kitchen | dining
line(60, 800, 240, 800, WALL, 8)          # restroom top
line(240, 800, 240, 940, WALL, 8)         # restroom side

# ---------- openings
gap(330, 200, 400, 200, 8); door(330, 200, 70, "+x", "-y")                # store door (opens into the store)
gap(470, 520, 550, 520, 8); door(550, 520, 80, "-x", "+y")                # kitchen door (into dining)
gap(150, 800, 220, 800, 8); door(220, 800, 70, "-x", "-y")                # restroom door
gap(1540, 760, 1540, 900, 16)                                             # main entrance: double door
door(1540, 760, 70, "+y", "-x"); door(1540, 900, 70, "-y", "-x")
for w_ in ((700, 940, 900, 940), (1000, 940, 1200, 940), (600, 520, 760, 520), (900, 520, 1100, 520), (60, 580, 60, 740), (60, 300, 60, 440)):
    window(*w_)

# ---------- KITCHEN (60,200)-(560,520)
rect(78, 218, 142, 500, LINE, 2, "rgba(255,255,255,.06)")                 # range along the left wall
for yy in (250, 320, 390, 460):
    a(f'<circle cx="110" cy="{yy}" r="18" fill="none" stroke="{LINE}" stroke-width="2"/><circle cx="110" cy="{yy}" r="7" fill="none" stroke="{LINE}" stroke-width="1.5"/>')
rect(72, 212, 160, 506, LINE, 1.5, dash="8 6")                            # exhaust hood
text(176, 360, "DOSA TAWA · RANGE", 13, 700, LINE, rot=90, ls=2)
rect(190, 216, 330, 262, LINE, 2, "rgba(255,255,255,.05)"); a(f'<rect x="205" y="224" width="50" height="30" rx="6" fill="none" stroke="{LINE}" stroke-width="1.5"/><rect x="265" y="224" width="50" height="30" rx="6" fill="none" stroke="{LINE}" stroke-width="1.5"/>')
text(260, 282, "SINK", 12, 700, FAINT)
rect(345, 216, 440, 262, LINE, 2, "rgba(255,255,255,.05)"); text(392, 245, "DISH", 12, 700, LINE)
rect(462, 216, 542, 300, LINE, 2, "rgba(255,255,255,.05)"); line(462, 258, 542, 258, LINE, 1.5); text(502, 320, "FRIDGE", 12, 700, FAINT)
rect(205, 330, 425, 410, LINE, 2, "rgba(255,255,255,.05)", rx=6); text(315, 366, "PREP ISLAND", 14, 800, LINE); text(315, 388, "batter · grinder · chutney", 11, 500, FAINT, ls=.5)
rect(270, 506, 450, 534, ACC, 2, "rgba(255,209,102,.18)"); text(360, 556, "▲ SERVING PASS", 12, 800, ACC)
text(320, 470, "KITCHEN", 30, 800, LINE, ls=6)

# ---------- STORE (60,60)-(560,200)
for i in range(5):
    rect(80 + i * 62, 78, 130 + i * 62, 120, FAINT, 1.5)
text(220, 150, "SHELVES · DRY STORE", 13, 700, FAINT)
rect(430, 78, 540, 182, LINE, 2, "rgba(255,255,255,.05)"); text(485, 136, "COLD", 12, 800, LINE); text(485, 152, "ROOM", 12, 800, LINE)
text(250, 186, "STORE", 22, 800, LINE, ls=5)

# ---------- RESTROOM (60,800)-(240,940)
a(f'<ellipse cx="105" cy="900" rx="18" ry="24" fill="none" stroke="{LINE}" stroke-width="2"/><rect x="85" y="916" width="40" height="16" fill="none" stroke="{LINE}" stroke-width="2"/>')
rect(160, 900, 225, 930, LINE, 2); a(f'<ellipse cx="192" cy="915" rx="18" ry="9" fill="none" stroke="{LINE}" stroke-width="1.5"/>')
text(150, 860, "RESTROOM", 15, 800, LINE, ls=3)
# hand wash outside the restroom
rect(262, 905, 340, 932, LINE, 2); a(f'<ellipse cx="301" cy="918" rx="20" ry="8" fill="none" stroke="{LINE}" stroke-width="1.5"/>'); text(301, 895, "HAND WASH", 11, 700, FAINT)

# ---------- CASHIER (top-right of the dining hall, next to the entrance)
a(f'<path d="M 1290 540 L 1524 540 L 1524 720 L 1462 720 L 1462 602 L 1290 602 Z" fill="rgba(255,209,102,.16)" stroke="{ACC}" stroke-width="3"/>')
rect(1330, 552, 1378, 588, ACC, 2); text(1354, 576, "POS", 11, 800, ACC)     # billing screen
a(f'<circle cx="1420" cy="570" r="9" fill="none" stroke="{ACC}" stroke-width="2"/>')                     # UPI QR stand
text(1420, 598, "UPI", 10, 800, ACC)
a(f'<circle cx="1495" cy="650" r="13" fill="none" stroke="{FAINT}" stroke-width="2"/>')                   # cashier stool
text(1380, 650, "CASHIER", 22, 800, ACC, ls=4); text(1380, 674, "billing · parcel", 12, 600, ACC, ls=1, op=.85)

# waiting bench + entrance
rect(1300, 905, 1450, 928, FAINT, 2, rx=6); text(1375, 896, "WAITING", 11, 700, FAINT)
a(f'<path d="M 1590 830 L 1560 830" stroke="{ACC}" stroke-width="3"/><path d="M 1568 818 L 1556 830 L 1568 842" fill="none" stroke="{ACC}" stroke-width="3"/>')
text(1462, 836, "ENTRANCE", 15, 800, ACC, anchor="end", ls=3)

# ---------- DINING HALL tables (positions match the app's floor plan, in % of the image)
TABLES = [("T1", 170, 650, 4), ("T2", 400, 650, 4), ("T3", 420, 830, 4), ("T4", 720, 660, 4), ("T5", 980, 660, 4)]
for lab, x, y, n in TABLES:
    table_round(x, y, 36, n, lab)
table_rect(850, 840, 190, 62, 3, "T6")
text(1150, 792, "DINING HALL", 34, 800, LINE, ls=8, op=.9)
text(1150, 820, "6 tables · 26 seats", 14, 600, FAINT, ls=2)
for px, py in ((1240, 905), (90, 560), (1215, 560)):   # plants
    a(f'<circle cx="{px}" cy="{py}" r="14" fill="rgba(46,230,166,.18)" stroke="#7ff0c8" stroke-width="2"/>')

# ---------- outside: dimensions, north arrow, title block
def dim(x1, y1, x2, y2, label, off_x=0, off_y=0, rot=None):
    line(x1, y1, x2, y2, FAINT, 1.5)
    for x, y in ((x1, y1), (x2, y2)):
        if y1 == y2:
            line(x, y - 9, x, y + 9, FAINT, 1.5)
        else:
            line(x - 9, y, x + 9, y, FAINT, 1.5)
    text((x1 + x2) / 2 + off_x, (y1 + y2) / 2 + off_y, label, 14, 700, LINE, rot=rot, ls=1)


dim(60, 30, 560, 30, "6.25 m", off_y=-6)
dim(60, 972, 1540, 972, "18.50 m", off_y=22)
dim(28, 60, 28, 940, "11.00 m", off_x=-8, rot=-90)
dim(1572, 520, 1572, 940, "5.25 m", off_x=8, rot=90)
dim(580, 80, 580, 500, "5.75 m", off_x=16, rot=90)

# title block (open ground in the inside corner of the L)
rect(660, 110, 1180, 330, LINE, 2, "rgba(10,30,60,.55)")
line(660, 170, 1180, 170, LINE, 1.5); line(660, 290, 1180, 290, LINE, 1.5); line(920, 290, 920, 330, LINE, 1.5)
text(920, 152, "DOSA CORNER", 34, 800, ACC, ls=8)
text(920, 206, "GROUND FLOOR PLAN · L-SHAPED", 18, 700, LINE, ls=3)
text(920, 236, "Kitchen · Store · Cashier · Dining for 6 tables · Restroom", 14, 500, FAINT, ls=.5)
text(920, 264, "Built-up area ≈ 133 m²  ·  grid = 1 m", 14, 600, LINE, ls=1)
text(790, 316, "SCALE 1 : 100", 13, 700, LINE, ls=2)
text(1050, 316, "SHEET A-01", 13, 700, LINE, ls=2)
text(920, 380, "OPEN-AIR SEATING / PARKING", 16, 700, FAINT, ls=4, op=.8)
a(f'<rect x="700" y="400" width="440" height="80" fill="none" stroke="{FAINT}" stroke-width="1.5" stroke-dasharray="10 8"/>')

# north arrow + legend
a(f'<g transform="translate(1420 150)"><circle r="46" fill="none" stroke="{LINE}" stroke-width="2"/>'
  f'<path d="M 0 -38 L 14 18 L 0 8 L -14 18 Z" fill="{ACC}"/><text y="-52" text-anchor="middle" font-size="18" font-weight="800" fill="{LINE}" font-family="Segoe UI, Arial">N</text></g>')
lx, ly = 1250, 250
rect(lx, ly, 1520, 488, LINE, 1.5, "rgba(10,30,60,.55)")
text(lx + 135, ly + 28, "LEGEND", 14, 800, LINE, ls=3)
items = [("door", "Door + swing"), ("win", "Window"), ("table", "Table spot (T1–T6)"), ("chair", "Chair"), ("hood", "Exhaust hood")]
for i, (k, lab) in enumerate(items):
    y = ly + 62 + i * 38
    if k == "door":
        line(lx + 22, y + 6, lx + 22, y - 16, ACC, 3); a(f'<path d="M {lx + 22} {y - 16} A 22 22 0 0 1 {lx + 44} {y + 6}" fill="none" stroke="{ACC}" stroke-width="1.5" stroke-dasharray="5 4"/>')
    elif k == "win":
        line(lx + 14, y - 8, lx + 54, y - 8, LINE, 2); line(lx + 14, y + 2, lx + 54, y + 2, LINE, 2)
    elif k == "table":
        a(f'<circle cx="{lx + 34}" cy="{y - 3}" r="12" fill="rgba(255,209,102,.1)" stroke="{ACC}" stroke-width="2"/>')
    elif k == "chair":
        rect(lx + 24, y - 13, lx + 44, y + 7, FAINT, 2, rx=4)
    else:
        rect(lx + 14, y - 14, lx + 54, y + 8, LINE, 1.5, dash="6 4")
    text(lx + 70, y + 2, lab, 13, 600, LINE, anchor="start", ls=.5)

a("</svg>")
open(sys.argv[1], "w", encoding="utf-8").write("\n".join(out))
pos = [(lab, round(x / W * 100, 2), round(y / H * 100, 2)) for lab, x, y, _ in TABLES] + [("T6", round(850 / W * 100, 2), 84.0)]
print("table positions (% of image):", pos)
