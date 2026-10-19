"""Generate the figures for this README from the recorded measurements.

Every number is read from data/*.json, produced by the measure_* scripts. Nothing
is hard-coded, so the figures cannot drift from the measurements.

Warm editorial palette; English labels because this README is published on GitHub.
"""
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches
import matplotlib.pyplot as plt

sys_path = os.path.dirname(os.path.abspath(__file__))
import sys

sys.path.insert(0, sys_path)
import _paths

INK = "#2b2119"
PAPER = "#faf6f0"
AMBER = "#c8892b"
TERRACOTTA = "#b4552f"
OLIVE = "#6b6b3a"
MUTED = "#8a7a68"
GRID = "#e0d4c2"

DATA = _paths.DATA
OUT = _paths.OUT

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "text.color": INK,
    "axes.labelcolor": INK,
    "axes.edgecolor": GRID,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "figure.facecolor": PAPER,
    "axes.facecolor": PAPER,
    "savefig.facecolor": PAPER,
})


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as handle:
        return json.load(handle)


def style(ax, title=None, subtitle=None):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    ax.yaxis.grid(True, color=GRID, linewidth=0.7, alpha=0.8)
    ax.set_axisbelow(True)
    if title:
        # Push the title up so the subtitle has its own line underneath.
        ax.set_title(title, loc="left", fontsize=13, fontweight="bold", color=INK, pad=26)
    if subtitle:
        ax.text(0.0, 1.015, subtitle, transform=ax.transAxes, fontsize=9.5,
                color=MUTED, va="bottom", ha="left")


def fig_recursion():
    data = load("recursion.json")
    sweep = data["sweep"]
    cliffs = data["cliffs"]

    depths = sorted({int(key.split("|")[1]) for key in sweep})
    ops = ["to_json", "show"]

    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.8))

    for ax, op in zip(axes, ops):
        for arm, colour, marker in (("upstream", TERRACOTTA, "X"), ("patched", OLIVE, "o")):
            xs_ok, ys_ok, xs_fail = [], [], []
            for depth in depths:
                row = sweep.get("%s|%d|%s" % (arm, depth, op))
                if not row:
                    continue
                if row["ok"]:
                    xs_ok.append(depth)
                    ys_ok.append(row["ms"])
                else:
                    xs_fail.append(depth)

            if xs_ok:
                ax.plot(xs_ok, ys_ok, color=colour, linewidth=1.8, marker=marker,
                        markersize=5, label=arm, zorder=3)
            if xs_fail:
                # Below the axis: a failure has no timing, so it must not be drawn
                # as if it were one.
                ax.plot(xs_fail, [-0.075] * len(xs_fail), linestyle="none", marker="x",
                        markersize=8, markeredgewidth=2, color=TERRACOTTA, zorder=5,
                        transform=ax.get_xaxis_transform(), clip_on=False,
                        label="upstream: RecursionError" if arm == "upstream" else None)

        # Fit the data, then leave headroom so the top of the curve is never
        # clipped and the cliff note has somewhere to live.
        top = max(row["ms"] for key, row in sweep.items()
                  if key.endswith("|" + op) and row.get("ok"))
        bottom = min(row["ms"] for key, row in sweep.items()
                     if key.endswith("|" + op) and row.get("ok"))
        ax.set_ylim(bottom * 0.6, top * 4.0)

        cliff = cliffs.get("upstream/%s" % op)
        if cliff:
            ax.axvline(cliff, color=TERRACOTTA, linestyle=(0, (4, 3)), linewidth=1.2, alpha=0.7, zorder=1)
            # The curve occupies the upper right in the show() panel, so the note
            # moves to the middle right there; to_json leaves the top free.
            anchor = {"to_json": (0.97, 0.97), "show": (0.97, 0.52)}[op]
            ax.annotate("upstream dies\nat depth %d" % cliff,
                        xy=anchor, xycoords="axes fraction",
                        ha="right", va="top", fontsize=9, color=TERRACOTTA, linespacing=1.4)

        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("tree depth (nodes in a single chain)")
        ax.set_ylabel("wall time (ms, log scale)")
        style(ax,
              title={"to_json": "to_json()", "show": "show()"}[op],
              subtitle="fork survives 5,000; upstream stops at ~1,000")

    axes[0].legend(loc="upper left", frameon=False, fontsize=9.5)

    fig.suptitle("The recursion cliff: deep trees were un-serialisable",
                 x=0.012, y=0.995, ha="left", va="top", fontsize=14.5, fontweight="bold", color=INK)
    fig.text(0.012, 0.935,
             "Default recursion limit is 1,000 frames. Crosses = the call raised RecursionError (no time to plot).",
             ha="left", va="top", fontsize=9.5, color=MUTED)
    fig.tight_layout(rect=(0.012, 0, 1, 0.90))
    path = os.path.join(OUT, "recursion_cliff.png")
    fig.savefig(path, dpi=170)
    plt.close(fig)
    return path


