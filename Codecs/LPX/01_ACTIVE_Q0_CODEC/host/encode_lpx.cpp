// Binary-safe, Python-free native entry point for the shared LPX encoder.
#include "LpxEncoder.h"
#include "LpxAdaptiveController.h"
#include "LpxHostWorkspace.h"
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cerrno>
#include <climits>
#include <exception>
#include <algorithm>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

#ifndef LPX_ENCODER_ENABLE_CUDA
#define LPX_ENCODER_ENABLE_CUDA 0
#endif
#if LPX_ENCODER_ENABLE_CUDA
extern "C" int enc_set_backend(int backend);
extern "C" const char* enc_backend_error(void);
#endif

namespace {
using Clock = std::chrono::steady_clock;
struct Options {
    int profile = 6, rate = 8000, calls = 4, maxBytes = 0, repeat = 1, sizeAllowance = 0;
    bool cuda = false, adaptive = true, autoQuiet = false, speech = true, expandedSearch = true, normalize = false;
    int targetLufs = -18, maxGainDb = 12;
};
void jsonString(FILE* out, const char* value) {
    fputc('"', out);
    for (const unsigned char* p = reinterpret_cast<const unsigned char*>(value); *p; ++p) {
        if (*p == '"' || *p == '\\') fputc('\\', out);
        if (*p < 32) fprintf(out, "\\u%04x", unsigned(*p)); else fputc(*p, out);
    }
    fputc('"', out);
}
int fail(const char* message, int code = 2) {
    fputs("{\"error\":", stderr); jsonString(stderr, message); fputs("}\n", stderr);
    return code;
}
bool integer(const char* value, int& number) {
    if (!value || !*value) return false;
    for (const char* p = value; *p; ++p) if (*p < '0' || *p > '9') return false;
    errno = 0; char* end = nullptr; long parsed = strtol(value, &end, 10);
    if (errno || *end || parsed > INT_MAX) return false;
    number = int(parsed); return true;
}
int run(int argc, char** argv) {
    Options options;
    for (int i = 1; i < argc; ++i) {
        const char* name = argv[i];
        if (!strcmp(name, "--help")) {
            puts("Usage: lpx-encode [--profile 4|6] [--rate 8000|12000|16000]"
                 " [--backend cpu|cuda] [--quality fast|adaptive] [--calls 0..4]"
                 " [--search expanded|reference] [--size-allowance 0..100]"
                 " [--max-bytes N] [--repeat 1..20] [--auto-quiet] [--non-speech]"
                 " [--normalize] [--target-lufs -30..-9] [--max-gain-db 0..24]\n"
                 "Input: mono PCM16 little-endian on stdin, 1..32000000 samples.\n"
                 "Output: one verified LPX V9/Long file on stdout; JSON diagnostics on stderr.\n"
                 "Use encode-lpx-native.mjs for binary-safe file conversion on Windows.");
            return 0;
        }
        if (!strcmp(name, "--auto-quiet")) { options.autoQuiet = true; continue; }
        if (!strcmp(name, "--normalize")) { options.normalize = true; continue; }
        if (!strcmp(name, "--non-speech")) { options.speech = false; continue; }
        if (i + 1 >= argc) return fail("Missing option value");
        const char* value = argv[++i];
        if (!strcmp(name, "--backend")) {
            if (strcmp(value, "cpu") && strcmp(value, "cuda")) return fail("Backend must be cpu or cuda");
            options.cuda = !strcmp(value, "cuda");
        } else if (!strcmp(name, "--quality")) {
            if (strcmp(value, "fast") && strcmp(value, "adaptive")) return fail("Quality must be fast or adaptive");
            options.adaptive = !strcmp(value, "adaptive");
        } else if (!strcmp(name, "--search")) {
            if (strcmp(value, "expanded") && strcmp(value, "reference")) return fail("Search must be expanded or reference");
            options.expandedSearch = !strcmp(value, "expanded");
        } else if (!strcmp(name, "--target-lufs")) {
            errno=0;char* end=nullptr;long level=strtol(value,&end,10);
            if(errno || !*value || *end || level<-30 || level>-9)return fail("Target loudness must be -30..-9 LUFS");
            options.targetLufs=int(level);
        } else {
            int number;
            if (!integer(value, number)) return fail("Expected a nonnegative integer option value");
            if (!strcmp(name, "--profile")) options.profile = number;
            else if (!strcmp(name, "--rate")) options.rate = number;
            else if (!strcmp(name, "--calls")) options.calls = number;
            else if (!strcmp(name, "--max-bytes")) options.maxBytes = number;
            else if (!strcmp(name, "--repeat")) options.repeat = number;
            else if (!strcmp(name, "--size-allowance")) options.sizeAllowance = number;
            else if (!strcmp(name, "--max-gain-db")) options.maxGainDb = number;
            else return fail("Unknown encoder option");
        }
    }
    if (options.profile != 4 && options.profile != 6) return fail("Profile must be 4 or 6");
    if (options.rate != 8000 && options.rate != 12000 && options.rate != 16000) return fail("Unsupported sample rate");
    if (options.calls < 0 || options.calls > 4) return fail("Refinement calls must be in 0..4");
    if(options.maxGainDb<0 || options.maxGainDb>24)return fail("Maximum gain must be 0..24 dB");
    if(options.normalize && options.autoQuiet)return fail("Select one input-level policy: normalization or auto quiet");
    if (options.repeat < 1 || options.repeat > 20) return fail("Repeat count must be in 1..20");
    if (options.sizeAllowance < 0 || options.sizeAllowance > 100) return fail("Size allowance must be in 0..100 percent");
    if (options.maxBytes && (options.maxBytes < 22 || options.maxBytes > int(kLpxMaxFileBytes))) return fail("Complete byte budget must be 22..104857600, or 0 for the control size");
    if (!options.adaptive && (options.autoQuiet || options.maxBytes || options.calls != 4 || !options.speech || !options.expandedSearch || options.sizeAllowance)) return fail("Adaptive search options require --quality adaptive");
#ifdef _WIN32
    if (_setmode(_fileno(stdin), _O_BINARY) == -1 || _setmode(_fileno(stdout), _O_BINARY) == -1) return fail("Cannot open binary standard streams", 3);
#endif
    const auto initialization = Clock::now();
#if LPX_ENCODER_ENABLE_CUDA
    if (enc_set_backend(options.cuda ? 1 : 0) < 0) return fail(enc_backend_error(), 4);
#else
    if (options.cuda) return fail("This executable was built without CUDA; select cpu or build the CUDA executable", 4);
#endif
    const double initializationMs = std::chrono::duration<double, std::milli>(Clock::now() - initialization).count();
    lpx::Pcm pcm; unsigned char input[65536]; int low = -1;
    for (;;) {
        const size_t count = fread(input, 1, sizeof(input), stdin);
        for (size_t i = 0; i < count; ++i) {
            if (low < 0) low = input[i];
            else {
                if (pcm.size() >= kLpxMaxSamples) return fail("PCM exceeds the 32000000-sample limit", 5);
                const unsigned value = unsigned(low) | (unsigned(input[i]) << 8);
                pcm.push_back(int16_t(value < 32768 ? int(value) : int(value) - 65536)); low = -1;
            }
        }
        if (count < sizeof(input)) { if (ferror(stdin)) return fail("Cannot read input PCM", 5); if (feof(stdin)) break; }
    }
    if (low >= 0) return fail("PCM16 input has an odd byte count", 5);
    if (pcm.empty()) return fail("PCM input is empty", 5);
    std::vector<uint8_t> bytes; lpx::AdaptiveReport report; std::vector<double> timings;
    for (int repetition = 0; repetition < options.repeat; ++repetition) {
      const auto started = Clock::now();
      lpx::Pcm prepared;
      lpx::LoudnessReport level;
      if(options.normalize) { prepared=pcm;level=lpx::normalizeLoudness(prepared,options.rate,options.targetLufs,options.maxGainDb); }
      const auto& reference=options.normalize?prepared:pcm;
      if (!enc_reserve(uint32_t(pcm.size()))) return fail("Cannot reserve encoder memory", 6);
      std::vector<uint8_t> current;
      if (options.adaptive) {
        auto stream = lpx::adaptiveEncode(reference, options.profile, options.rate, report,
            options.autoQuiet, options.maxBytes, options.calls, options.speech, options.expandedSearch, options.sizeAllowance);
        if (report.error || stream.samples != int(pcm.size())) return fail("Adaptive encoding or complete-size admission failed", 7);
        auto expected = lpx::render(stream);
        if (!lpx::verifyStream(stream, expected)) return fail("Adaptive output failed native decoder verification", 7);
        current = lpx::packV9(stream);
      } else {
        memcpy(enc_input(), reference.data(), reference.size() * sizeof(int16_t));
        const int blocks = enc_begin(int(pcm.size()), options.profile, options.rate);
        if (blocks < 1) return fail("Cannot begin encoding", 7);
        for (int i = 0; i < blocks; ++i) if (enc_step() < 0) return fail("Encoding backend failed", 7);
        const int size = enc_finish();
        if (size < 13) return fail("Output failed native decoder verification", 7);
        current.assign(enc_output(), enc_output() + size);
      }
      if(options.normalize)report.loudness=level;
      timings.push_back(std::chrono::duration<double, std::milli>(Clock::now() - started).count());
      if (!repetition) bytes = std::move(current);
      else if (current != bytes) return fail("Repeated encoding changed the LPX output", 7);
    }
    // No output byte is emitted until encoding and complete-stream verification
    // succeed. The file wrapper also waits for process success before writing.
    if (fwrite(bytes.data(), 1, bytes.size(), stdout) != bytes.size() || fflush(stdout)) return fail("Cannot write LPX output", 8);
    fprintf(stderr, "{\"schema\":\"lpx-native-encode-v1\",\"backend\":\"%s\",\"quality\":\"%s\",\"search\":\"%s\",\"sizeAllowancePercent\":%d,\"expandedAccepted\":%d,\"samples\":%u,\"sampleRate\":%d,\"profile\":%d,\"bytes\":%u,\"long\":%s,\"backendInitializationMs\":%.6f,\"encodingMs\":%.6f,\"candidates\":%d,\"refinementCalls\":%d,\"gainPower2Exponent\":%d,\"repeatTimesMs\":[",
        options.cuda ? "cuda" : "cpu", options.adaptive ? "adaptive" : "fast",
        options.adaptive ? (options.expandedSearch ? "expanded" : "reference") : "fast",
        options.adaptive ? options.sizeAllowance : 0, report.expandedAccepted,
        unsigned(pcm.size()), options.rate, options.profile, unsigned(bytes.size()),
        bytes[2] & 64 ? "true" : "false", initializationMs, timings[0], report.candidates, report.stages, report.gainExponent);
    for (size_t i = 0; i < timings.size(); ++i) fprintf(stderr, "%s%.6f", i ? "," : "", timings[i]);
    fputs("],\"warmMedianMs\":", stderr);
    if (timings.size() > 1) {
        std::vector<double> warm(timings.begin() + 1, timings.end()); std::sort(warm.begin(), warm.end());
        fprintf(stderr, "%.6f", (warm[(warm.size() - 1) / 2] + warm[warm.size() / 2]) / 2);
    } else fputs("null", stderr);
    fprintf(stderr,",\"normalized\":%s,\"inputGainDb\":%.6f}",options.normalize?"true":"false",report.loudness.gainDb);fputc('\n',stderr);
    return 0;
}
}
int main(int argc, char** argv) {
    try { return run(argc, argv); }
    catch (const std::exception&) { return fail("Allocation or encoding failed", 9); }
    catch (...) { return fail("Unexpected encoder failure", 9); }
}
