"""Which regression tests actually distinguish upstream from the fork?

Runs tests/test_bugfixes.py against both trees and records, per test, whether it
passes on upstream and on the fork. A test is *discriminating* only if it is red
on upstream and green on the fork; the rest are equivalence guards.

Usage:
    python measure_tests.py
    TREELIB_UPSTREAM=/path/to/treelib python measure_tests.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths

PY = sys.executable
OUT = os.path.join(_paths.DATA, "tests.json")
FORK = _paths.fork_root()
TEST_FILE = "test_bugfixes.py"


def collect(base, workdir):
    """Copy the tree's package plus the fork's tests, then run that file verbosely."""
    shutil.copytree(os.path.join(base, "treelib"), os.path.join(workdir, "treelib"))
    shutil.copytree(os.path.join(FORK, "tests"), os.path.join(workdir, "tests"))
    env = dict(os.environ)
    env["PYTHONPATH"] = workdir
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    process = subprocess.run(
        [PY, "-m", "pytest", "tests/" + TEST_FILE, "-v", "--no-header", "-p", "no:cacheprovider"],
        cwd=workdir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output = process.stdout.decode("utf-8", "replace")
    outcome = {}
    for line in output.splitlines():
        match = re.match(r"^tests/" + TEST_FILE + r"::(\S+)\s+(PASSED|FAILED|ERROR)", line)
        if match:
            outcome[match.group(1)] = match.group(2)
    return outcome, output


def main():
    upstream = _paths.require_upstream()
    results = {}
    for label, base in (("upstream", upstream), ("fork", FORK)):
        workdir = tempfile.mkdtemp()
        outcome, output = collect(base, workdir)
        results[label] = outcome
        print("%-9s collected=%d passed=%d failed=%d"
              % (label, len(outcome),
                 sum(1 for v in outcome.values() if v == "PASSED"),
                 sum(1 for v in outcome.values() if v != "PASSED")))
        if not outcome:
            print(output[-1500:])
        shutil.rmtree(workdir, ignore_errors=True)

    all_tests = sorted(set(results["upstream"]) | set(results["fork"]))
    table = []
    for name in all_tests:
        u = results["upstream"].get(name, "MISSING")
        p = results["fork"].get(name, "MISSING")
        table.append({
            "test": name,
            "upstream": u,
            "fork": p,
            "discriminating": u != "PASSED" and p == "PASSED",
        })

    disc = [row for row in table if row["discriminating"]]
    guard = [row for row in table if row["upstream"] == "PASSED" and row["fork"] == "PASSED"]
    other = [row for row in table if not row["discriminating"] and row not in guard]

    print("\ntotal tests      :", len(table))
    print("discriminating   :", len(disc))
    print("equivalence guard:", len(guard))
    print("other            :", len(other))
    for row in other:
        print("   OTHER", row)

    os.makedirs(_paths.DATA, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as handle:
        json.dump({"table": table, "summary": {
            "total": len(table),
            "discriminating": len(disc),
            "guard": len(guard),
        }}, handle, indent=2)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
