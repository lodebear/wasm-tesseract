# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Compare native/WASI API timings and CLI startup; Linux/macOS host RSS."""
import argparse
import json
import os
import platform
import statistics
import subprocess
import tempfile
import time
import unicodedata
from pathlib import Path


def normalized(text):
    return " ".join(unicodedata.normalize("NFC", text).split())


def edits(a, b):
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        current = [i]
        for j, y in enumerate(b, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (x != y)))
        previous = current
    return previous[-1]


def measured(command):
    # wait4 reports this child's peak, unlike the cumulative RUSAGE_CHILDREN.
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        start = time.perf_counter()
        child = subprocess.Popen(command, stdout=out, stderr=err)
        _, status, usage = os.wait4(child.pid, 0)
        elapsed = (time.perf_counter() - start) * 1000
        child.returncode = os.waitstatus_to_exitcode(status)
        out.seek(0)
        err.seek(0)
        stdout, stderr = out.read().decode(), err.read().decode()
        if child.returncode:
            raise RuntimeError(f"exit {child.returncode}: {stderr}")
    rss = usage.ru_maxrss * (1024 if platform.system() == "Linux" else 1)
    return {"wall_ms": elapsed, "host_peak_rss_bytes": rss}, stdout, stderr


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--wasmtime", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--wasm-mode", default="wasip2")
    parser.add_argument("--only", nargs="*", help="Restrict corpus names for a compiler experiment")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    cases = json.loads((args.corpus / "manifest.json").read_text())["cases"]
    if args.only:
        cases = [case for case in cases if case["name"] in args.only]
    wasm = args.build / args.wasm_mode / "out"
    native = args.build / "native" / "out"
    precompiled = args.out / "ocr-bench.cwasm"
    compile_metrics, _, _ = measured([args.wasmtime, "compile", "-W", "exceptions=y", str(wasm / "ocr-bench.wasm"), "-o", str(precompiled)])
    wasm_prefix = [args.wasmtime, "run", "-W", "exceptions=y", "--allow-precompiled",
                   "--dir", f"{args.corpus.resolve()}::/corpus", "--dir", f"{args.models.resolve()}::/models"]
    startup = {}
    for runtime, command in {
        "native": [str(native / "tesseract"), "--version"],
        "wasm_fresh_compile": [args.wasmtime, "run", "-C", "cache=n", "-W", "exceptions=y", str(wasm / "tesseract.wasm"), "--version"],
    }.items():
        startup[runtime] = [measured(command)[0] for _ in range(args.repeats)]
    cli_precompiled = args.out / "tesseract.cwasm"
    cli_compile, _, _ = measured([args.wasmtime, "compile", "-W", "exceptions=y", str(wasm / "tesseract.wasm"), "-o", str(cli_precompiled)])
    startup["wasm_precompiled"] = [measured(wasm_prefix + [str(cli_precompiled), "--version"])[0] for _ in range(args.repeats)]
    rows = []
    with (args.out / "runs.jsonl").open("w") as stream:
        for runtime in ("native", "wasm"):
            for quality in ("fast", "best"):
                for case in cases:
                    settings = [(3, 0), (6, 0)]
                    if case["kind"] == "identifiers":
                        settings.append((6, 1))
                    for psm, no_dawg in settings:
                        for repeat in range(args.repeats):
                            if runtime == "native":
                                command = [str(native / "ocr-bench"), str(args.models / quality), case["lang"], str(psm), str(no_dawg), str(args.corpus / case["image"])]
                            else:
                                command = wasm_prefix + [str(precompiled), f"/models/{quality}", case["lang"], str(psm), str(no_dawg), f"/corpus/{case['image']}"]
                            host, stdout, stderr = measured(command)
                            metrics = json.loads(stdout)
                            text = bytes.fromhex(metrics.pop("text_hex")).decode("utf-8")
                            expected, actual = normalized(case["text"]), normalized(text)
                            row = {"runtime": runtime, "quality": quality, "case": case["name"], "kind": case["kind"],
                                   "lang": case["lang"], "psm": psm, "no_dawg": bool(no_dawg), "repeat": repeat,
                                   "character_edits": edits(expected, actual), "reference_characters": len(expected),
                                   "word_edits": edits(expected.split(), actual.split()), "reference_words": len(expected.split()),
                                   "blank_false_positive": not expected and bool(actual), "text": text, "stderr": stderr,
                                   **host, **metrics}
                            rows.append(row)
                            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                            stream.flush()
                        print(runtime, quality, case["name"], psm, no_dawg, "done", flush=True)
    result = {"platform": platform.system() + " " + platform.machine(), "repeats": args.repeats,
              "wasm_mode": args.wasm_mode, "compile": compile_metrics, "cli_compile": cli_compile,
              "startup": startup, "runs": rows}
    (args.out / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print("startup median ms:", {key: round(statistics.median(run['wall_ms'] for run in runs), 2) for key, runs in startup.items()})


if __name__ == "__main__":
    main()
