"""Measure the recursion cliff: for each depth, can upstream/patched serialise?

Each (arm, depth, operation) runs in its own subprocess so a crash in one cannot
poison the batch, and so the recursion limit is the interpreter's default.

Usage:
    python measure_recursion.py
    TREELIB_UPSTREAM=/path/to/treelib python measure_recursion.py
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths

PY = sys.executable
OUT = os.path.join(_paths.DATA, "recursion.json")

ARMS = {"patched": _paths.fork_root()}
upstream = _paths.find_upstream()
if upstream:
    ARMS["upstream"] = upstream
else:
    print("warning: upstream checkout not found, measuring the fork only")

WORKER = r'''
import json, sys, time
sys.path.insert(0, sys.argv[1])
from treelib import Tree

depth = int(sys.argv[2])
op = sys.argv[3]

tree = Tree()
tree.create_node("n0", "n0")
for i in range(1, depth):
    tree.create_node("n%d" % i, "n%d" % i, parent="n%d" % (i - 1))

start = time.perf_counter()
try:
    if op == "to_json":
        out = tree.to_json(with_identifier=True)
    elif op == "to_dict":
        out = tree.to_dict()
    elif op == "show":
        out = tree.show(stdout=False)
    elif op == "save2file":
        import tempfile, os
        p = os.path.join(tempfile.mkdtemp(), "t.txt")
        tree.save2file(p)
        out = open(p, "rb").read()
    else:
        raise SystemExit("bad op")
    elapsed = time.perf_counter() - start
    print(json.dumps({"ok": True, "ms": elapsed * 1000.0, "size": len(out)}))
except RecursionError:
    elapsed = time.perf_counter() - start
    print(json.dumps({"ok": False, "error": "RecursionError", "ms": elapsed * 1000.0}))
except Exception as exc:
    elapsed = time.perf_counter() - start
    print(json.dumps({"ok": False, "error": type(exc).__name__, "ms": elapsed * 1000.0}))
'''


def run(arm_root, depth, op, timeout=180):
    handle = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8")
    handle.write(WORKER)
    handle.close()
    try:
        process = subprocess.run(
            [PY, handle.name, arm_root, str(depth), op],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "ms": None}
    finally:
        os.unlink(handle.name)
    text = process.stdout.decode("utf-8", "replace").strip().splitlines()
    if not text:
        return {"ok": False, "error": "no-output", "ms": None}
    try:
        return json.loads(text[-1])
    except json.JSONDecodeError:
        return {"ok": False, "error": "bad-json", "ms": None}


def bisect_cliff(arm_root, op):
    """Smallest depth that fails, assuming monotonicity."""
    low, high = 2, 4000
    if run(arm_root, high, op)["ok"]:
        return None
    if not run(arm_root, low, op)["ok"]:
        return low
    while low + 1 < high:
        mid = (low + high) // 2
        if run(arm_root, mid, op)["ok"]:
            low = mid
        else:
            high = mid
    return high


def main():
    results = {"deps": {}, "cliffs": {}, "sweep": {}}

    print("== bisecting cliffs ==")
    for arm, root in ARMS.items():
        for op in ("to_json", "to_dict", "show", "save2file"):
            cliff = bisect_cliff(root, op)
            results["cliffs"]["%s/%s" % (arm, op)] = cliff
            print("  %-8s %-10s cliff=%s" % (arm, op, cliff if cliff else "none up to 4000"))

    print("== sweep ==")
    depths = [100, 250, 400, 550, 700, 850, 900, 950, 1000, 1100, 1500, 2000, 3000, 4000, 5000]
    for depth in depths:
        for op in ("to_json", "show"):
            for arm, root in ARMS.items():
                key = "%s|%d|%s" % (arm, depth, op)
                results["sweep"][key] = run(root, depth, op)
                row = results["sweep"][key]
                print("  %-8s d=%-5d %-8s %s %s" % (
                    arm, depth, op,
                    "OK  " if row["ok"] else "FAIL",
                    ("%.1fms" % row["ms"]) if row.get("ms") else row.get("error", ""),
                ))

    os.makedirs(_paths.DATA, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(results, handle, indent=2)
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
