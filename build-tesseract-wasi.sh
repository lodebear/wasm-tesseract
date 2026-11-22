#!/usr/bin/env bash
# Build the same small OCR runtime natively or as a WASI Preview2 component.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:-wasip2}"
WORK="${TESSERACT_BUILD_ROOT:-$ROOT/build-ocr}"
JOBS="${JOBS:-8}"
case "$MODE" in wasip2|wasip2-simd|native) ;; *) echo 'usage: build-tesseract-wasi.sh [wasip2|wasip2-simd|native]' >&2; exit 2;; esac
mkdir -p "$WORK/downloads" "$WORK/src" "$WORK/$MODE"
WORK="$(cd "$WORK" && pwd)"
PREFIX="$WORK/$MODE/install"

digest_file() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1"; else shasum -a 256 "$1"; fi
}
fetch() {
  local name="$1" url="$2" digest="$3"
  if [ ! -f "$WORK/downloads/$name.tar.gz" ]; then
    curl -fLsS --retry 3 "$url" -o "$WORK/downloads/$name.tar.gz.part"
    mv "$WORK/downloads/$name.tar.gz.part" "$WORK/downloads/$name.tar.gz"
  fi
  local actual
  actual="$(digest_file "$WORK/downloads/$name.tar.gz" | cut -d' ' -f1)"
  [ "$actual" = "$digest" ] || { echo "checksum mismatch: $name" >&2; exit 1; }
  if [ ! -d "$WORK/src/$name" ]; then
    mkdir -p "$WORK/src/$name"
    tar -xzf "$WORK/downloads/$name.tar.gz" --strip-components=1 -C "$WORK/src/$name"
    if [ "$name" = leptonica ]; then
      patch -d "$WORK/src/leptonica" -p1 < "$ROOT/mcpone/leptonica-wasi.patch"
    fi
  fi
}
fetch zlib https://github.com/madler/zlib/archive/refs/tags/v1.3.1.tar.gz 17e88863f3600672ab49182f217281b6fc4d3c762bde361935e436a95214d05c
fetch libpng https://github.com/pnggroup/libpng/archive/refs/tags/v1.6.50.tar.gz 71158e53cfdf2877bc99bcab33641d78df3f48e6e0daad030afe9cb8c031aa46
fetch jpeg https://github.com/libjpeg-turbo/libjpeg-turbo/archive/refs/tags/3.2.1.tar.gz 6f5819c51649bce2571a23b1b0cd41eae2f57fc3f8908c7ec9e7047efb65ca13
fetch leptonica https://github.com/DanBloomberg/leptonica/archive/refs/tags/1.87.0.tar.gz fa2b40c5caea96d1bb93a97486262aed8731b69ce25a84a6bf5d25323e33f631

COMMON=(-DCMAKE_BUILD_TYPE=Release -DCMAKE_C_FLAGS_RELEASE="-O2 -DNDEBUG" -DCMAKE_CXX_FLAGS_RELEASE="-O2 -DNDEBUG" -DPACKAGE_VERSION=5.5.4 -DBUILD_SHARED_LIBS=OFF -DCMAKE_INSTALL_PREFIX="$PREFIX" -DCMAKE_PREFIX_PATH="$PREFIX")
CFLAGS="-O2 -ffile-prefix-map=$ROOT=/src/tesseract -ffile-prefix-map=$WORK=/build/ocr"
CXXFLAGS="$CFLAGS"
LINKFLAGS=""
if [ "$MODE" != native ]; then
  : "${WASI_SDK_PATH:?Set WASI_SDK_PATH to wasi-sdk 33.0}"
  SDK_VERSION="$(head -n 1 "$WASI_SDK_PATH/VERSION")"
  [[ "$SDK_VERSION" = 33.0* ]] || { echo 'This MonoCP build requires wasi-sdk 33.0 (WASI 0.2.6 imports).' >&2; exit 1; }
  COMMON+=(-DCMAKE_TOOLCHAIN_FILE="$WASI_SDK_PATH/share/cmake/wasi-sdk-p2.cmake" -DCMAKE_FIND_ROOT_PATH="$PREFIX;$WASI_SDK_PATH/share/wasi-sysroot")
  CFLAGS+=" -mllvm -wasm-enable-sjlj -mllvm -wasm-use-legacy-eh=false -D_WASI_EMULATED_SIGNAL -D_WASI_EMULATED_PROCESS_CLOCKS"
  if [ "$MODE" = wasip2-simd ]; then CFLAGS+=" -msimd128"; fi
  CXXFLAGS="$CFLAGS -fwasm-exceptions"
  LINKFLAGS="-fwasm-exceptions -lunwind -lsetjmp -lwasi-emulated-signal -lwasi-emulated-process-clocks -Wl,-z,stack-size=8388608 -Wl,--max-memory=1073741824"
