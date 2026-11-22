# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Render the reproducible comparison tables used in the spike report."""
import argparse
import json
import statistics
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("results", type=Path)
parser.add_argument("--simd", type=Path)
args = parser.parse_args()
data = json.loads(args.results.read_text())
rows = data["runs"]


def pick(runtime, quality, case=None, psm=6):
    return [row for row in rows if row["runtime"] == runtime and row["quality"] == quality and row["psm"] == psm and not row["no_dawg"] and (case is None or row["case"] == case)]


def median(rows, key):
    return statistics.median(row[key] for row in rows)


def cer(rows):
    return 100 * sum(row["character_edits"] for row in rows) / max(1, sum(row["reference_characters"] for row in rows))


print("| Input | Fast CER % | Best CER % | Native fast ms | WASI fast ms | Native best ms | WASI best ms |")
print("|---|---:|---:|---:|---:|---:|---:|")
for case in dict.fromkeys(row["case"] for row in rows if row["kind"] != "blank"):
    fast, best = pick("wasm", "fast", case), pick("wasm", "best", case)
    print(f"| {case} | {cer(fast):.2f} | {cer(best):.2f} | {median(pick('native','fast',case),'recognize_ms'):.1f} | {median(fast,'recognize_ms'):.1f} | {median(pick('native','best',case),'recognize_ms'):.1f} | {median(best,'recognize_ms'):.1f} |")

native = {(r["quality"], r["case"], r["psm"], r["no_dawg"], r["repeat"]): r["text"] for r in rows if r["runtime"] == "native"}
wasm = [r for r in rows if r["runtime"] == "wasm"]
same = sum(r["text"] == native[(r["quality"], r["case"], r["psm"], r["no_dawg"], r["repeat"])] for r in wasm)
print(f"\nNative/WASI byte-identical text: {same}/{len(wasm)} matched runs.")
blanks = [r for r in wasm if r["kind"] == "blank"]
print(f"Blank false positives: {sum(r['blank_false_positive'] for r in blanks)}/{len(blanks)} WASI runs.")
print("\n| Runtime | Model | Median init ms | Max guest MiB | Max process RSS MiB |")
print("|---|---|---:|---:|---:|")
for runtime in ("native", "wasm"):
    for quality in ("fast", "best"):
        r = pick(runtime, quality)
        print(f"| {runtime} | {quality} | {median(r,'init_ms'):.2f} | {max(x['linear_memory_bytes'] for x in r)/2**20:.2f} | {max(x['host_peak_rss_bytes'] for x in r)/2**20:.2f} |")
print("\n| Startup (no model) | Median wall ms | Max process RSS MiB |")
print("|---|---:|---:|")
for name, r in data["startup"].items():
    print(f"| {name} | {median(r,'wall_ms'):.2f} | {max(x['host_peak_rss_bytes'] for x in r)/2**20:.2f} |")
print("\n| Model | PSM | Aggregate CER % | Aggregate WER % |")
print("|---|---:|---:|---:|")
for quality in ("fast", "best"):
    for psm in (3, 6):
        r = pick("wasm", quality, psm=psm)
        wer = 100 * sum(x["word_edits"] for x in r) / sum(x["reference_words"] for x in r)
        print(f"| {quality} | {psm} | {cer(r):.3f} | {wer:.3f} |")
for quality in ("fast", "best"):
    for no_dawg in (False, True):
        r = [x for x in wasm if x["quality"] == quality and x["kind"] == "identifiers" and x["psm"] == 6 and x["no_dawg"] == no_dawg]
        print(f"\nIdentifier CER {quality}, no_dawg={no_dawg}: {cer(r):.3f}%")
if args.simd:
    simd = json.loads(args.simd.read_text())["runs"]
    print("\n| Input | Model | Scalar ms | SIMD ms | Scalar / SIMD |")
    print("|---|---|---:|---:|---:|")
    for case in ("clean-eng", "clean-deu", "degraded-eng", "degraded-deu", "identifiers-eng", "identifiers-deu"):
        for quality in ("fast", "best"):
            r = [x for x in simd if x["runtime"] == "wasm" and x["quality"] == quality and x["case"] == case and x["psm"] == 6 and not x["no_dawg"]]
            scalar, vector = median(pick("wasm", quality, case), "recognize_ms"), median(r, "recognize_ms")
            print(f"| {case} | {quality} | {scalar:.1f} | {vector:.1f} | {scalar/vector:.2f}x |")
