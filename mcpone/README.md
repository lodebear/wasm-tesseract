# Standalone Tesseract for WASI Preview2

This fork adds a small, offline OCR command to Tesseract **5.5.4**, upstream
commit `7e548e6eff172f38f97664afe7f7ce40db36c8d6`. The fork's default branch is
`monocp-wasm`. The upstream command-line interface is retained.
The fork also returns failure if it cannot create any requested output renderer;
upstream otherwise reports success after a denied output-file creation.

The measured recommendation is the SIMD variant with `fast` models. A paired
single-CPU comparison improved fast recognition by 1.32–1.37x without changing
the output. Best models ran but were slower and less accurate on this small
synthetic corpus; keep them optional rather than treating that as a general
accuracy ranking. The scalar variant remains available for comparison.

## Build

Requirements: CMake 3.22+, Make, a native C/C++ compiler, curl, tar, patch,
SHA-256 tools, and **wasi-sdk 33.0**. Use the SDK's complete sysroot, not just
its clang executable. SDK 34 builds run in a recent standalone Wasmtime, but
import `wasi:cli/exit@0.2.12.exit-with-code`, which the tested MonoCP host does
not implement. SDK 33 uses WASI 0.2.6 imports and works with that host.

```sh
export WASI_SDK_PATH=/path/to/wasi-sdk-33.0
export TESSERACT_BUILD_ROOT=/path/to/build-output
./build-tesseract-wasi.sh wasip2-simd
./build-tesseract-wasi.sh wasip2
./build-tesseract-wasi.sh native
bash mcpone/fetch-models.sh /path/to/models
```

The build fetches and verifies pinned zlib 1.3.1, libpng 1.6.50,
libjpeg-turbo 3.2.1, and Leptonica 1.87.0 archives. Everything is statically
linked into the component. PNG and JPEG use those codecs; BMP and PNM use
Leptonica's built-in readers. TIFF, GIF, WebP and JPEG2000 are omitted.
Leptonica's named temporary-file and external-program diagnostic helpers
return explicit errors on WASI; its diagnostic CPU timers use monotonic elapsed
time. These helpers are not needed for the tested OCR paths.

Both targets use `-O2`, `FAST_FLOAT=ON`, no OpenMP, no legacy engine, no training
tools, no ScrollView GUI/debug fonts, no CURL, no libarchive, and no LTO.
The native baseline retains the upstream ARM NEON implementation where
available. `wasip2-simd` additionally enables compiler vectorization with
`-msimd128`; it does not implement a new hand-written Tesseract SIMD kernel.

WASI uses an 8 MiB stack and a 1 GiB linear-memory ceiling. C++ uses
`-fwasm-exceptions -mllvm -wasm-use-legacy-eh=false` and links the SDK's
exception-enabled libc++/libc++abi plus `-lunwind`. All C/C++ code uses
`-mllvm -wasm-enable-sjlj`; `-lsetjmp` supports codec error handling. Signal
and process-clock emulation libraries are linked explicitly. The engine must
support standardized WebAssembly exception handling, including exception refs.
This is a Preview2 component, not a Preview1 executable or an Emscripten module.

## Run

```sh
wasmtime run -W exceptions=y \
  --dir /path/to/images::/images --dir /path/to/models::/models \
  /path/to/build-output/wasip2-simd/out/tesseract.wasm \
  /images/input.png stdout --tessdata-dir /models/fast -l eng --oem 1 --psm 6
```

Use `-l deu` for German, `-l eng+deu` for mixed text, and `/models/best` to
select the optional float models. PSM 6 assumes one text block; use PSM 3
for automatic page segmentation. The default upstream PSM is 3. Orientation
detection is disabled in this LSTM-only build: PSM 0 fails, and PSM 1/12 warn
and fall back to PSM 3/11. Adding `osd.traineddata` alone cannot enable it.
Language models contain dictionaries and LSTM weights, not an LLM. Identifiers
can be wrong even when ordinary prose is correct. Check important numbers.

