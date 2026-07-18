
import csv, json, sys, time
bot = sys.argv[1]
from loko.bot.classifier.loader import load_classifier
clf = load_classifier(bot)
texts = [r["text"] for r in csv.DictReader(open("/app/eval/datasets/train.csv", encoding="utf-8"))]
texts = (texts * 3)[:200]
for t in texts[:50]:
    clf.classify_l1(t)
def p95(vals):
    s = sorted(vals)
    return s[max(0, int(round(0.95 * len(s))) - 1)]
a, b = [], []
for t in texts:
    t0p = time.perf_counter()
    t0m = time.monotonic_ns()
    clf.classify_l1(t)
    t1m = time.monotonic_ns()
    t1p = time.perf_counter()
    a.append((t1p - t0p) * 1000)
    b.append((t1m - t0m) / 1e6)
res = {"n": len(texts), "p95_perf_ms": round(p95(a), 2), "p95_mono_ms": round(p95(b), 2)}
res["ecart_rel"] = round(abs(res["p95_perf_ms"] - res["p95_mono_ms"]) / max(res["p95_perf_ms"], 1e-9), 3)
print(json.dumps(res))
