"""Measure query throughput: callback filter vs selector.

Compares the only two ways to express the same predicate:
  A) list(tree.filter_nodes(lambda n: ...))     — the upstream idiom
  B) tree.query("...")                           — this fork

Each (workload, size) runs in its own process; rounds are interleaved inside that
process and the median of each workload is reported, because absolute timings on
Windows are noisy.

Usage:
    python measure_query.py
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths

PY = sys.executable
OUT = os.path.join(_paths.DATA, "query.json")

WORKER = r'''
import json, sys, time, gc, statistics
sys.path.insert(0, sys.argv[1])
from treelib import Tree

size = int(sys.argv[2])
reps = int(sys.argv[3])

# A wide, shallow tree: 1 root, 50 branches, the rest leaves.
tree = Tree()
tree.create_node("root", "root", data={"kind": "dir", "classes": "root"})
branch_count = 50
per_branch = max(1, (size - 1) // branch_count)
created = 1
for b in range(branch_count):
    bid = "b%03d" % b
    tree.create_node("branch-%03d" % b, bid, parent="root", data={"kind": "dir", "classes": "dir"})
    created += 1
    for i in range(per_branch):
        if created >= size:
            break
        nid = "n%06d" % created
        tree.create_node(
            "file-%06d.py" % created,
            nid,
            parent=bid,
            data={"kind": "file", "size": created % 500, "classes": "py" if created % 3 else "py draft"},
        )
        created += 1
    if created >= size:
        break

def predicate(node):
    data = node.data
    return data.get("kind") == "file" and "py" in data.get("classes", "").split()

def by_filter():
    return [n.identifier for n in tree.filter_nodes(predicate)]

def by_query():
    return tree.query("[kind=file].py").ids

def by_selector_complex():
    return tree.query("#root > * > .py:leaf").ids

# Warm up both paths so neither pays first-call costs inside the timed window.
by_filter(); by_query(); by_selector_complex()

samples = {"filter": [], "query": [], "complex": []}
for rep in range(reps):
    gc.collect()
    t0 = time.perf_counter(); r1 = by_filter(); t1 = time.perf_counter()
    r2 = by_query(); t2 = time.perf_counter()
    r3 = by_selector_complex(); t3 = time.perf_counter()
    samples["filter"].append((t1 - t0) * 1000)
    samples["query"].append((t2 - t1) * 1000)
    samples["complex"].append((t3 - t2) * 1000)

assert r1 == r2 == r3, "result sets differ: %d vs %d vs %d" % (len(r1), len(r2), len(r3))
print(json.dumps({
    "size": size,
    "matches": len(r1),
    "filter": statistics.median(samples["filter"]),
    "query": statistics.median(samples["query"]),
    "complex": statistics.median(samples["complex"]),
    "all": samples,
}))
'''


def run(size, reps, timeout=300):
    handle = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8")
    handle.write(WORKER)
    handle.close()
    try:
        process = subprocess.run(
            [PY, handle.name, _paths.fork_root(), str(size), str(reps)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    finally:
        os.unlink(handle.name)
    lines = process.stdout.decode("utf-8", "replace").strip().splitlines()
    if not lines:
        return {"error": "no-output", "stderr": process.stderr.decode()[:400]}
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError:
        return {"error": "bad-json", "raw": lines[-1][:300]}


def main():
    results = {}
    for size in (1000, 5000, 20000, 50000):
        reps = 5 if size <= 5000 else 3
        row = run(size, reps)
        results[str(size)] = row
        if "error" in row:
            print("size=%-6d ERROR %s" % (size, row["error"]))
        else:
            print("size=%-6d matches=%-6d filter=%7.2fms query=%7.2fms complex=%7.2fms"
                  % (size, row["matches"], row["filter"], row["query"], row["complex"]))

    os.makedirs(_paths.DATA, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(results, handle, indent=2)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
