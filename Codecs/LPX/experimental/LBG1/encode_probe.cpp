// File adapter for actual LG streams; writes nothing until decoder/reference
// comparison succeeds. Source/model audio are local public experiment inputs.
#include "encoder.h"
#include "decoder.h"
#include "LpxQuality.h"
#include "LpxFullBand.h"
#include "Lpx4HybridCore.h"
#include <fstream>
#include <iterator>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <cmath>

namespace {
std::vector<uint8_t> read(const std::string& path){std::ifstream f(path,std::ios::binary);if(!f)throw std::runtime_error("Cannot read input");return {std::istreambuf_iterator<char>(f),{}};}
lpx::Pcm pcm(const std::string& path){auto b=read(path);if(b.size()%2)throw std::runtime_error("Odd PCM length");lpx::Pcm out;for(size_t i=0;i<b.size();i+=2)out.push_back(int16_t(b[i]|(uint16_t(b[i+1])<<8)));return out;}
void save(const std::string& path,const std::vector<uint8_t>& b){
    std::ifstream existing(path,std::ios::binary);
    if(existing){std::vector<uint8_t> previous{std::istreambuf_iterator<char>(existing),{}};if(previous==b)return;throw std::runtime_error("Refusing to overwrite a different frozen experiment artifact");}
    std::ofstream f(path,std::ios::binary);f.write(reinterpret_cast<const char*>(b.data()),b.size());if(!f)throw std::runtime_error("Cannot write output");
}
void savePcm(const std::string& path,const lpx::Pcm& p){std::vector<uint8_t>b;for(int16_t x:p){b.push_back(x&255);b.push_back(uint16_t(x)>>8);}save(path,b);}
template<size_t N>void numbers(std::ostream& out,const uint64_t(&values)[N]){out<<'[';for(size_t i=0;i<N;i++)out<<(i?",":"")<<values[i];out<<']';}
}
int main(int argc,char** argv){try{
    if((argc==2||argc==3)&&std::string(argv[1])=="selftest"){
        lpx::Stream s;s.samples=9*160;s.profile=4;s.rate=8000;s.pre=13926;
        int frames=(s.samples+319)/320;s.spectra.resize(frames);s.parameters.resize(frames*2);s.pulses.resize(frames*16);s.extras.assign(frames*8,lpx::Pulse{{-1,0}});
        for(auto& v:s.spectra)for(int j=0;j<10;j++)v[j]=2+3*j;
        for(size_t j=0;j<s.parameters.size();j++)s.parameters[j]=lpx::Parameters{{23+std::min(int(j),8),60+int(j),8}};
        for(auto& p:s.pulses)p=lpx::Pulse{{0,8}};
        int invalidRejected=0;
        for(int test=0;test<18;test++){
            auto bad=s;
            if(test==0)bad.profile=0;
            if(test==1)bad.spectra.clear();
            if(test==2)bad.initial.h[0]=1;
            if(test==3)bad.spectra[0][1]=bad.spectra[0][0];
            if(test==4)bad.parameters[0][2]=15;
            if(test==5)bad.pre=16385;
            if(test==6)bad.parameters.pop_back();
            if(test==7)bad.pulses.pop_back();
            if(test==8)bad.extras.pop_back();
            if(test==9)bad.initial.ring[123]=1;
            if(test==10)bad.initial.dd=1;
            if(test==11)bad.bright=11470;
            if(test==12)bad.pulses.clear();
            if(test==13)bad.extras.clear();
            if(test==14)bad.initial.cc=1;
            if(test==15)bad.spectra[0][9]=32;
            if(test==16)bad.samples=0;
            if(test==17)bad.parameters.clear();
            try{lbg1::encode(bad,lbg1::variant("exact"));}catch(const std::runtime_error&){++invalidRejected;}
        }
        if(invalidRejected!=18)throw std::runtime_error("Public encoder validation selftest failed");
        auto exact=lbg1::encode(s,lbg1::variant("exact"));auto original=lpx::packV9(s);Lpx4HybridCore originalDecoder;
        if(!originalDecoder.begin(original.data(),original.size()))throw std::runtime_error("Synthetic LPX control header failed");
        lpx::Pcm originalPcm;int16_t originalSample;while(originalDecoder.nextS16(originalSample))originalPcm.push_back(originalSample);
        if(originalDecoder.error()||originalPcm!=exact.pcm)throw std::runtime_error("Exact synthetic LG/native LPX control failed");
        auto encoded=lbg1::encode(s,lbg1::variant("trajectory-quality"));
        lbg1::Decoder d;if(!d.begin(encoded.bytes.data(),encoded.bytes.size()))throw std::runtime_error("Encoder synthetic header failed");
        lpx::Pcm replay;int16_t x;while(d.nextS16(x))replay.push_back(x);
        if(d.error()||replay!=encoded.pcm||!encoded.stats.scaleCommands[2]||!encoded.stats.pitchCommands[2]||encoded.stats.maximumLevelErrorDb>.05+1e-12)
            throw std::runtime_error("True logarithmic/integer-pitch encoder selftest failed");
        std::ostringstream metadata;metadata.precision(12);metadata<<"{\"samples\":"<<s.samples<<",\"bytes\":"<<encoded.bytes.size()<<",\"decoder_reference_exact\":true,\"true_log_scale_commands\":"<<encoded.stats.scaleCommands[2]
                 <<",\"linear_pitch_commands\":"<<encoded.stats.pitchCommands[2]<<",\"maximum_level_error_db\":"<<encoded.stats.maximumLevelErrorDb<<",\"invalid_public_models_rejected\":"<<invalidRejected<<",\"exact_control_matches_native_lpx\":true}\n";
        if(argc==3){save(std::string(argv[2])+".lbg",encoded.bytes);savePcm(std::string(argv[2])+".pcm",encoded.pcm);std::ofstream f(std::string(argv[2])+".json");f<<metadata.str();}
        std::cout<<metadata.str();return 0;
    }
    if(argc!=6)throw std::runtime_error("Usage: encode_probe MODEL SOURCE_PCM BASELINE_PCM OUTPUT_PREFIX VARIANT");
    const auto model=lbg1::readModel(argv[1]);const auto source=pcm(argv[2]),baseline=pcm(argv[3]);
    if(source.size()!=size_t(model.samples)||baseline.size()!=source.size()||lpx::render(model)!=baseline)throw std::runtime_error("Model/baseline/reference mismatch");
    std::string variantName(argv[5]);bool refit=variantName.size()>6&&variantName.substr(variantName.size()-6)=="-refit";
    auto options=lbg1::variant(refit?variantName.substr(0,variantName.size()-6):variantName);auto result=lbg1::encode(model,options);
    lbg1::PulseRefitStats refitStats;bool refitAccepted=false;lpx::Quality preRefitQuality,proposalQuality;unsigned refitRejectedBy=0;
    bool proposalFullBand=true,proposalLevel=true,proposalSpectrum=true;
    if(refit){
        lpx::QualityContext q(source);lpx::FullBandContext f(source,8000);preRefitQuality=q.quality(result.pcm);auto oldFull=f.measure(result.pcm);
        auto fitted=lbg1::refitPulses(model,result,source,refitStats);auto candidate=lbg1::encode(fitted,options);
        if(candidate.bytes.size()!=result.bytes.size())throw std::runtime_error("Pulse refit changed the fixed bit budget");
        proposalQuality=q.quality(candidate.pcm);auto nextFull=f.measure(candidate.pcm);
        proposalFullBand=f.accepts(nextFull,oldFull);proposalLevel=lpx::safeSynthesisLevel(model,source,candidate.pcm);proposalSpectrum=lpx::safeSynthesisSpectrum(source,candidate.pcm);
        if(proposalQuality.error[0]>preRefitQuality.error[0])refitRejectedBy|=1;
        if(proposalQuality.error[1]>preRefitQuality.error[1])refitRejectedBy|=2;
        if(proposalQuality.stoi[0]+1e-12<preRefitQuality.stoi[0])refitRejectedBy|=4;
        if(proposalQuality.stoi[1]+1e-12<preRefitQuality.stoi[1])refitRejectedBy|=8;
        if(!proposalFullBand)refitRejectedBy|=16;if(!proposalLevel)refitRejectedBy|=32;if(!proposalSpectrum)refitRejectedBy|=64;
        refitAccepted=!refitRejectedBy;
        if(refitAccepted)result=std::move(candidate);
    }
    lbg1::Decoder d;if(!d.begin(result.bytes.data(),result.bytes.size()))throw std::runtime_error("LG decoder rejected header");
    lpx::Pcm replay;int16_t value;
    while(d.nextS16(value))replay.push_back(value);
    if(d.error()||replay!=result.pcm)throw std::runtime_error("LG decoder and independent reference differ");
    if(!refit&&!options.trajectories&&options.coefficientError==0&&result.pcm!=baseline)throw std::runtime_error("Exact LG control changed output");
    lpx::QualityContext quality(source);auto actual=quality.quality(result.pcm),old=quality.quality(baseline);
    if(!refit)preRefitQuality=proposalQuality=actual;
    lpx::FullBandContext full(source,8000);auto a=full.measure(result.pcm),b=full.measure(baseline);
    bool levelSafe=lpx::safeSynthesisLevel(model,source,result.pcm),spectrumSafe=lpx::safeSynthesisSpectrum(source,result.pcm);
    std::ostringstream json;json.precision(12);
    json<<"{\"variant\":\""<<argv[5]<<"\",\"samples\":"<<model.samples<<",\"bytes\":"<<result.bytes.size()
        <<",\"decoder_reference_exact\":true,\"baseline_pcm_equal\":"<<(result.pcm==baseline?"true":"false")
        <<",\"coefficient_error_budget\":"<<options.coefficientError<<",\"actual_coefficient_max_error\":"<<result.stats.coefficientMaxError
        <<",\"changed_coefficients\":"<<result.stats.changedCoefficients<<",\"forced_raw_frames\":"<<result.stats.forcedRawFrames
        <<",\"level_error_budget_db\":"<<options.levelErrorDb<<",\"maximum_level_error_db\":"<<result.stats.maximumLevelErrorDb
        <<",\"spectrum_bits\":"<<result.stats.spectrumBits<<",\"scale_bits\":"<<result.stats.scaleBits<<",\"pitch_bits\":"<<result.stats.pitchBits
        <<",\"pulse_bits\":"<<result.stats.pulseBits<<",\"extra_bits\":"<<result.stats.extraBits
        <<",\"repeat_frames\":"<<result.stats.repeatFrames<<",\"repeat_anchors\":"<<result.stats.repeatAnchors
        <<",\"pulse_refit_attempted\":"<<(refit?"true":"false")<<",\"pulse_refit_accepted\":"<<(refitAccepted?"true":"false")
        <<",\"pulse_refit_evaluations\":"<<refitStats.evaluations<<",\"pulse_refit_changed_proposal_pulses\":"<<refitStats.changedPulses
        <<",\"pulse_refit_changed_applied_pulses\":"<<(refitAccepted?refitStats.changedPulses:0)<<",\"pulse_refit_rejection_bits\":"<<refitRejectedBy
        <<",\"pre_refit_pcm_sse\":"<<preRefitQuality.error[0]<<",\"pre_refit_pwm_sse\":"<<preRefitQuality.error[1]
        <<",\"pre_refit_pcm_stoi\":"<<preRefitQuality.stoi[0]<<",\"pre_refit_pwm_stoi\":"<<preRefitQuality.stoi[1]
        <<",\"refit_proposal_pcm_sse\":"<<proposalQuality.error[0]<<",\"refit_proposal_pwm_sse\":"<<proposalQuality.error[1]
        <<",\"refit_proposal_pcm_stoi\":"<<proposalQuality.stoi[0]<<",\"refit_proposal_pwm_stoi\":"<<proposalQuality.stoi[1]
        <<",\"refit_proposal_fullband_admitted\":"<<(proposalFullBand?"true":"false")<<",\"refit_proposal_level_safe\":"<<(proposalLevel?"true":"false")
        <<",\"refit_proposal_spectrum_safe\":"<<(proposalSpectrum?"true":"false")
        <<",\"group_plan_counts\":";numbers(json,result.stats.planCounts);json<<",\"group_width_counts\":";numbers(json,result.stats.widthCounts);
    json<<",\"group_exponent_counts\":";numbers(json,result.stats.exponentCounts);json<<",\"scale_commands\":";numbers(json,result.stats.scaleCommands);
    json<<",\"pitch_commands\":";numbers(json,result.stats.pitchCommands);
    json<<",\"pcm_sse\":"<<actual.error[0]<<",\"pwm_sse\":"<<actual.error[1]<<",\"pcm_stoi\":"<<actual.stoi[0]<<",\"pwm_stoi\":"<<actual.stoi[1]
        <<",\"baseline_pcm_sse\":"<<old.error[0]<<",\"baseline_pwm_sse\":"<<old.error[1]<<",\"baseline_pcm_stoi\":"<<old.stoi[0]<<",\"baseline_pwm_stoi\":"<<old.stoi[1]
        <<",\"spectral_error\":"<<a.balancedError[0]<<",\"temporal_error\":"<<a.balancedTemporalError[0]
        <<",\"baseline_spectral_error\":"<<b.balancedError[0]<<",\"baseline_temporal_error\":"<<b.balancedTemporalError[0]
        <<",\"level_safe\":"<<(levelSafe?"true":"false")<<",\"spectrum_safe\":"<<(spectrumSafe?"true":"false")<<"}\n";
    save(std::string(argv[4])+".lbg",result.bytes);savePcm(std::string(argv[4])+".pcm",result.pcm);
    std::ofstream metadata(std::string(argv[4])+".json");metadata<<json.str();if(!metadata)throw std::runtime_error("Cannot write metadata");
    std::cout<<json.str();return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