fi
CXXFLAGS+=" -DTESSERACT_DISABLE_DEBUG_FONTS"
COMMON+=(-DCMAKE_C_FLAGS="$CFLAGS" -DCMAKE_CXX_FLAGS="$CXXFLAGS" -DCMAKE_EXE_LINKER_FLAGS="$LINKFLAGS")
# Do not let pkg-config leak native dependencies into a WASI link.
export PKG_CONFIG_LIBDIR="$PREFIX/lib/pkgconfig"
unset PKG_CONFIG_PATH
build_dep() {
  local name="$1"; shift
  cmake -S "$WORK/src/$name" -B "$WORK/$MODE/$name" "${COMMON[@]}" "$@"
  cmake --build "$WORK/$MODE/$name" -j "$JOBS"
  cmake --install "$WORK/$MODE/$name"
}
build_dep zlib -DZLIB_BUILD_EXAMPLES=OFF
if [ "$MODE" != native ]; then
  COMMON+=(-DZLIB_LIBRARY="$PREFIX/lib/libzlibstatic.a")
else
  COMMON+=(-DZLIB_USE_STATIC_LIBS=ON -DZLIB_LIBRARY="$PREFIX/lib/libz.a")
fi
build_dep libpng -DPNG_SHARED=OFF -DPNG_TESTS=OFF -DPNG_TOOLS=OFF -DPNG_EXECUTABLES=OFF -DPNG_HARDWARE_OPTIMIZATIONS=OFF
build_dep jpeg -DENABLE_SHARED=OFF -DENABLE_STATIC=ON -DWITH_SIMD=OFF -DWITH_TURBOJPEG=OFF -DWITH_TOOLS=OFF -DWITH_TESTS=OFF
build_dep leptonica -DBUILD_PROG=OFF -DENABLE_GIF=OFF -DENABLE_TIFF=OFF -DENABLE_WEBP=OFF -DENABLE_OPENJPEG=OFF -DSTRICT_CONF=ON
cmake -S "$ROOT" -B "$WORK/$MODE/tesseract" "${COMMON[@]}" \
  -DBUILD_TRAINING_TOOLS=OFF -DBUILD_TESTS=OFF -DGRAPHICS_DISABLED=ON \
  -DDISABLED_LEGACY_ENGINE=ON -DOPENMP_BUILD=OFF -DENABLE_LTO=OFF \
  -DDISABLE_CURL=ON -DDISABLE_ARCHIVE=ON -DDISABLE_TIFF=ON \
  -DENABLE_PRECOMPILED_HEADERS=OFF -DENABLE_CCACHE=OFF -DFAST_FLOAT=ON -DBUILD_OCR_BENCH=ON
cmake --build "$WORK/$MODE/tesseract" --target tesseract ocr-bench -j "$JOBS"
mkdir -p "$WORK/$MODE/out"
if [ "$MODE" != native ]; then
  BIN="$WORK/$MODE/tesseract/bin/tesseract"
  [ ! -f "$BIN.wasm" ] || BIN="$BIN.wasm"
  cp "$BIN" "$WORK/$MODE/out/tesseract.wasm"
  BENCH="$WORK/$MODE/tesseract/bin/ocr-bench"
  [ ! -f "$BENCH.wasm" ] || BENCH="$BENCH.wasm"
  cp "$BENCH" "$WORK/$MODE/out/ocr-bench.wasm"
else
  cp "$WORK/$MODE/tesseract/bin/tesseract" "$WORK/$MODE/out/tesseract"
  cp "$WORK/$MODE/tesseract/bin/ocr-bench" "$WORK/$MODE/out/ocr-bench"
fi
echo "Built $WORK/$MODE/out"