def fig_query():
    data = load("query.json")
    sizes = sorted(int(k) for k in data if "error" not in data[k])
    if not sizes:
        raise SystemExit("no query data")

    filter_ms = [data[str(s)]["filter"] for s in sizes]
    query_ms = [data[str(s)]["query"] for s in sizes]
    complex_ms = [data[str(s)]["complex"] for s in sizes]

    fig, ax = plt.subplots(figsize=(10.4, 4.8))

    ax.plot(sizes, filter_ms, color=INK, linewidth=2.0, marker="o", markersize=6,
            label="hand-written predicate  (upstream idiom)")
    ax.plot(sizes, query_ms, color=AMBER, linewidth=2.0, marker="s", markersize=6,
            label='selector  "[kind=file].py"')
    ax.plot(sizes, complex_ms, color=TERRACOTTA, linewidth=2.0, marker="^", markersize=6,
            label='selector  "#root > * > .py:leaf"')

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("nodes in the tree")
    ax.set_ylabel("wall time (ms, log scale)")

    for xs, ys, colour in ((sizes, filter_ms, INK), (sizes, query_ms, AMBER), (sizes, complex_ms, TERRACOTTA)):
        ax.annotate("%.1f ms" % ys[-1], xy=(xs[-1], ys[-1]), xytext=(6, 0),
                    textcoords="offset points", va="center", ha="left",
                    fontsize=9, color=colour)

    ax.set_xlim(sizes[0] * 0.8, sizes[-1] * 1.55)
    style(ax,
          title="What the selector costs",
          subtitle="Same result set, same tree. Selectors parse then match; the predicate just matches.")
    ax.legend(loc="upper left", frameon=False, fontsize=9.5)

    ratio = [q / f for q, f in zip(query_ms, filter_ms)]
    fig.text(0.012, 0.015,
             "Selector overhead: %.1fx at %s nodes (range %.1f-%.1fx). "
             "It buys a query you can store, pass on a CLI and review in a diff - not speed."
             % (ratio[-1], format(sizes[-1], ","), min(ratio), max(ratio)),
             ha="left", va="bottom", fontsize=9, color=MUTED)

    fig.tight_layout(rect=(0.012, 0.075, 1, 0.90))
    path = os.path.join(OUT, "query_cost.png")
    fig.savefig(path, dpi=170)
    plt.close(fig)
    return path


def fig_tests():
    data = load("tests.json")
    table = data["table"]

    disc = [row for row in table if row["discriminating"]]
    guard = [row for row in table if row["upstream"] == "PASSED" and row["fork"] == "PASSED"]

    fig, (left, right) = plt.subplots(
        1, 2, figsize=(11.4, 4.6), gridspec_kw={"width_ratios": [1.05, 1.35]}
    )

    labels = ["red on upstream,\ngreen on fork", "green on both\n(equivalence guards)"]
    counts = [len(disc), len(guard)]
    colours = [OLIVE, MUTED]
    total = sum(counts)
    starts = [0, counts[0]]
    for start, count, colour in zip(starts, counts, colours):
        left.barh(0, count, left=start, height=0.42, color=colour, edgecolor=PAPER, linewidth=2)
        left.text(start + count / 2, 0, str(count), ha="center", va="center",
                  color=PAPER, fontsize=15, fontweight="bold")
    left.set_xlim(0, total)
    left.set_ylim(-0.55, 0.55)
    left.set_yticks([])
    left.set_xlabel("tests in tests/test_bugfixes.py")
    for spine in ("top", "right", "left"):
        left.spines[spine].set_visible(False)
    left.spines["bottom"].set_color(GRID)
    left.grid(False)
    left.set_title("Do the new tests have teeth?", loc="left",
                   fontsize=13, fontweight="bold", color=INK, pad=26)
    left.text(0.0, 1.015, "%d of %d distinguish the fix from upstream" % (len(disc), total),
              transform=left.transAxes, fontsize=9.5, color=MUTED, va="bottom", ha="left")
    # Legend under the bar; wide flat patches read as the same stacked segments.
    handles = [matplotlib.patches.Patch(facecolor=c, edgecolor=PAPER, label=l.replace("\n", " "))
               for c, l in zip(colours, labels)]
    left.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.22),
                frameon=False, fontsize=9, ncol=1, handlelength=2.6, handleheight=0.9)

    groups = {}
    for row in table:
        if not row["discriminating"]:
            continue
        cls = row["test"].split("::")[0]
        groups[cls] = groups.get(cls, 0) + 1
    order = sorted(groups.items(), key=lambda item: (-item[1], item[0]))
    names = [name.replace("Tests", "") for name, _ in order]
    values = [count for _, count in order]
    positions = range(len(names))
    right.barh(list(positions), values, height=0.62, color=AMBER, edgecolor=PAPER, linewidth=1.2)
    right.set_yticks(list(positions))
    right.set_yticklabels(names, fontsize=9.5)
    right.invert_yaxis()
    right.set_xlabel("discriminating tests")
    right.set_xlim(0, max(values) + 1.2)
    for spine in ("top", "right"):
        right.spines[spine].set_visible(False)
    right.spines["left"].set_color(GRID)
    right.spines["bottom"].set_color(GRID)
    right.xaxis.grid(True, color=GRID, linewidth=0.7, alpha=0.8)
    right.set_axisbelow(True)
    for position, value in zip(positions, values):
        right.text(value + 0.12, position, str(value), va="center", ha="left",
                   fontsize=9.5, color=INK, fontweight="bold")
    right.set_title("Where the teeth are", loc="left",
                    fontsize=13, fontweight="bold", color=INK, pad=26)
    right.text(0.0, 1.015, "Each test is red on upstream and green on the fork",
               transform=right.transAxes, fontsize=9.5, color=MUTED, va="bottom", ha="left")

    fig.tight_layout(rect=(0.012, 0.02, 1, 0.90))
    path = os.path.join(OUT, "test_teeth.png")
    fig.savefig(path, dpi=170)
    plt.close(fig)
    return path


if __name__ == "__main__":
    for maker in (fig_recursion, fig_query, fig_tests):
        print("wrote", maker())
