"""Append entries to state/scorecard.json through analyst.bulletin.append.

Reads a JSON list of entries (without hashes) from a file or stdin,
verifies the chain before and after the write, and prints the head hash
either side. Refuses to write if any id is already on the chain.

  python3 scripts/chain_append.py entries.json
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from analyst import bulletin as B

SC = os.path.join(ROOT, "state", "scorecard.json")


def main(path):
    new = json.load(open(path)) if path != "-" else json.load(sys.stdin)
    entries = json.load(open(SC))
    B.verify(entries)
    before_n, before_h = len(entries), entries[-1]["hash"]
    have = {e["id"] for e in entries}
    dupes = [e["id"] for e in new if e["id"] in have]
    if dupes:
        sys.exit(f"refusing to write, ids already chained: {dupes}")
    for e in new:
        entries = B.append(entries, e)
    B.verify(entries)
    json.dump(entries, open(SC, "w"), indent=1)
    again = json.load(open(SC))
    B.verify(again)
    print(f"before: {before_n} entries, head {before_h}")
    print(f"after:  {len(again)} entries, head {again[-1]['hash']}")
    for e in again[before_n:]:
        print(f"  + {e['id']:22s} {e['status']:12s} {e['hash']}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "-")
