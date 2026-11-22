# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Make deterministic runtime/model archives, including dependency notices."""
import argparse
import gzip
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument("--build", type=Path, required=True)
parser.add_argument("--models", type=Path, required=True)
parser.add_argument("--mode", choices=("wasip2", "wasip2-simd"), default="wasip2")
parser.add_argument("--wasm-tools", required=True)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
args.out.mkdir(parents=True, exist_ok=True)
binary = args.out / ("tesseract-" + args.mode + ".wasm")
unstripped = args.build / args.mode / "out" / "tesseract.wasm"
subprocess.run([args.wasm_tools, "strip", "--all", str(unstripped), "-o", str(binary)], check=True)
subprocess.run([args.wasm_tools, "validate", "--features", "all", str(binary)], check=True)
licenses = {
    "Tesseract.txt": root / "LICENSE",
    "Leptonica.txt": args.build / "src/leptonica/leptonica-license.txt",
    "zlib.txt": args.build / "src/zlib/LICENSE",
    "libpng.txt": args.build / "src/libpng/LICENSE",
    "libjpeg-turbo.md": args.build / "src/jpeg/LICENSE.md",
    "libjpeg-turbo-README.ijg": args.build / "src/jpeg/README.ijg",
    "libjpeg-turbo-README.md": args.build / "src/jpeg/README.md",
}
notices = {"notices/" + key: value.read_bytes() for key, value in licenses.items()}


def archive(filename, files):
    # Fixed headers make the archive independent of user, mtime and checkout path.
    with (args.out / filename).open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="", compresslevel=9) as compressed:
        with tarfile.open(fileobj=compressed, mode="w|", format=tarfile.USTAR_FORMAT) as tar:
            for name, data in sorted(files.items()):
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = 0o644
                tar.addfile(info, io.BytesIO(data))


archive(f"tesseract-{args.mode}-5.5.4.tar.gz", {
    "tesseract.wasm": binary.read_bytes(),
    "tesseract.meta.json": (root / "mcpone/tesseract.meta.json").read_bytes(),
    "README.md": (root / "mcpone/README.md").read_bytes(), **notices,
})
for quality in ("fast", "best"):
    files = {f"tesseract.wasm.resources/tessdata/{quality}/{lang}.traineddata": (args.models / quality / f"{lang}.traineddata").read_bytes() for lang in ("eng", "deu")}
    files["notices/traineddata-Apache-2.0.txt"] = (root / "LICENSE").read_bytes()
    archive(f"tesseract-models-{quality}-eng-deu.tar.gz", files)
manifest = {"upstream": "7e548e6eff172f38f97664afe7f7ce40db36c8d6", "mode": args.mode,
            "unstripped_bytes": unstripped.stat().st_size, "files": {}}
for file in sorted(args.out.iterdir()):
    if file.suffix not in (".gz", ".wasm"):
        continue
    data = file.read_bytes()
    manifest["files"][file.name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
(args.out / (args.mode + "-manifest.json")).write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps(manifest, indent=2))
