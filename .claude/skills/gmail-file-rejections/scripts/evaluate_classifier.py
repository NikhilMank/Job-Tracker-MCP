#!/usr/bin/env python3
"""Measure rejection_classifier on labelled mail (run this after every change to its patterns).

  evaluate_classifier.py --positives work/rejected   (emails.json + bodies.json of the user's filed rejections)
                         --negatives work/neg1 work/neg2   (mail that should NOT be rejections)

Prints recall on the positives (user-sent replies excluded -- the Rejected folder also holds the user's own
messages and thread context, so ~10% of it is legitimately not a rejection) and every negative that was
flagged REJECTION/UNCLEAR for manual review: each is either a false positive (fix the patterns) or a real
rejection the user has not filed yet (move it!). Also lists positives missed that contain a regret word.
"""
import argparse, collections, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rejection_classifier import classify, USER_HINTS  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--positives", required=True)
ap.add_argument("--negatives", nargs="*", default=[])
ap.add_argument("--show-misses", type=int, default=15)
a = ap.parse_args()


def load(d):
    return json.load(open(f"{d}/emails.json")), json.load(open(f"{d}/bodies.json"))


pe, pb = load(a.positives)
c, misses = collections.Counter(), []
for e in pe:
    if any(h in e["frm"].lower() for h in USER_HINTS):
        continue
    r = classify(e["frm"], e["subject"], pb.get(e["id"], ""))
    c[r["verdict"]] += 1
    if r["verdict"] != "REJECTION":
        misses.append((e, r))
n = sum(c.values())
print(f"POSITIVES (not user-sent): {n}  ->  {dict(c)}  recall={c['REJECTION'] / n:.1%}")
regret = re.compile(r"(leider|unfortunately|bedauer|regret|malheureusement|helaas)", re.I)
shown = 0
for e, r in misses:
    if regret.search(pb.get(e["id"], "")[:2500]) and shown < a.show_misses:
        ss = [x for x in re.split(r"(?<=[.!?])\s+", pb[e["id"]]) if regret.search(x)]
        print(f"  miss[{r['verdict'][:3]}] {e['frm'].split('<')[0][:18]:18} | {(ss[0] if ss else '')[:150]}")
        shown += 1

for d in a.negatives:
    ne, nb = load(d)
    cc, flagged = collections.Counter(), []
    for e in ne:
        r = classify(e["frm"], e["subject"], nb.get(e["id"], ""))
        cc[r["verdict"]] += 1
        if r["verdict"] != "NOT_REJECTION":
            flagged.append((e, r))
    print(f"\nNEGATIVES {d}: {len(ne)} -> {dict(cc)}")
    for e, r in flagged:
        print(f"  {r['verdict'][:3]} {e['id'][:8]} {e['frm'].split('<')[0][:20]:20} | {e['subject'][:40]:40} | {r['sentence'][:110]} [{r['why'][:40]}]")
