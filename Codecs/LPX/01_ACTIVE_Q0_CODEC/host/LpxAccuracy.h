#pragma once
#include "LpxAdaptiveController.h"

// Explicit zero reproduces the previous encoder. This experimental phase also
// requires the existing quality and joint-search switches; decoder unaffected.
#ifndef LPX_ENCODER_COMPACT_ENSEMBLE
#define LPX_ENCODER_COMPACT_ENSEMBLE 1
#endif

namespace lpx{
struct BitrateReport;
enum CompactEnsembleStatus {
    CompactDisabled=0,CompactIneligible=1,CompactUnchanged=2,
    CompactRejected=3,CompactSelected=4,CompactSearchFailure=-1,
    CompactInvalidIncumbent=-2,CompactRelabelMismatch=-3,
    CompactInvalidCandidate=-4,CompactOverBudget=-5,
    CompactNativeMismatch=-6,CompactUnsafeCandidate=-7,
    CompactSelectionFailure=-8
};
bool compactEnsembleEnabled();
bool compactEnsembleEligible(const Stream& completed,int calls,const Stream* prefix=nullptr);
// Selection of an already generated result. Provides forced-error/malformed
// result tests without invoking a seed search. The original remains immutable.
Stream selectCompactEnsembleCandidate(const Stream& completed,const Pcm& reference,
    const Stream& proposal,const BitrateReport& search,CompactEnsembleReport& report,
    CandidateEvaluation* evaluation=nullptr);
// Exactly one existing fine-grid search at completed's actual V9 size, followed
// by the unchanged production selector. rawProposal retains only a well-formed
// native-exact proposal, even if its safety/quality admission subsequently fails.
// Capture is cleared on entry, and must not alias the immutable input stream.
Stream refineCompactEnsemble(const Stream& completed,const Pcm& reference,
    CompactEnsembleReport& report,CandidateEvaluation* evaluation=nullptr,
    Stream* rawProposal=nullptr);
struct AccuracyPolicy{int level=0,wireProfile=0,detailBitsPerFrame=0;bool corrections=false;};
AccuracyPolicy accuracyPolicy(int level);
int accuracyPacketBound(int samples,int level);
int accuracyBudget(int samples,int level,int originalBytes);
Stream refineAccuracyCorrections(const Stream& input,const Pcm& reference,int completeV9Budget);
// Optional capture is cleared on entry; it may not alias prefix. Skipped or
// invalid phases leave it empty, never a proposal from an earlier call.
Stream encodeAccuracy(const Pcm& reference,int level,int rate,AdaptiveReport& report,
                      int calls=4,const Stream* prefix=nullptr,QualityTarget target=QualityTarget::Pwm,
                      Stream* compactRawProposal=nullptr);
}
