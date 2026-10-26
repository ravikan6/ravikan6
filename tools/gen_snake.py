#!/usr/bin/env python3
"""renders an auto-playing snake game as one self-contained animated svg.

the game is simulated here (an ai plays it), then every move is baked into
SMIL animations, so the readme only needs <img src="assets/snake.svg">.
no javascript, no interaction, loops forever.

usage:
    python tools/gen_snake.py                      daily seed, writes assets/snake.svg
    python tools/gen_snake.py --seed 7             pick a seed
    python tools/gen_snake.py --frame 120          static still of step 120 (for previews)
"""
import argparse
import datetime
import random
import sys
from collections import deque
from pathlib import Path

COLS, ROWS = 26, 13
CELL = 22
STEPS = 260          # moves per loop
STEP_S = 0.09        # seconds per move
HOLD_S = 1.6         # pause on the last frame before looping
MIN_SCORE = 14       # a run must eat at least this much to be used

WIN_W = COLS * CELL + 40
HEADER_H = 38
BOARD_X = 20
BOARD_Y = HEADER_H + 18
BOARD_W, BOARD_H = COLS * CELL, ROWS * CELL
STATUS_Y = BOARD_Y + BOARD_H + 16
WIN_H = STATUS_Y + 38

DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1)]


# --------------------------------------------------------------- the player

def inside(p):
    return 0 <= p[0] < COLS and 0 <= p[1] < ROWS


def bfs(start, goal, blocked):
    prev = {start: None}
    q = deque([start])
    while q:
        cur = q.popleft()
        if cur == goal:
            path = []
            while prev[cur] is not None:
                path.append(cur)
                cur = prev[cur]
            return path[::-1]
        for dx, dy in DIRS:
            n = (cur[0] + dx, cur[1] + dy)
            if inside(n) and n not in blocked and n not in prev:
                prev[n] = cur
                q.append(n)
    return None


def flood(start, blocked):
    seen = {start}
    q = deque([start])
    while q:
        cur = q.popleft()
        for dx, dy in DIRS:
            n = (cur[0] + dx, cur[1] + dy)
            if inside(n) and n not in blocked and n not in seen:
                seen.add(n)
                q.append(n)
    return len(seen)


def choose(snake, food):
    """snake is head first. returns (next_head, mode) or None if boxed in."""
    head, tail = snake[0], snake[-1]
    body = set(snake)

    # 1. go for the food, but only if the snake can still reach its own tail afterwards
    path = bfs(head, food, body - {tail})
    if path:
        virtual = deque(snake)
        for step in path:
            virtual.appendleft(step)
            if step != food:
                virtual.pop()
        vbody = set(virtual)
        if bfs(virtual[0], virtual[-1], vbody - {virtual[-1]}) is not None or len(virtual) == COLS * ROWS:
            return path[0], "seek"

    # 2. otherwise follow the tail until a safe route to the food opens up
    path = bfs(head, tail, body - {tail})
    if path:
        return path[0], "chase"

    # 3. last resort: pick the neighbour with the most room
    best = None
    for dx, dy in DIRS:
        n = (head[0] + dx, head[1] + dy)
        if inside(n) and n not in body - {tail}:
            room = flood(n, body - {tail})
            if best is None or room > best[0]:
                best = (room, n)
    return (best[1], "chase") if best else None


def simulate(seed):
    rng = random.Random(seed)
    snake = deque([(6, 6), (5, 6), (4, 6)])

    def spawn():
        free = [(x, y) for x in range(COLS) for y in range(ROWS) if (x, y) not in snake]
        return rng.choice(free)

    food = spawn()
    score = 0
    frames = [(list(snake), food, score, "seek")]
    for _ in range(STEPS):
        pick = choose(snake, food)
        if pick is None:
            return None  # died
        nxt, mode = pick
        snake.appendleft(nxt)
        if nxt == food:
            score += 1
            food = spawn()
        else:
            snake.pop()
        frames.append((list(snake), food, score, mode))
    return frames if score >= MIN_SCORE else None


def find_run(seed):
    for s in range(seed, seed + 500):
        frames = simulate(s)
        if frames:
            return s, frames
    raise SystemExit("no good run found, try another seed")


# ------------------------------------------------------------------ svg bits

def f(n):
    return f"{n:.4f}".rstrip("0").rstrip(".")


def anim_discrete(attr, values, times, dur):
    """one discrete animation. times are seconds, values already stringified."""
    keys = ";".join(f(t / dur) for t in times)
    vals = ";".join(values)
    return (f'<animate attributeName="{attr}" calcMode="discrete" dur="{f(dur)}s" '
            f'repeatCount="indefinite" keyTimes="{keys}" values="{vals}"/>')


def compress(series):
    """series[i] is a value at step i. returns (step_indexes, values) where it changes."""
    idx, vals = [], []
    for i, v in enumerate(series):
        if not vals or vals[-1] != v:
            idx.append(i)
            vals.append(v)
    return idx, vals


