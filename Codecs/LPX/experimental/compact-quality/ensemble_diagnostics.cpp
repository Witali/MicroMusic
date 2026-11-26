// Posthoc measurement only. Replays frozen bytes; never invokes an encoder.
#define LPX_ENSEMBLE_NO_MAIN
#include "benchmark_ensemble.cpp"

namespace {
uint8_t diagnosticOctaveMask(double source,double actual) {
    if(!std::isfinite(source)||!std::isfinite(actual))return 0;
    const double cents=1200*std::log2(source/actual);
    return uint8_t((std::abs(cents+1200)<=100?1:0)|(std::abs(cents-1200)<=100?2:0));
}
double diagnosticPeriod(const Pcm& samples,int start,std::vector<double>& scratch) {
    for(int i=0;i<640;++i)scratch[i]=samples[start+i];
    double rms;return estimatePeriod(scratch.data(),640,rms,8000);
}
void value(double x){num(x);}
void emitBands(const Pcm& reference,const Pcm& original,const Pcm& raw,QualityTarget target) {
    FullBandContext context(reference,8000,target);
    const auto a=context.measure(original),b=context.measure(raw);
    if(!a.valid || !b.valid)throw std::runtime_error("Invalid full-band diagnostic");
    double totalPower=0;for(int band=0;band<a.bands;++band)totalPower+=a.sourcePower[band];
    bool reconstructed=true;
    for(int path=0;path<qualityPathCount(target);++path) {
        if(path)std::cout<<',';
        std::cout<<"{\"path\":\""<<(path?"pwm":"pcm")<<"\",\"total_error_baseline\":";value(a.totalError[path]);
        std::cout<<",\"total_error_raw\":";value(b.totalError[path]);
        const bool totalRejected=b.totalError[path]>a.totalError[path]+1e-12;
        reconstructed&=!totalRejected;
        std::cout<<",\"total_error_regressed\":";boolval(totalRejected);
        std::cout<<",\"bands\":[";
        for(int band=0;band<a.bands;++band) {
            if(band)std::cout<<',';
            const bool errorRejected=a.supported[band] && b.error[path][band]>a.error[path][band]+1e-12;
            const bool retentionRejected=a.supported[band] && b.retention[path][band]+1e-12<a.retention[path][band];
            reconstructed&=!errorRejected&&!retentionRejected;
            std::cout<<"{\"low_hz\":"<<band*1000<<",\"high_hz\":"<<(band+1)*1000<<",\"supported\":";boolval(a.supported[band]);
            std::cout<<",\"source_power\":";value(a.sourcePower[band]);
            std::cout<<",\"source_power_fraction\":";value(totalPower?a.sourcePower[band]/totalPower:0);
            std::cout<<",\"baseline_error\":";value(a.error[path][band]);
            std::cout<<",\"raw_error\":";value(b.error[path][band]);
            std::cout<<",\"error_delta\":";value(b.error[path][band]-a.error[path][band]);
            std::cout<<",\"error_relative_delta_percent\":";value(a.error[path][band]?(b.error[path][band]/a.error[path][band]-1)*100:NAN);
            std::cout<<",\"error_floor_rejected\":";boolval(errorRejected);
            std::cout<<",\"baseline_retention\":";value(a.retention[path][band]);
            std::cout<<",\"raw_retention\":";value(b.retention[path][band]);
            std::cout<<",\"retention_delta_percentage_points\":";value((b.retention[path][band]-a.retention[path][band])*100);
            std::cout<<",\"retention_relative_db\":";value(a.retention[path][band]>0&&b.retention[path][band]>0?20*std::log10(b.retention[path][band]/a.retention[path][band]):NAN);
            std::cout<<",\"retention_floor_rejected\":";boolval(retentionRejected);
            std::cout<<",\"baseline_output_rms_over_source\":";value(a.sourcePower[band]>0?std::sqrt(a.outputPower[path][band]/a.sourcePower[band]):NAN);
            std::cout<<",\"raw_output_rms_over_source\":";value(a.sourcePower[band]>0?std::sqrt(b.outputPower[path][band]/a.sourcePower[band]):NAN);
            std::cout<<'}';
        }
        std::cout<<"]}";
    }
    if(reconstructed!=context.accepts(b,a))throw std::runtime_error("Full-band rule reconstruction differs");
}

void emitOctaves(const Pcm& reference,const Pcm& original,const Pcm& raw,QualityTarget target) {
    const Pcm baselinePaths[2]={original,target==QualityTarget::Pwm?pwm(original):Pcm{}};
    const Pcm rawPaths[2]={raw,target==QualityTarget::Pwm?pwm(raw):Pcm{}};
    std::vector<double> scratch(640);bool reconstructed=true;
    for(int path=0;path<qualityPathCount(target);++path) {
        if(path)std::cout<<',';
        int total=0,eligible=0,baselineLabels=0,rawLabels=0,added=0,removed=0;
        std::ostringstream events;events.precision(17);
        // Save detailed events through the same numeric helper/precision stream.
        std::streambuf* originalBuffer=std::cout.rdbuf();
        std::cout.rdbuf(events.rdbuf());
        for(int start=0;start+640<=int(reference.size());start+=160) {
            ++total;
            const double source=diagnosticPeriod(reference,start,scratch);
            if(!std::isfinite(source))continue;
            ++eligible;
            const double previous=diagnosticPeriod(baselinePaths[path],start,scratch);
            const double next=diagnosticPeriod(rawPaths[path],start,scratch);
            const uint8_t before=diagnosticOctaveMask(source,previous),after=diagnosticOctaveMask(source,next);
            baselineLabels+=before!=0;rawLabels+=after!=0;
            removed+=(before&~after)!=0;
            const uint8_t addition=after&~before;
            if(!addition)continue;
            if(added++)std::cout<<',';
            std::cout<<"{\"start_sample\":"<<start<<",\"end_sample_exclusive\":"<<start+640
                <<",\"start_seconds\":"<<double(start)/8000<<",\"end_seconds\":"<<double(start+640)/8000
                <<",\"source_period_samples\":";value(source);
            std::cout<<",\"baseline_period_samples\":";value(previous);
            std::cout<<",\"raw_period_samples\":";value(next);
            std::cout<<",\"source_estimated_hz\":";value(8000/source);
            std::cout<<",\"baseline_estimated_hz\":";value(8000/previous);
            std::cout<<",\"raw_estimated_hz\":";value(8000/next);
            std::cout<<",\"baseline_cents\":";value(1200*std::log2(source/previous));
            std::cout<<",\"raw_cents\":";value(1200*std::log2(source/next));
            std::cout<<",\"baseline_mask\":"<<int(before)<<",\"raw_mask\":"<<int(after)
                <<",\"added_mask\":"<<int(addition)<<'}';
        }
        std::cout.rdbuf(originalBuffer);
        reconstructed&=added==0;
        std::cout<<"{\"path\":\""<<(path?"pwm":"pcm")<<"\",\"all_windows\":"<<total
            <<",\"finite_source_period_windows\":"<<eligible<<",\"baseline_octave_windows\":"<<baselineLabels
            <<",\"raw_octave_windows\":"<<rawLabels<<",\"removed_octave_windows\":"<<removed
            <<",\"added_octave_windows\":"<<added<<",\"additions\":["<<events.str()<<"]}";
    }
    const PitchGuardContext guard(reference,original,8000,target);
    if(reconstructed!=guard.accepts(raw))throw std::runtime_error("Pitch rule reconstruction differs");
}
}

int main(int argc,char** argv) {
    try {
        if(argc!=5)throw std::runtime_error("SOURCE BASELINE RAW pcm|pwm");
        const std::string mode=argv[4];
        if(mode!="pcm"&&mode!="pwm")throw std::runtime_error("Invalid policy");
        const auto target=mode=="pcm"?QualityTarget::Pcm:QualityTarget::Pwm;
        const auto reference=pcm(argv[1]);
        const auto baseline=ensemble::checked(bytes(argv[2]),target,3);
        const auto raw=ensemble::checked(bytes(argv[3]),target,4);
        if(reference.size()!=size_t(baseline.samples)||baseline.samples!=raw.samples)
            throw std::runtime_error("Reference geometry mismatch");
        const auto a=render(baseline),b=render(raw);
        std::cout.precision(17);
        std::cout<<"{\"fullband\":[";emitBands(reference,a,b,target);
        std::cout<<"],\"octaves\":[";emitOctaves(reference,a,b,target);
        std::cout<<"],\"native_model_exact\":true,\"fullband_rule_crosscheck\":true,\"pitch_rule_crosscheck\":true}\n";
        return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