`stdout` writes UTF-8 text to standard output. An output basename writes a
`.txt` file. Errors use standard error and a nonzero exit code. The upstream
CLI also supports richer outputs when its separate config/font assets are
supplied; this distribution validates plain text only. PDF input is not
supported. Network access is not needed or imported by the component.

## MonoCP resources

Unpack the executable and model archives into the same tool directory:

```text
tesseract.wasm
tesseract.meta.json
tesseract.wasm.resources/tessdata/fast/eng.traineddata
tesseract.wasm.resources/tessdata/fast/deu.traineddata
tesseract.wasm.resources/tessdata/best/eng.traineddata  # optional
tesseract.wasm.resources/tessdata/best/deu.traineddata  # optional
```

The metadata declares a read-only `tessdata` asset and
`TESSDATA_PREFIX=${tessdata}/fast`. MonoCP expands that to
`/.sandbox/resources/assets/tesseract.wasm/tessdata/fast`. To select best in
MonoCP, pass `--tessdata-dir
/.sandbox/resources/assets/tesseract.wasm/tessdata/best`.

Add any compatible `<language>.traineddata` to the selected directory before
generating the tool lock; no executable rebuild is needed. `--list-langs` lists
the installed files. Model directories are not writable per-thread storage.
The current installer verifies one entire, signed/locked tool tree: adding a
file beside an installed bundle is rejected. Independently installed packs
would require installer/lock composition and asset-mount changes. This spike
does not change that trust model or the default pinned tool bundle.

## Reproduce the measurements

Use `uv`, Wasmtime 51.0.0, wasm-tools 1.263.0, and DejaVu Sans (the corpus
manifest records the exact font hash). The pinned Pillow generator uses no
private input data.

```sh
uv run mcpone/corpus.py /path/to/corpus
uv run mcpone/benchmark.py \
  --build /path/to/build-output --models /path/to/models \
  --corpus /path/to/corpus --wasmtime /path/to/wasmtime \
  --wasm-mode wasip2-simd --out /path/to/results --repeats 3
uv run mcpone/package.py \
  --build /path/to/build-output --models /path/to/models \
  --mode wasip2-simd --wasm-tools /path/to/wasm-tools --out /path/to/packages
uv run mcpone/summarize.py /path/to/results/results.json
uv run mcpone/startup.py --wasmtime /path/to/wasmtime \
  --wasm /path/to/packages/tesseract-wasip2-simd.wasm --out /path/to/startup.json
```

For a paired compiler comparison on Linux, use `mcpone/compiler-compare.py`
with `--build`, `--models`, `--corpus`, `--wasmtime`, `--cpu` and `--out`.
It pins both variants to one selected CPU and alternates their run order.

The helper separates model initialization, image decode, and recognition.
The Python driver measures process wall time and individual child peak RSS
with `wait4`; WASI also reports the instance's linear-memory high-water mark.
It compares native and WASI with fast/best data, PSM 3/6, and disabled system/
frequency dictionaries for identifiers. CER and WER use NFC Unicode with
collapsed whitespace. Blank false positives are counted separately. Raw output
text and all repeat measurements are retained in `results.json`/`runs.jsonl`.
The full corpus includes two A4-sized pages at 300 DPI.

The benchmark uses locally precompiled, trusted Wasmtime artifacts to separate
JIT compilation from execution. Those host-specific `.cwasm` files are not part
of the distribution. Fresh-process startup is measured separately; the OS file
cache is not flushed. Measurements on a shared machine are indicative, not an
isolated performance guarantee. The synthetic corpus is too small to rank OCR
engines in general or establish real-document accuracy.

See the MonoCP spike report linked from the release for measured results,
alternatives, toolchain experiments and the final recommendation. The release
includes checksummed executable/model archives, dependency notices and raw
measurements. No training, GUI, network client, or native OCR service is needed
at runtime.
