// Direct visitor API contracts. No files, corpus identities or logging hooks.
#include "LpxBitrateProfiles.h"
#include "LpxAdaptiveController.h"
#include "LpxEncoder.h"
#include <cmath>
#include <cstdio>
#include <cstdlib>

#ifdef LPX_THREE_K_VISITOR_LEGACY_ORACLE
// The private regression build supplies the unchanged ba02e453 implementation,
// with only its external function name renamed to avoid a duplicate symbol.
namespace lpx {
Stream encodeThreeKLegacy(const Pcm&, int, BitrateReport&, double, const Stream*);
}
#endif
namespace {
int checks = 0, rejectedCandidates = 0;
void require(bool condition, const char* message) {
    if (!condition) { std::fprintf(stderr, "FAIL: %s\n", message); std::exit(1); }
}
bool sameReport(const lpx::BitrateReport& a, const lpx::BitrateReport& b) {
    return a.candidates == b.candidates && a.selected == b.selected && a.error == b.error
        && a.parameterTrials == b.parameterTrials && a.pulseTrials == b.pulseTrials;
}
std::vector<uint8_t> bytes(const lpx::Stream& s) {
    return s.samples ? lpx::packV9(s) : std::vector<uint8_t>{};
}
lpx::Pcm signal(int count) {
    lpx::Pcm pcm(count); unsigned random = 17;
    for (int i = 0; i < count; ++i) {
        random = random * 1664525u + 1013904223u;
        const double t = double(i) / 8000;
        const double envelope = .6 + .3 * std::sin(2 * 3.14159265358979323846 * 5 * t);
        pcm[i] = int16_t(std::nearbyint(envelope * (4000 * std::sin(2 * 3.14159265358979323846 * 219 * t)
            + 1600 * std::sin(2 * 3.14159265358979323846 * 1533 * t)) + int(random >> 24) - 128));
    }
    return pcm;
}
struct Visits {
    Visits(const lpx::Pcm& reference, int budget) : context(reference), cap(budget) {}
    lpx::QualityContext context;
    int cap, rejected = 0;
    bool valid = true;
    lpx::Measurement baseline;
    std::vector<std::vector<uint8_t>> packets;
};
void visit(const lpx::Stream& stream, const lpx::Pcm& pcm, void* opaque) {
    auto& state = *static_cast<Visits*>(opaque);
    auto packed = lpx::packV9(stream);
    state.valid &= packed.size() <= size_t(state.cap) && pcm.size() == size_t(stream.samples)
        && stream.profile == 4 && stream.rate == 8000
        && lpx::render(stream) == pcm && lpx::verifyStream(stream, pcm);
    const auto measurement = state.context.measure(pcm);
    if (state.packets.empty()) state.baseline = measurement;
    else if (!lpx::noRegression(measurement.quality, state.baseline.quality)) ++state.rejected;
    state.packets.push_back(std::move(packed));
}
lpx::Stream check(const lpx::Pcm& reference, int cap, double bandwidth = .97,
                  const lpx::Stream* incumbent = nullptr, bool explicitNull = false) {
    require(enc_reserve(reference.size()), "workspace reservation failed");
    const auto savedIncumbent = incumbent ? bytes(*incumbent) : std::vector<uint8_t>{};
    lpx::BitrateReport baselineReport, visitedReport;
    const auto baseline = lpx::encodeThreeK(reference, cap, baselineReport, bandwidth, incumbent);
    Visits visits(reference, cap);
    const auto selected = lpx::encodeThreeK(reference, cap, visitedReport, bandwidth, incumbent, visit, &visits);
    require(bytes(selected) == bytes(baseline) && sameReport(visitedReport, baselineReport),
        "visitor changed the selected output or legacy report");
    require(visits.valid && visits.packets.size() == size_t(visitedReport.candidates),
        "visitor did not receive every verified complete candidate");
    require(visits.packets.size() <= size_t(lpx::kThreeKMaxCandidateVisits), "candidate bound exceeded");
    if (incumbent && !visitedReport.error) {
        require(!visits.packets.empty() && visits.packets.front() == savedIncumbent,
            "optional incumbent was not visited first");
        require(bytes(*incumbent) == savedIncumbent, "protected incumbent was mutated");
    }
    if (explicitNull) {
        lpx::BitrateReport nullReport;
        const auto nullSelected = lpx::encodeThreeK(reference, cap, nullReport,
            bandwidth, incumbent, nullptr, &visits);
        require(bytes(nullSelected) == bytes(baseline) && sameReport(nullReport, baselineReport),
            "explicit null changed legacy behavior");
        Visits repeated(reference, cap); lpx::BitrateReport repeatedReport;
        lpx::encodeThreeK(reference, cap, repeatedReport, bandwidth, incumbent, visit, &repeated);
        require(repeated.packets == visits.packets && sameReport(repeatedReport, visitedReport),
            "candidate visitor order or duplicate sequence changed");
    }
#ifdef LPX_THREE_K_VISITOR_LEGACY_ORACLE
    lpx::BitrateReport oldReport;
    const auto old = lpx::encodeThreeKLegacy(reference, cap, oldReport, bandwidth, incumbent);
    require(bytes(old) == bytes(baseline) && sameReport(oldReport, baselineReport),
        "default null differs from the frozen original implementation");
#endif
    rejectedCandidates += visits.rejected;
    ++checks; return selected;
}
void invalid(const lpx::Pcm& reference, int cap, double bandwidth, int expectedError) {
    Visits visits(reference, cap); lpx::BitrateReport report;
    const auto selected = lpx::encodeThreeK(reference, cap, report, bandwidth, nullptr, visit, &visits);
    require(!selected.samples && report.error == expectedError && visits.packets.empty(),
        "invalid/no-fit input exposed a candidate or changed its error");
    lpx::BitrateReport nullReport;
    const auto nullSelected = lpx::encodeThreeK(reference, cap, nullReport, bandwidth);
    require(bytes(nullSelected) == bytes(selected) && sameReport(nullReport, report),
        "visitor changed invalid/no-fit default behavior");
#ifdef LPX_THREE_K_VISITOR_LEGACY_ORACLE
    lpx::BitrateReport oldReport;
    const auto old = lpx::encodeThreeKLegacy(reference, cap, oldReport, bandwidth, nullptr);
    require(bytes(old) == bytes(selected) && sameReport(oldReport, report),
        "invalid/no-fit behavior differs from the frozen original");
#endif
    ++checks;
}
}
int main() {
    check(signal(1), 80, .97, nullptr, true);
    check(signal(161), 80, .99);
    // The strict cap forces the existing bounded zero-gain fallback at this
    // short length when the seed does not already fit its omitted lag fields.
    check(signal(3201), 3201 * 3 / 64, .94);
    const auto reference = signal(6401);
    const auto incumbent = check(reference, 6401 * 3 / 64);
    require(incumbent.samples == int(reference.size()), "active fixture found no fit");
    check(reference, 6401 * 3 / 64, .99, &incumbent);
    check(lpx::Pcm(64001), 64001 * 3 / 64);
    require(rejectedCandidates > 0, "visitor did not expose any candidate before legacy rejection");
    require(enc_reserve(641), "error workspace reservation failed");
    invalid({}, 80, .97, -1);
    invalid(signal(641), 12, .97, -1);
    invalid(signal(641), 13, .97, -6);
    invalid(signal(641), 80, 0, -1);
    require(!enc_reserve(0), "invalid reserve succeeded");
    invalid(signal(641), 80, .97, -1);
    std::printf("PASS: %d strict-3k visitor contracts; %d pre-filter candidates exposed despite legacy waveform rejection.\n",
        checks, rejectedCandidates);
}
