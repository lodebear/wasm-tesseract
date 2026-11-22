// Measurement helper only: the shipped OCR interface is the upstream CLI.
#include <tesseract/baseapi.h>
#include <allheaders.h>
#include <chrono>
#include <cstdio>
#include <memory>
#include <string>
#include <vector>

using Clock = std::chrono::steady_clock;
static double ms(Clock::time_point from, Clock::time_point to) {
  return std::chrono::duration<double, std::milli>(to - from).count();
}

int main(int argc, char **argv) {
  if (argc != 6) {
    std::fprintf(stderr, "usage: ocr-bench tessdata lang psm no-dawg image\n");
    return 2;
  }
  const auto start = Clock::now();
  tesseract::TessBaseAPI api;
  std::vector<std::string> names, values;
  if (std::string(argv[4]) == "1") {
    names = {"load_system_dawg", "load_freq_dawg"};
    values = {"0", "0"};
  }
  if (api.Init(argv[1], argv[2], tesseract::OEM_LSTM_ONLY,
               nullptr, 0, &names, &values, false) != 0) return 1;
  api.SetPageSegMode(static_cast<tesseract::PageSegMode>(std::stoi(argv[3])));
  const auto initialized = Clock::now();
  Pix *image = pixRead(argv[5]);
  if (!image) return 1;
  api.SetImage(image);
  api.SetSourceResolution(300);
  const auto loaded = Clock::now();
  if (api.Recognize(nullptr) != 0) {
    pixDestroy(&image);
    return 1;
  }
  std::unique_ptr<char[]> text(api.GetUTF8Text());
  const auto done = Clock::now();
  unsigned long long memory = 0;
#ifdef __wasm__
  // Linear memory grows monotonically, so this is the instance high-water mark.
  memory = static_cast<unsigned long long>(__builtin_wasm_memory_size(0)) * 65536;
#endif
  std::printf("{\"init_ms\":%.3f,\"read_ms\":%.3f,\"recognize_ms\":%.3f,"
              "\"total_ms\":%.3f,\"linear_memory_bytes\":%llu,\"confidence\":%d,\"text_hex\":\"",
              ms(start, initialized), ms(initialized, loaded), ms(loaded, done),
              ms(start, done), memory, api.MeanTextConf());
  if (text) for (const unsigned char *c = reinterpret_cast<unsigned char *>(text.get()); *c; ++c)
    std::printf("%02x", *c);
  std::puts("\"}");
  pixDestroy(&image);
  return 0;
}
