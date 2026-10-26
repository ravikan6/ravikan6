#!/usr/bin/env python3
"""run with: python .github/game/test_engine.py"""
import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine as e  # noqa: E402


def path_to(grid, src, dst, blocked=None):
    """shortest list of directions from src to dst."""
    prev = {src: None}
    q = deque([src])
    while q:
        cur = q.popleft()
        if cur == dst:
            break
        for name, (dx, dy) in e.DIRS.items():
            n = (cur[0] + dx, cur[1] + dy)
            if grid[n[1]][n[0]] == "#" or n in prev or n == blocked:
                continue
            prev[n] = (cur, name)
            q.append(n)
    steps = []
    cur = dst
    while prev[cur] is not None:
        cur, name = prev[cur]
        steps.append(name)
    return steps[::-1]


def solve_level(state, user="tester"):
    """plays the current level to the end the way a patient human would."""
    grid, exit_tile, _ = e.make_level(state["level"])
    level = state["level"]
    while state["gems"]:
        here = tuple(state["pos"])
        target = min((tuple(g) for g in state["gems"]), key=lambda g: len(path_to(grid, here, g, exit_tile)))
        for d in path_to(grid, here, target, exit_tile):
            moved, _ = e.apply_move(state, d, user)
            assert moved, f"solver bumped on level {level}"
    for d in path_to(grid, tuple(state["pos"]), exit_tile):
        moved, _ = e.apply_move(state, d, user)
        assert moved
    assert state["level"] == level + 1, "level did not advance"


def test_levels_are_solvable_and_sane():
    for level in range(1, 31):
        grid, exit_tile, gems = e.make_level(level)
        assert len(grid) == e.H and all(len(r) == e.W for r in grid)
        assert all(grid[0][x] == "#" and grid[-1][x] == "#" for x in range(e.W)), "top/bottom border open"
        assert all(grid[y][0] == "#" and grid[y][-1] == "#" for y in range(e.H)), "side border open"
        dist = e._bfs(grid, e.START)
        assert exit_tile in dist and exit_tile != e.START
        assert len(set(gems)) == len(gems) == min(2 + level, 9)
        assert all(g in dist and g not in (e.START, exit_tile) for g in gems)
        assert e.make_level(level) == (grid, exit_tile, gems), "generation is not deterministic"


def test_full_playthrough():
    state = e.new_state()
    for _ in range(12):
        solve_level(state)
    assert state["levels_cleared"] == 12 and state["level"] == 13
    assert state["pos"] == list(e.START)
    assert len(state["hall"]) == e.HALL_KEEP
    assert len(state["log"]) == e.LOG_KEEP


def test_wall_and_sealed_stairs():
    state = e.new_state()
    moved, msg = e.apply_move(state, "up", "tester")  # start is in the corner, up is wall
    assert not moved and "wall" in msg and state["moves_total"] == 0
    grid, exit_tile, _ = e.make_level(1)
    # walk next to the stairs with gems still left, then try to enter
    adj = None
    for name, (dx, dy) in e.DIRS.items():
        n = (exit_tile[0] - dx, exit_tile[1] - dy)
        if grid[n[1]][n[0]] != "#":
            adj, enter = n, name
    state["pos"] = list(adj)
    moved, msg = e.apply_move(state, enter, "tester")
    assert not moved and "sealed" in msg and state["pos"] == list(adj)


def test_input_handling():
    assert e.TITLE_RE.fullmatch("crawl: up") and e.TITLE_RE.fullmatch("CRAWL:  Down ")
    for bad in ("crawl: sideways", "crawl: up; rm -rf /", "hello", "crawl:", "crawl: up up"):
        assert not e.TITLE_RE.fullmatch(bad), bad
    assert e.clean_login("ravikan6") == "ravikan6"
    assert e.clean_login("some-user-1") == "some-user-1"
    for bad in ("", None, "a b", "x" * 40, "evil](http://x)", "-lead", "a\nb", "<script>"):
        assert e.clean_login(bad) == "anon", bad


def test_render():
    state = e.new_state()
    board = e.draw_board(state)
    assert board.count("@") == 1 and board.count("*") == state["gems_total"] and board.count("=") == 1
    assert len(board.splitlines()) == e.H and all(len(r) == e.W for r in board.splitlines())
    block = e.render_game(state)
    for d in e.DIRS:
        assert f"crawl%3A%20{d}" in block or f"crawl%3A+{d}" in block or f"crawl%3A%20{d}".replace("%20", "+") in block
    assert "github.com/ravikan6/ravikan6/issues/new" in block


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok  ", t.__name__)
    print(f"{len(tests)} passed")
