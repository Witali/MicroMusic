// Bounded packing gate. Uses the existing audited V9/native/quality adapter;
// no new decoder or wire format is implemented here.
#define main existing_probe_main
#include "../../research/lbg1-2026-11-26/probe.cpp"
#undef main
#include <cmath>

int main(int argc,char** argv){try{
    if(argc!=4)throw std::runtime_error("Usage: gate_probe BASELINE_V9 CANDIDATE_V9 SOURCE_PCM");
    auto originalBytes=bytes(argv[1]),candidateBytes=bytes(argv[2]);
    auto original=native(originalBytes),candidate=native(candidateBytes);
    auto before=unpack(originalBytes),after=unpack(candidateBytes);validateSpectra(before);validateSpectra(after);
    auto reference=pcm(argv[3]);
    if(reference.size()!=original.size()||candidate.size()!=reference.size()||before.samples!=after.samples||before.profile!=after.profile
       ||before.pre!=after.pre||before.bright!=after.bright||before.parameters!=after.parameters||before.pulses!=after.pulses||before.extras!=after.extras)
        throw std::runtime_error("One-bin gate requires unchanged complete non-spectral parameters");
    int maximum=0,changed=0;
    for(size_t i=0;i<before.spectra.size();i++)for(int j=0;j<10;j++){
        int error=std::abs(before.spectra[i][j]-after.spectra[i][j]);maximum=std::max(maximum,error);changed+=error!=0;
    }
    if(maximum>1)throw std::runtime_error("Candidate exceeds one-bin source error");
    if(render(before)!=original||render(after)!=candidate)throw std::runtime_error("Independent/native model mismatch");
    QualityContext q(reference);auto a=q.quality(candidate),b=q.quality(original);
    FullBandContext f(reference,8000);auto af=f.measure(candidate),bf=f.measure(original);
    bool full=f.accepts(af,bf),stable=stableLpcStream(after),level=safeSynthesisLevel(after,reference,candidate),spectrum=safeSynthesisSpectrum(reference,candidate);
    unsigned reasons=0;if(a.error[0]>b.error[0])reasons|=1;if(a.error[1]>b.error[1])reasons|=2;
    if(!std::isfinite(a.stoi[0])||!std::isfinite(b.stoi[0])||a.stoi[0]+1e-12<b.stoi[0])reasons|=4;
    if(!std::isfinite(a.stoi[1])||!std::isfinite(b.stoi[1])||a.stoi[1]+1e-12<b.stoi[1])reasons|=8;
    if(!full)reasons|=16;if(!level)reasons|=32;if(!spectrum)reasons|=64;if(!stable)reasons|=128;
    std::cout.precision(12);std::cout<<"{\"quality_admitted\":"<<(!reasons?"true":"false")<<",\"rejection_bits\":"<<reasons
      <<",\"maximum_lsf_bin_error\":"<<maximum<<",\"changed_lsf_indices\":"<<changed
      <<",\"unchanged_other_parameters\":true,\"native_model_exact\":true,\"stable_interpolated_filters\":"<<(stable?"true":"false")
      <<",\"level_safe\":"<<(level?"true":"false")<<",\"spectrum_safe\":"<<(spectrum?"true":"false")<<",\"fullband_admitted\":"<<(full?"true":"false")
      <<",\"pcm_sse\":"<<a.error[0]<<",\"pwm_sse\":"<<a.error[1]<<",\"pcm_stoi\":"<<a.stoi[0]<<",\"pwm_stoi\":"<<a.stoi[1]
      <<",\"baseline_pcm_sse\":"<<b.error[0]<<",\"baseline_pwm_sse\":"<<b.error[1]<<",\"baseline_pcm_stoi\":"<<b.stoi[0]<<",\"baseline_pwm_stoi\":"<<b.stoi[1]
      <<",\"spectral_error\":"<<af.balancedError[0]<<",\"temporal_error\":"<<af.balancedTemporalError[0]
      <<",\"baseline_spectral_error\":"<<bf.balancedError[0]<<",\"baseline_temporal_error\":"<<bf.balancedTemporalError[0]<<"}\n";return 0;
}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}}
