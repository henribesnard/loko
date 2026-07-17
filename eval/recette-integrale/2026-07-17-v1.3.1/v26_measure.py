
import csv, json, sys, time
bot = sys.argv[1]
from loko.bot.classifier.loader import load_classifier
clf = load_classifier(bot)
texts = [r["text"] for r in csv.DictReader(open("/app/eval/datasets/train.csv", encoding="utf-8"))]
texts = (texts * 3)[:200]
for t in texts[:10]:
    clf.classify_l1(t)
def p95(vals):
    s = sorted(vals)
    return s[max(0, int(round(0.95 * len(s))) - 1)]
a = []
for t in texts:
    t0 = time.perf_counter()
    clf.classify_l1(t)
    a.append((time.perf_counter() - t0) * 1000)
b = []
for t in texts:
    t0 = time.monotonic_ns()
    clf.classify_l1(t)
    b.append((time.monotonic_ns() - t0) / 1e6)
res = {"n": len(texts), "p95_perf_ms": round(p95(a), 2), "p95_mono_ms": round(p95(b), 2)}
res["ecart_rel"] = round(abs(res["p95_perf_ms"] - res["p95_mono_ms"]) / max(res["p95_perf_ms"], 1e-9), 3)
print(json.dumps(res))
