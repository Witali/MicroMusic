// Separate synthetic validity gate; no speech encode or production test edits.
#define LPX_ENSEMBLE_NO_MAIN
#include "../benchmark_ensemble.cpp"
#include <functional>

namespace {
void requireTest(bool condition,const char* why){if(!condition){std::cerr<<"FAIL: "<<why<<'\n';std::exit(1);}}
template<class F> void rejects(F action,const char* why){bool threw=false;try{action();}catch(const std::exception&){threw=true;}requireTest(threw,why);}
Pcm nativeOracle(const std::vector<uint8_t>& bytes) {
    Lpx4HybridCore decoder;requireTest(decoder.beginWideV9(bytes.data(),bytes.size()),"independent native begin");
    Pcm result(decoder.samples());for(auto& value:result)requireTest(decoder.nextS16(value),"independent native PCM length");
    int16_t tail;requireTest(!decoder.nextS16(tail)&&!decoder.error()&&decoder.finished(),"independent native PCM EOF");
    requireTest(decoder.beginWideV9(bytes.data(),bytes.size()),"independent PWM restart");
    for(int value:result){uint8_t actual;const int q14=(value+1)>>1;const int expected=std::max(0,std::min(255,128+((q14*130+8192)>>14)));
        requireTest(decoder.next(actual)&&actual==expected,"independent native PWM transfer");}
    uint8_t last;requireTest(!decoder.next(last)&&!decoder.error()&&decoder.finished(),"independent native PWM EOF");return result;
}
Stream baselineFixture(int n,QualityTarget target) {
    Stream s;s.samples=n;s.rate=8000;s.profile=4;s.accuracy=3;s.qualityTarget=target;s.pre=8192;s.bright=0;
    Spectrum v;for(int j=0;j<10;++j)v[j]=2+3*j;
    const int frames=(n+319)/320;s.spectra.assign(frames,v);s.parameters.assign(frames*2,Parameters{{16,37,6}});
    s.pulses.resize(frames*16);s.extras.assign(frames*8,Pulse{{-1,0}});
    for(int p=0;p<frames*16;++p){int pos=(p*7)%20;if(pos%5==2)++pos;s.pulses[p]={{pos,p%2?-8:8}};}
    return ensemble::checked(packV9(s),target,3);
}
bool physicalEqual(const Stream& a,const Stream& b) {
    return a.samples==b.samples&&a.rate==b.rate&&a.profile==b.profile&&a.pre==b.pre&&a.bright==b.bright
        &&a.qualityTarget==b.qualityTarget&&a.spectra==b.spectra&&a.parameters==b.parameters&&a.pulses==b.pulses
        &&a.extras==b.extras&&a.continuation==b.continuation&&a.allowExtras==b.allowExtras
        &&a.previousSpectrum==b.previousSpectrum&&a.previousInput==b.previousInput&&a.previousCoefficients==b.previousCoefficients
        &&a.lookahead==b.lookahead&&a.initial.dd==b.initial.dd&&a.initial.cc==b.initial.cc
        &&std::equal(a.initial.h,a.initial.h+10,b.initial.h)&&std::equal(a.initial.ring,a.initial.ring+256,b.initial.ring);
}
Stream oddCandidate(const Stream& base){auto s=ensemble::relabelFine(base);for(auto& v:s.spectra)++v[0];return s;}
void retained(const ensemble::Protection& result,const Stream& base) {
    requireTest(!result.admitted&&packV9(result.selected)==packV9(base)&&render(result.selected)==render(base),"protection did not retain original physical baseline");
}
int identity() {
    int cases=0;
    for(QualityTarget target:{QualityTarget::Pcm,QualityTarget::Pwm})for(int n:{1,19,20,21,39,40,41,159,160,161,319,320,321,641,1281}) {
        const auto base=baselineFixture(n,target),fine=ensemble::relabelFine(base);const auto bytes=packV9(base);
        requireTest(base.accuracy==3&&fine.accuracy==4&&physicalEqual(base,fine),"host relabel changed a physical field");
        requireTest(bytes==packV9(fine)&&render(base)==render(fine),"host relabel changed bytes or model PCM");
        requireTest(nativeOracle(bytes)==render(fine),"host relabel changed actual native PCM");
        requireTest(packV9(ensemble::checked(bytes,target,4))==bytes,"fine checker altered physical P3 baseline");++cases;
    }
    std::cout<<"PASS identity: "<<cases<<" reset/partial-tail cases; all physical fields, exact bytes/native PCM/PWM/EOF retained\n";return 0;
}
int fineGrid() {
    int cases=0;
    for(QualityTarget target:{QualityTarget::Pcm,QualityTarget::Pwm})for(int n:{41,161,321,641,1281}) {
        const auto base=baselineFixture(n,target),fine=oddCandidate(base);const auto bytes=packV9(fine);const auto actual=nativeOracle(bytes);
        requireTest((fine.spectra[0][0]&1)==1&&bytes.size()<=packV9(base).size(),"odd-grid fixture must fit actual B0");
        auto accepted=ensemble::checked(bytes,target,4);
        requireTest(accepted.spectra==fine.spectra&&packV9(accepted)==bytes&&render(accepted)==actual,"ordinary P4 odd rank was requantized by checker");
        auto forced=fine;forced.accuracy=3;
        requireTest(packV9(forced)!=bytes&&render(forced)!=actual,"wrong forced-P3 checker fixture did not alter physical output");
        rejects([&]{ensemble::checked(bytes,target,3);},"forced P3 checker accepted noncanonical fine packet");++cases;
    }
    const auto base=baselineFixture(641,QualityTarget::Pcm);const auto bytes=packV9(base);
    rejects([&]{ensemble::checked(bytes,QualityTarget(7),4);},"invalid quality target checker");
    for(int accuracy:{0,2,5,8})rejects([&]{ensemble::checked(bytes,QualityTarget::Pcm,accuracy);},"invalid accuracy checker");
    auto bad=bytes;bad.pop_back();rejects([&]{ensemble::checked(bad,QualityTarget::Pcm,4);},"truncated packet checker");
    bad=bytes;bad.push_back(0);rejects([&]{ensemble::checked(bad,QualityTarget::Pcm,4);},"trailing byte checker");
    std::cout<<"PASS fine grid: "<<cases<<" legal odd-rank/native cases; forced-P3 alteration and policy/EOF failures detected\n";return 0;
}
int protection() {
    int rejected=0,noiseCases=0;
    for(QualityTarget target:{QualityTarget::Pcm,QualityTarget::Pwm}) {
        const auto base=baselineFixture(641,target),fine=ensemble::relabelFine(base);const auto ref=nativeOracle(packV9(base));
        const auto unchanged=ensemble::protect(ref,base,fine);retained(unchanged,base);requireTest(!unchanged.changed,"same bytes relabel declared changed");
        auto growing=fine;growing.extras[0]={{0,1}};
        requireTest(packV9(growing).size()>packV9(base).size(),"growth fixture fits B0 unexpectedly");
        const auto growth=ensemble::protect(ref,base,growing);retained(growth,base);
        requireTest(growth.reject&ensemble::Size,"actual B0 growth was not rejected");++rejected;
        auto worse=fine;worse.pulses[0][1]*=-1;
        requireTest(render(worse)!=ref,"regression fixture is unchanged");const auto quality=ensemble::protect(ref,base,worse);retained(quality,base);
        requireTest(quality.reject&ensemble::ActiveQuality,"experimental strict active-SSE floor missing");++rejected;
        auto loud=fine;for(auto& p:loud.parameters)p[0]=31;
        const auto noise=ensemble::protect(ref,base,loud);retained(noise,base);
        QualityContext q(ref,true,8000,target);const auto a=q.measure(ref),b=q.measure(render(loud));bool expectedNoise=false;
        for(int path=0;path<qualityPathCount(target);++path)expectedNoise|=!std::isfinite(b.noise[path])||b.noise[path]>a.noise[path]+1e-12;
        requireTest(bool(noise.reject&ensemble::OldNoise)==expectedNoise,"experimental old-noise gate differs from independent active-path measurement");
        noiseCases+=expectedNoise;
        for(int accuracy:{0,3,6}){auto invalid=fine;invalid.accuracy=accuracy;const auto p=ensemble::protect(ref,base,invalid);retained(p,base);requireTest(p.reject&ensemble::Policy,"wrong candidate policy was not rejected");++rejected;}
        auto invalid=fine;invalid.qualityTarget=target==QualityTarget::Pcm?QualityTarget::Pwm:QualityTarget::Pcm;
        auto policy=ensemble::protect(ref,base,invalid);retained(policy,base);requireTest(policy.reject&ensemble::Policy,"wrong target was not rejected");++rejected;
        const std::vector<std::function<void(Stream&)>> mutations={
            [](Stream&s){s.samples--;},[](Stream&s){s.rate=16000;},[](Stream&s){s.profile=6;},
            [](Stream&s){s.spectra.pop_back();},[](Stream&s){s.parameters.clear();},[](Stream&s){s.pulses.clear();},[](Stream&s){s.extras.clear();},
            [](Stream&s){s.spectra[0][1]=s.spectra[0][0];},[](Stream&s){s.spectra[0][0]=-1;},
            [](Stream&s){s.pulses[0]={{2,8}};},[](Stream&s){s.pulses[0]={{0,0}};},
            [](Stream&s){s.parameters[0][0]=32;},[](Stream&s){s.parameters[0][1]=17;},[](Stream&s){s.parameters[0][2]=3;},
            [](Stream&s){s.bright=11470;},[](Stream&s){s.pre=16385;},[](Stream&s){s.continuation=true;},
            [](Stream&s){s.initial.dd=1;},[](Stream&s){s.lookahead.push_back(0);}
        };
        for(const auto& mutate:mutations){invalid=fine;mutate(invalid);const auto p=ensemble::protect(ref,base,invalid);retained(p,base);requireTest(p.reject&ensemble::Geometry,"malformed/nonreset geometry was not rejected");++rejected;}
        rejects([&]{ensemble::protect(Pcm(640),base,fine);},"wrong reference geometry accepted");
    }
    requireTest(noiseCases==2,"constructed old-noise regression did not exercise both target policies");
    std::cout<<"PASS protection: "<<rejected<<" B0/policy/target/geometry/SSE rejections; strict old-noise checks on both policies; original floor retained\n";return 0;
}
int fallback() {
    int cases=0;
    for(QualityTarget target:{QualityTarget::Pcm,QualityTarget::Pwm}) {
        const auto base=baselineFixture(641,target),fine=ensemble::relabelFine(base);const auto original=packV9(base);
        BitrateReport report;report.candidates=7;report.parameterTrials=13;report.pulseTrials=17;
        for(int error:{-1,-2,-3,-6,-7,-1000}) {
            auto failed=report;failed.error=error;ensemble::SearchResult result;
            ensemble::settleSearch(fine,oddCandidate(base),failed,result);
            requireTest(result.fallback&&result.fallbackReason=="search_error"&&result.report.error==error
                &&result.report.parameterTrials==13&&packV9(result.raw)==original&&nativeOracle(original)==render(result.raw),"search error displaced valid floor or lost report");++cases;
        }
        std::vector<Stream> invalid;
        Stream empty;empty.accuracy=4;empty.qualityTarget=target;invalid.push_back(empty);
        auto wrong=fine;wrong.accuracy=3;invalid.push_back(wrong);wrong=fine;wrong.bright=11470;invalid.push_back(wrong);
        wrong=fine;wrong.samples--;invalid.push_back(wrong);wrong=fine;wrong.extras[0]={{0,1}};invalid.push_back(wrong);
        wrong=fine;wrong.pulses[0]={{0,0}};invalid.push_back(wrong);
        for(const auto& proposal:invalid){ensemble::SearchResult result;ensemble::settleSearch(fine,proposal,report,result);
            requireTest(result.fallback&&result.fallbackReason!="none"&&packV9(result.raw)==original,"malformed/growing search result displaced valid floor");++cases;}
        ensemble::SearchResult good;const auto odd=oddCandidate(base);ensemble::settleSearch(fine,odd,report,good);
        requireTest(!good.fallback&&good.fallbackReason=="none"&&packV9(good.raw)==packV9(odd),"valid odd-grid raw result was relabeled or lost");++cases;
        // Syntactically valid quality regressions remain RAW diagnostics; only
        // protect() decides admission, so do not mislabel these as search errors.
        auto worse=fine;worse.pulses[0][1]*=-1;ensemble::settleSearch(fine,worse,report,good);
        requireTest(!good.fallback&&packV9(good.raw)==packV9(worse),"valid regressing raw output was silently replaced");++cases;
    }
    std::cout<<"PASS fallback: "<<cases<<" forced errors/malformed/growth and valid-raw settlement contracts; no encode search invoked\n";return 0;
}
}
int main(int argc,char** argv){requireTest(argc==2,"select identity, grid, protection or fallback");const std::string mode=argv[1];
    if(mode=="identity")return identity();if(mode=="grid")return fineGrid();if(mode=="protection")return protection();if(mode=="fallback")return fallback();return 2;}
