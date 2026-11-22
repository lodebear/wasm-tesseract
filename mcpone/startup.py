# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Measure the actual stripped release component, with JIT cache disabled."""
import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from benchmark import measured

parser = argparse.ArgumentParser()
parser.add_argument("--wasmtime", required=True)
parser.add_argument("--wasm", type=Path, required=True)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
prefix = [args.wasmtime, "run", "-C", "cache=n", "-W", "exceptions=y"]
with tempfile.TemporaryDirectory(prefix="ocr-startup-") as temp:
    precompiled = str(Path(temp) / "tesseract.cwasm")
    compile_metrics, _, _ = measured([args.wasmtime, "compile", "-C", "cache=n", "-W", "exceptions=y", str(args.wasm), "-o", precompiled])
    fresh = [measured(prefix + [str(args.wasm), "--version"])[0] for _ in range(3)]
    loaded = [measured(prefix + ["--allow-precompiled", precompiled, "--version"])[0] for _ in range(3)]
result = {"wasm_sha256": hashlib.sha256(args.wasm.read_bytes()).hexdigest(),
          "jit_cache": False, "compile": compile_metrics, "fresh_compile": fresh, "precompiled": loaded}
args.out.write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
