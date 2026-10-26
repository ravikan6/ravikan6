#!/usr/bin/env python3
"""the crawler: a tiny dungeon everyone on a github profile drives together.

usage:
    python engine.py issue "<issue title>" "<github login>"   apply a move
    python engine.py render                                   rebuild README.md
    python engine.py reset                                    back to level 1

state lives in state.json. the maze is never stored, it is rebuilt from the
level number, so the state file stays tiny and diffs stay readable.
"""
import json
import random
import re
import sys
from collections import deque
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
STATE_FILE = HERE / "state.json"
TEMPLATE = ROOT / "README.tpl.md"
README = ROOT / "README.md"

REPO = "ravikan6/ravikan6"  # owner/repo of the profile repository
BASE_SEED = 1026

CW, CH = 10, 5                 # maze size in cells
W, H = CW * 2 + 1, CH * 2 + 1  # grid size in tiles (21 x 11)
START = (1, 1)

DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
ARROWS = {"up": "⬆️", "down": "⬇️", "left": "⬅️", "right": "➡️"}
TITLE_RE = re.compile(r"crawl:\s*(up|down|left|right)\s*", re.IGNORECASE)
LOGIN_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")

LOG_KEEP = 6
HALL_KEEP = 5


# ---------------------------------------------------------------- level gen

def _bfs(grid, src):
    dist = {src: 0}
    q = deque([src])
    while q:
        x, y = q.popleft()
        for dx, dy in DIRS.values():
            n = (x + dx, y + dy)
            if grid[n[1]][n[0]] != "#" and n not in dist:
                dist[n] = dist[(x, y)] + 1
                q.append(n)
    return dist


def make_level(level):
    """returns (grid, exit_tile, gem_tiles) for a level, fully deterministic."""
    rng = random.Random(BASE_SEED * 1000 + level)
    grid = [["#"] * W for _ in range(H)]

    # recursive backtracker over the cell lattice
    grid[1][1] = "."
    seen = {(0, 0)}
    stack = [(0, 0)]
    while stack:
        cx, cy = stack[-1]
        nbrs = [
            (cx + dx, cy + dy)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            if 0 <= cx + dx < CW and 0 <= cy + dy < CH and (cx + dx, cy + dy) not in seen
        ]
        if not nbrs:
            stack.pop()
            continue
        nx, ny = rng.choice(nbrs)
        grid[ny * 2 + 1][nx * 2 + 1] = "."
        grid[cy + ny + 1][cx + nx + 1] = "."
        seen.add((nx, ny))
        stack.append((nx, ny))

    # knock out a few walls so the maze has loops and is less of a corridor
    for _ in range(6 + level):
        x = rng.randrange(1, W - 1)
        y = rng.randrange(1, H - 1)
        if grid[y][x] != "#":
            continue
        horiz = grid[y][x - 1] == "." and grid[y][x + 1] == "."
        vert = grid[y - 1][x] == "." and grid[y + 1][x] == "."
        if horiz != vert:
            grid[y][x] = "."

    dist = _bfs(grid, START)
    exit_tile = max(dist, key=lambda t: (dist[t], t[1], t[0]))

    floor = sorted(t for t in dist if t != START and t != exit_tile)
    gem_count = min(2 + level, 9)
    gems = rng.sample(floor, gem_count)
    return grid, exit_tile, sorted(gems)


# ------------------------------------------------------------------- state

def new_state():
    _, _, gems = make_level(1)
    return {
        "level": 1,
        "pos": list(START),
        "gems": [list(g) for g in gems],
        "gems_total": len(gems),
        "moves_level": 0,
        "moves_total": 0,
        "levels_cleared": 0,
        "players": {},
        "log": [],
        "hall": [],
    }


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return new_state()


def save_state(state):
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    tmp.replace(STATE_FILE)


def clean_login(raw):
    raw = (raw or "").strip()
    return raw if LOGIN_RE.fullmatch(raw) else "anon"


# ------------------------------------------------------------------- moves