STYLE = """
  .win{fill:#0d1117;stroke:#30363d}
  .bar{fill:#161b22}
  .sep{fill:#30363d}
  .board{fill:#0a0e13}
  .dot{fill:#1b222b}
  .body{fill:#2f9e5b}
  .head{fill:#7ee2a8}
  .eye{fill:#0a0e13}
  .food{fill:#f74c00}
  .t{fill:#c9d1d9}
  .d{fill:#7d8590}
  .accent{fill:#f74c00}
  .prog{fill:#f74c00}
  text{font-family:'JetBrains Mono',ui-monospace,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace}
  @media (prefers-color-scheme: light){
    .win{fill:#ffffff;stroke:#d0d7de}
    .bar{fill:#f6f8fa}
    .sep{fill:#d0d7de}
    .board{fill:#f6f8fa}
    .dot{fill:#dde2e8}
    .body{fill:#2da44e}
    .head{fill:#116329}
    .eye{fill:#ffffff}
    .t{fill:#24292f}
    .d{fill:#57606a}
  }
"""


def build_svg(frames, seed, still=None):
    n = len(frames)
    dur = n * STEP_S + HOLD_S
    times = [i * STEP_S for i in range(n)]
    out = []
    add = out.append

    add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIN_W} {WIN_H}" '
        f'width="{WIN_W}" height="{WIN_H}" role="img" '
        f'aria-label="a snake game that plays itself, looping forever">')
    add("<title>snake.rs, an ai playing snake on loop</title>")
    add(f"<style>{STYLE}</style>")
    add("<defs>"
        '<radialGradient id="glow"><stop offset="0" stop-color="#f74c00" stop-opacity=".55"/>'
        '<stop offset="1" stop-color="#f74c00" stop-opacity="0"/></radialGradient>'
        f'<clipPath id="win"><rect width="{WIN_W}" height="{WIN_H}" rx="12"/></clipPath>'
        "</defs>")

    # window chrome
    add(f'<rect class="win" x=".5" y=".5" width="{WIN_W - 1}" height="{WIN_H - 1}" rx="12"/>')
    add('<g clip-path="url(#win)">')
    add(f'<rect class="bar" width="{WIN_W}" height="{HEADER_H}"/>')
    add(f'<rect class="sep" y="{HEADER_H}" width="{WIN_W}" height="1"/>')
    add('</g>')
    for i, c in enumerate(("#ff5f56", "#ffbd2e", "#27c93f")):
        add(f'<circle cx="{22 + i * 18}" cy="{HEADER_H / 2}" r="5.5" fill="{c}"/>')
    add(f'<text class="d" x="{WIN_W / 2}" y="{HEADER_H / 2 + 4}" font-size="12" text-anchor="middle">'
        f'snake.rs  ~  autoplay</text>')
    add(f'<text class="d" x="{WIN_W - 18}" y="{HEADER_H / 2 + 4}" font-size="11" text-anchor="end">'
        f'seed {seed}</text>')

    # loop progress line under the header
    if still is None:
        add(f'<rect class="prog" y="{HEADER_H}" height="2" width="0">'
            f'<animate attributeName="width" from="0" to="{WIN_W}" dur="{f(dur)}s" repeatCount="indefinite"/></rect>')

    # board
    add(f'<rect class="board" x="{BOARD_X}" y="{BOARD_Y}" width="{BOARD_W}" height="{BOARD_H}" rx="8"/>')
    dots = []
    for x in range(COLS):
        for y in range(ROWS):
            dots.append(f'<circle cx="{BOARD_X + x * CELL + CELL / 2}" cy="{BOARD_Y + y * CELL + CELL / 2}" r="1.1"/>')
    add('<g class="dot">' + "".join(dots) + "</g>")

    def px(x):
        return BOARD_X + x * CELL

    def py(y):
        return BOARD_Y + y * CELL

    # body cells: one rect per visited cell, opacity toggled only when it changes
    occupancy = {}
    for i, (snake, _, _, _) in enumerate(frames):
        occ = set(snake[1:])
        for cell in occ | set(occupancy):
            occupancy.setdefault(cell, [0] * n)
        for cell in occ:
            occupancy[cell][i] = 1
    for (x, y), series in sorted(occupancy.items()):
        inset = 1.5
        base = (f'<rect class="body" x="{f(px(x) + inset)}" y="{f(py(y) + inset)}" '
                f'width="{CELL - 2 * inset}" height="{CELL - 2 * inset}" rx="6" ')
        if still is not None:
            if series[still]:
                add(base + 'opacity="1"/>')
            continue
        idx, vals = compress(series)
        if len(vals) == 1 and vals[0] == 0:
            continue
        add(base + f'opacity="{vals[0]}">' + anim_discrete(
            "opacity", [str(v) for v in vals], [times[i] for i in idx], dur) + "</rect>")

    # food: soft glow plus a pulsing core
    food_x = [px(fr[1][0]) + CELL / 2 for fr in frames]
    food_y = [py(fr[1][1]) + CELL / 2 for fr in frames]
    fi_x, fv_x = compress([f(v) for v in food_x])
    fi_y, fv_y = compress([f(v) for v in food_y])
    s = still if still is not None else 0
    add(f'<circle fill="url(#glow)" r="{CELL * 1.1}" cx="{f(food_x[s])}" cy="{f(food_y[s])}">'
        + ("" if still is not None else
           anim_discrete("cx", fv_x, [times[i] for i in fi_x], dur)
           + anim_discrete("cy", fv_y, [times[i] for i in fi_y], dur))
        + "</circle>")
    add(f'<circle class="food" r="6" cx="{f(food_x[s])}" cy="{f(food_y[s])}">'
        + ("" if still is not None else
           anim_discrete("cx", fv_x, [times[i] for i in fi_x], dur)
           + anim_discrete("cy", fv_y, [times[i] for i in fi_y], dur)
           + '<animate attributeName="r" values="5;7.5;5" dur="1s" repeatCount="indefinite"/>')
        + "</circle>")

    # head and eyes
    heads = [fr[0][0] for fr in frames]
    dirs = []
    for i, h in enumerate(heads):
        if i == 0:
            dirs.append((1, 0))
        else:
            p = heads[i - 1]
            dirs.append((h[0] - p[0], h[1] - p[1]))

    def eye_pos(h, d, side):
        cx, cy = px(h[0]) + CELL / 2, py(h[1]) + CELL / 2
        fx, fy = d
        sx, sy = -fy, fx  # perpendicular
        return cx + fx * 4 + sx * 4 * side, cy + fy * 4 + sy * 4 * side

    hx_i, hx_v = compress([f(px(h[0]) + 1) for h in heads])
    hy_i, hy_v = compress([f(py(h[1]) + 1) for h in heads])
    hs = still if still is not None else 0
    add(f'<rect class="head" width="{CELL - 2}" height="{CELL - 2}" rx="7" '
        f'x="{f(px(heads[hs][0]) + 1)}" y="{f(py(heads[hs][1]) + 1)}">'
        + ("" if still is not None else
           anim_discrete("x", hx_v, [times[i] for i in hx_i], dur)
           + anim_discrete("y", hy_v, [times[i] for i in hy_i], dur))
        + "</rect>")
    for side in (-1, 1):
        ex = [eye_pos(h, d, side) for h, d in zip(heads, dirs)]
        ei_x, ev_x = compress([f(e[0]) for e in ex])
        ei_y, ev_y = compress([f(e[1]) for e in ex])
        add(f'<circle class="eye" r="2.2" cx="{f(ex[hs][0])}" cy="{f(ex[hs][1])}">'
            + ("" if still is not None else
               anim_discrete("cx", ev_x, [times[i] for i in ei_x], dur)
               + anim_discrete("cy", ev_y, [times[i] for i in ei_y], dur))
            + "</circle>")

    # status bar
    add(f'<text class="d" x="{BOARD_X}" y="{STATUS_Y + 14}" font-size="12">score</text>')
    add(f'<text class="d" x="{BOARD_X + 150}" y="{STATUS_Y + 14}" font-size="12">length</text>')
    add(f'<text class="d" x="{BOARD_X + 300}" y="{STATUS_Y + 14}" font-size="12">brain</text>')

    def stat(x, strings, series):
        """swap between text values with discrete opacity animations."""
        for text in dict.fromkeys(series):
            vis = [1 if v == text else 0 for v in series]
            if still is not None:
                if series[still] == text:
                    add(f'<text class="t" x="{x}" y="{STATUS_Y + 14}" font-size="12" font-weight="700">{strings(text)}</text>')
                continue
            idx, vals = compress(vis)
            add(f'<text class="t" x="{x}" y="{STATUS_Y + 14}" font-size="12" font-weight="700" opacity="{vals[0]}">'
                f'{strings(text)}' + anim_discrete("opacity", [str(v) for v in vals],
                                                  [times[i] for i in idx], dur) + "</text>")

    stat(BOARD_X + 48, lambda v: f"{v:02d}", [fr[2] for fr in frames])
    stat(BOARD_X + 205, lambda v: f"{v:02d}", [len(fr[0]) for fr in frames])
    stat(BOARD_X + 345, lambda v: "seeking food" if v == "seek" else "chasing tail",
         [fr[3] for fr in frames])
    add(f'<text class="d" x="{WIN_W - 18}" y="{STATUS_Y + 14}" font-size="11" text-anchor="end">no input needed</text>')
    add("</svg>")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "assets" / "snake.svg"))
    ap.add_argument("--frame", type=int, default=None, help="render one static step instead of the animation")
    args = ap.parse_args()

    base = args.seed if args.seed is not None else datetime.date.today().toordinal()
    seed, frames = find_run(base)
    if args.frame is not None and not 0 <= args.frame < len(frames):
        raise SystemExit(f"--frame must be 0..{len(frames) - 1}")
    svg = build_svg(frames, seed, still=args.frame)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(svg)
    print(f"seed {seed}: score {frames[-1][2]}, {len(frames) - 1} moves, {len(svg) / 1024:.0f} KB -> {args.out}")


if __name__ == "__main__":
    sys.exit(main())
