# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Paired scalar/SIMD measurements pinned to one Linux CPU, alternating order."""
import argparse
import json
import os
import statistics
import tempfile
from pathlib import Path

from benchmark import measured

parser = argparse.ArgumentParser()
parser.add_argument("--build", type=Path, required=True)
parser.add_argument("--models", type=Path, required=True)
parser.add_argument("--corpus", type=Path, required=True)
parser.add_argument("--wasmtime", required=True)
parser.add_argument("--cpu", type=int, required=True)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
os.sched_setaffinity(0, {args.cpu})
rows = []
with tempfile.TemporaryDirectory(prefix="ocr-compiler-") as temp:
    compiled = {}
    for mode in ("wasip2", "wasip2-simd"):
        compiled[mode] = str(Path(temp) / (mode + ".cwasm"))
        measured([args.wasmtime, "compile", "-W", "exceptions=y", str(args.build / mode / "out/ocr-bench.wasm"), "-o", compiled[mode]])
    for quality in ("fast", "best"):
        for case in ("clean-eng", "clean-deu", "degraded-eng", "degraded-deu", "identifiers-eng", "identifiers-deu"):
            for repeat in range(3):
                modes = ["wasip2", "wasip2-simd"]
                if repeat % 2:
                    modes.reverse()
                for mode in modes:
                    host, output, _ = measured([args.wasmtime, "run", "-W", "exceptions=y", "--allow-precompiled",
                        "--dir", f"{args.models.resolve()}::/models", "--dir", f"{args.corpus.resolve()}::/corpus",
                        compiled[mode], f"/models/{quality}", case.rsplit("-", 1)[1], "6", "0", f"/corpus/{case}.png"])
                    rows.append({"mode": mode, "quality": quality, "case": case, "repeat": repeat, **host, **json.loads(output)})
            scalar = [row for row in rows if row["case"] == case and row["quality"] == quality and row["mode"] == "wasip2"]
            simd = [row for row in rows if row["case"] == case and row["quality"] == quality and row["mode"] == "wasip2-simd"]
            assert {row["text_hex"] for row in scalar} == {row["text_hex"] for row in simd}
            a, b = (statistics.median(row["recognize_ms"] for row in group) for group in (scalar, simd))
            print(quality, case, f"scalar={a:.2f} ms SIMD={b:.2f} ms ratio={a/b:.3f}", flush=True)
args.out.write_text(json.dumps({"cpu": args.cpu, "runs": rows}, indent=2) + "\n")