def apply_move(state, direction, user):
    """mutates state. returns (moved, message)."""
    grid, exit_tile, _ = make_level(state["level"])
    x, y = state["pos"]
    dx, dy = DIRS[direction]
    nx, ny = x + dx, y + dy

    if grid[ny][nx] == "#":
        return False, f"bonk. @{user} walked into a wall, nothing changed."
    if (nx, ny) == exit_tile and state["gems"]:
        left = len(state["gems"])
        return False, f"the stairs are sealed. {left} gem{'s' if left != 1 else ''} still out there."

    state["pos"] = [nx, ny]
    state["moves_level"] += 1
    state["moves_total"] += 1
    state["players"][user] = state["players"].get(user, 0) + 1

    msg = f"@{user} stepped {direction}."
    entry = f"@{user} {direction}"

    if [nx, ny] in state["gems"]:
        state["gems"].remove([nx, ny])
        left = len(state["gems"])
        msg += " picked up a gem."
        entry += " + gem"
        if left == 0:
            msg += " the stairs are open now."

    if (nx, ny) == exit_tile and not state["gems"]:
        cleared = state["level"]
        state["hall"].append({"level": cleared, "user": user, "moves": state["moves_level"]})
        state["hall"] = state["hall"][-HALL_KEEP:]
        state["levels_cleared"] += 1
        state["level"] += 1
        _, _, gems = make_level(state["level"])
        state["gems"] = [list(g) for g in gems]
        state["gems_total"] = len(gems)
        state["pos"] = list(START)
        state["moves_level"] = 0
        msg += f" level {cleared} cleared! welcome to level {state['level']}."
        entry += f" (cleared level {cleared})"

    state["log"].append(entry)
    state["log"] = state["log"][-LOG_KEEP:]
    return True, msg


# ------------------------------------------------------------------ render

def draw_board(state):
    grid, exit_tile, _ = make_level(state["level"])
    rows = [row[:] for row in grid]
    for x in range(W):
        for y in range(H):
            if rows[y][x] == ".":
                rows[y][x] = " "
    ex, ey = exit_tile
    rows[ey][ex] = ">" if not state["gems"] else "="
    for gx, gy in state["gems"]:
        rows[gy][gx] = "*"
    px, py = state["pos"]
    rows[py][px] = "@"
    return "\n".join("".join(r) for r in rows)


def move_link(direction):
    title = quote(f"crawl: {direction}")
    body = quote("just press submit. a bot moves the @ and rewrites the profile. no need to edit anything.")
    return f"https://github.com/{REPO}/issues/new?title={title}&body={body}"


def render_game(state):
    got = state["gems_total"] - len(state["gems"])
    stairs = "open" if not state["gems"] else "sealed"
    board = draw_board(state)

    links = (
        f"[{ARROWS['up']} up]({move_link('up')})\n\n"
        f"[{ARROWS['left']} left]({move_link('left')}) &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"[right {ARROWS['right']}]({move_link('right')})\n\n"
        f"[{ARROWS['down']} down]({move_link('down')})"
    )

    top = sorted(state["players"].items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    board_rows = "\n".join(
        f"| {i + 1} | [@{u}](https://github.com/{u}) | {n} |" for i, (u, n) in enumerate(top)
    ) or "| - | nobody yet | 0 |"
    hall_rows = "\n".join(
        f"| {h['level']} | [@{h['user']}](https://github.com/{h['user']}) | {h['moves']} |"
        for h in reversed(state["hall"])
    ) or "| - | nobody yet | - |"
    log = "\n".join(f"- {line}" for line in reversed(state["log"])) or "- nothing yet, be the first"

    return f"""<div align="center">

```
{board}
```

`@` you &nbsp; `*` gem &nbsp; `=` sealed stairs &nbsp; `>` open stairs

**level {state['level']}** &nbsp;·&nbsp; gems {got}/{state['gems_total']} &nbsp;·&nbsp; stairs {stairs} &nbsp;·&nbsp; {state['moves_total']} step{'s' if state['moves_total'] != 1 else ''} taken together

{links}

</div>

<details>
<summary>recent steps, top crawlers, level clears</summary>

<br/>

{log}

| # | crawler | steps |
|---|---|---|
{board_rows}

| level | cleared by | steps |
|---|---|---|
{hall_rows}

</details>"""


def render_readme(state):
    tpl = TEMPLATE.read_text()
    if "{{GAME}}" not in tpl:
        raise SystemExit("README.tpl.md is missing the {{GAME}} placeholder")
    README.write_text(tpl.replace("{{GAME}}", render_game(state)))


# --------------------------------------------------------------------- cli

def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""

    if cmd == "reset":
        state = new_state()
        save_state(state)
        render_readme(state)
        print("reset")
        return 0

    if cmd == "render":
        render_readme(load_state())
        print("rendered")
        return 0

    if cmd == "issue" and len(argv) >= 4:
        m = TITLE_RE.fullmatch(argv[2].strip())
        if not m:
            print("that is not a move. use the arrow links in the profile readme.")
            return 2
        user = clean_login(argv[3])
        state = load_state()
        moved, msg = apply_move(state, m.group(1).lower(), user)
        if moved:
            save_state(state)
            render_readme(state)
        print(msg)
        return 0

    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
