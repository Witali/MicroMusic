// Automatic P3 integration benchmark; the old experiment remains immutable.
#define LPX_ENSEMBLE_NO_MAIN
#include "../benchmark_ensemble.cpp"

namespace {
void stageReport(const CompactEnsembleReport& r) {
    std::cout<<"{\"enabled\":"<<r.enabled<<",\"eligible\":"<<r.eligible
        <<",\"attempted\":"<<r.attempted<<",\"search_calls\":"<<r.searchCalls
        <<",\"status\":"<<r.status<<",\"error\":"<<r.error
        <<",\"policy_budget_C\":"<<r.policyBudget<<",\"baseline_bytes_B0\":"<<r.baselineBytes
        <<",\"raw_bytes\":"<<r.rawBytes<<",\"selected_bytes\":"<<r.selectedBytes
        <<",\"raw_valid\":"<<r.rawValid<<",\"raw_changed\":"<<r.rawChanged
        <<",\"selected\":"<<r.selected<<",\"search_candidates\":"<<r.searchCandidates
        <<",\"search_selected\":"<<r.searchSelected<<",\"parameter_trials\":"<<r.parameterTrials
        <<",\"pulse_trials\":"<<r.pulseTrials<<",\"selection_candidates\":"<<r.selection.candidates
        <<",\"selection_accepted\":"<<r.selection.accepted<<",\"selection_error\":"<<r.selection.error
        <<",\"selection_octave_rejected\":"<<r.selection.octaveRejected
        <<",\"initial_objective\":";num(r.selection.initialObjective);
    std::cout<<",\"final_objective\":";num(r.selection.finalObjective);std::cout<<'}';
}
int railCount(const Pcm& pcm) {
    int count=0;for(int x:pwm(pcm))count+=x==-32768 || x==32512;return count;
}
void ser(const Pcm& reference,const Pcm& output) {
    uint64_t energy=0;for(int value:reference)energy+=uint64_t(int64_t(value)*value);
    const uint64_t errors[2]={sse(reference,output),sse(reference,pwm(output))};
    std::cout<<'[';for(int path=0;path<2;++path) {
        if(path)std::cout<<',';num(energy && errors[path]?10*std::log10(double(energy)/errors[path]):NAN);
    }std::cout<<']';
}
}

int main(int argc,char** argv) {
    try {
        if(argc!=5)throw std::runtime_error("SOURCE OUTPUT_PREFIX pcm|pwm DISABLED_BASELINE_OR_DASH");
        const auto reference=pcm(argv[1]);const std::string prefix=argv[2],mode=argv[3];
        const std::string baselineFile=argv[4];
        if(mode!="pcm" && mode!="pwm")throw std::runtime_error("Invalid target");
        const auto target=mode=="pcm"?QualityTarget::Pcm:QualityTarget::Pwm;
        if(reference.empty() || reference.size()>64000 || !enc_reserve(reference.size()))
            throw std::runtime_error("Invalid reference/reserve");
        AdaptiveReport report;Stream raw;
        const auto wall=std::chrono::steady_clock::now();const auto cpu=std::clock();
        const auto selected=encodeAccuracy(reference,3,8000,report,4,nullptr,target,&raw);
        const double elapsed=std::chrono::duration<double>(std::chrono::steady_clock::now()-wall).count();
        const double cpuElapsed=double(std::clock()-cpu)/CLOCKS_PER_SEC;
        if(report.error || selected.samples!=int(reference.size()))throw std::runtime_error("Full encode failed");
        const auto selectedBytes=packV9(selected);const auto selectedPcm=render(selected);
        if(!verifyStream(selected,selectedPcm))throw std::runtime_error("Final native mismatch");
        std::cout.precision(14);
        std::cout<<"{\"samples\":"<<reference.size()<<",\"rate\":8000,\"target\":\""<<mode
            <<"\",\"calls\":4,\"whole_encode_seconds\":"<<elapsed<<",\"whole_encode_cpu_seconds\":"<<cpuElapsed
            <<",\"isolated_optional_phase_seconds\":null,\"global_error\":"<<report.error
            <<",\"legacy_cap\":"<<report.cap<<",\"legacy_selected\":"<<report.selected
            <<",\"legacy_candidates\":"<<report.candidates<<",\"legacy_stages\":"<<report.stages
            <<",\"stage\":";stageReport(report.compactEnsemble);
        std::cout<<",\"selected_output\":";ensemble::emitOutput(selected,reference,prefix);
        std::cout<<",\"selected_pwm_rail_samples\":"<<railCount(selectedPcm);
        std::cout<<",\"selected_ser_db\":";ser(reference,selectedPcm);
        if(baselineFile!="-") {
            const auto baselineBytes=bytes(baselineFile.c_str());
            const auto baseline=ensemble::checked(baselineBytes,target,3);
            if(baseline.samples!=selected.samples || selectedBytes.size()>baselineBytes.size()
                || report.compactEnsemble.baselineBytes!=int(baselineBytes.size()))
                throw std::runtime_error("Disabled floor/cap mismatch");
            const bool available=raw.samples!=0;
            if(!available)raw=baseline;
            ProfileQualityReport choice;
            const auto independentlySelected=selectQualityProposals(baseline,reference,{&raw},choice,true,baselineBytes.size());
            if(choice.error || packV9(independentlySelected)!=selectedBytes)
                throw std::runtime_error("Automatic selector differs from independent replay");
            const auto baselinePcm=render(baseline),rawPcm=render(raw);
            FullBandContext diagnostic(reference,8000,target);
            PitchGuardContext pitch(reference,baselinePcm,8000,target);
            std::cout<<",\"raw_available\":";boolval(available);
            std::cout<<",\"raw_candidate\":";ensemble::emitOutput(raw,reference,prefix+"-raw");
            std::cout<<",\"raw_pwm_rail_samples\":"<<railCount(rawPcm);
            std::cout<<",\"raw_ser_db\":";ser(reference,rawPcm);
            std::cout<<",\"raw_changed\":";boolval(packV9(raw)!=baselineBytes);
            std::cout<<",\"selected_changed\":";boolval(selectedBytes!=baselineBytes);
            std::cout<<",\"research_retention_guard_raw\":";boolval(diagnostic.accepts(diagnostic.measure(rawPcm),diagnostic.measure(baselinePcm)));
            std::cout<<",\"research_retention_guard_selected\":";boolval(diagnostic.accepts(diagnostic.measure(selectedPcm),diagnostic.measure(baselinePcm)));
            std::cout<<",\"production_pitch_guard_raw\":";boolval(pitch.accepts(rawPcm));
            std::cout<<",\"production_pitch_guard_selected\":";boolval(pitch.accepts(selectedPcm));
            std::cout<<",\"selector_replay_exact\":true,\"raw_changes\":";emitChanges(baseline,raw);
            std::cout<<",\"selected_changes\":";emitChanges(baseline,selected);
        }
        std::cout<<"}\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
