// Corpus-driven decoder validation. No generated media is retained in Git.
#include "decoder.h"
#include <algorithm>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <vector>

struct Source {
    const std::vector<uint8_t>* bytes;
    explicit Source(const std::vector<uint8_t>* value):bytes(value){}
    size_t calls=0;
    int failAt=-1;
    bool outside=false;
};
static bool reader(void* context,uint16_t at,uint8_t* value){
    Source& s=*static_cast<Source*>(context);++s.calls;
    if(at>=s.bytes->size()){s.outside=true;return false;}
    if(int(at)==s.failAt)return false;
    *value=(*s.bytes)[at];return true;
}
static void require(bool condition,const char* message){if(!condition)throw std::runtime_error(message);}
static std::vector<uint8_t> load(const char* path){
    std::ifstream f(path,std::ios::binary);if(!f)throw std::runtime_error("Cannot read corpus file");
    return {std::istreambuf_iterator<char>(f),{}};
}
static uint32_t randomWord(uint32_t& state){state^=state<<13;state^=state>>17;state^=state<<5;return state;}
struct Output {uint64_t hash=1469598103934665603ULL;size_t samples=0;uint8_t error=0;};
static Output run(lbg1::Decoder& d){
    Output out;int16_t sample;
    while(d.nextS16(sample)){
        require(++out.samples<=64000,"Decoder exceeded bounded sample count");
        out.hash^=uint16_t(sample);out.hash*=1099511628211ULL;
    }
    out.error=d.error();
    if(!out.error)require(out.samples==d.sampleCount()&&d.finished(),"Successful decode length mismatch");
    return out;
}
static bool same(const Output& a,const Output& b){return a.samples==b.samples&&a.hash==b.hash&&a.error==b.error;}
int main(int argc,char** argv){try{
    require(argc>=2,"Supply verified LG corpus files");
    std::vector<std::vector<uint8_t>> corpus;
    std::vector<Output> reference;
    uint64_t callbackChecks=0,faultChecks=0,mutations=0,rejected=0,validMutations=0,pwmSamples=0;
    lbg1::Decoder reused;
    for(int index=1;index<argc;index++){
        auto bytes=load(argv[index]);require(bytes.size()<=65535,"Oversized corpus input");
        lbg1::Decoder direct;require(direct.begin(bytes.data(),uint16_t(bytes.size())),"Valid corpus header rejected");
        auto expected=run(direct);require(!expected.error,"Valid corpus failed");
        Source source{&bytes};lbg1::Decoder callback;
        require(callback.beginCallback(reader,&source,uint16_t(bytes.size())),"Valid callback header rejected");
        require(same(run(callback),expected)&&!source.outside,"Callback differs from direct memory");++callbackChecks;
        require(reused.begin(bytes.data(),uint16_t(bytes.size())),"Reset header rejected");
        require(same(run(reused),expected),"Reset retained stale state");
        lbg1::Decoder q14,pwm;require(q14.begin(bytes.data(),uint16_t(bytes.size()))&&pwm.begin(bytes.data(),uint16_t(bytes.size())),"Output mode begin");
        int16_t q;uint8_t actual;
        while(q14.nextQ14(q)){
            require(pwm.next(actual),"PWM shorter than Q14");
            int expectedPwm=128+((int32_t(q)*130+8192)>>14);
            expectedPwm=std::max(0,std::min(255,expectedPwm));
            require(actual==expectedPwm,"PWM differs from integer output contract");++pwmSamples;
        }
        require(!q14.error()&&!pwm.next(actual)&&!pwm.error(),"Output mode tail differs");
        for(int offset:{0,2,7,12,13,int(bytes.size()-1)}){
            Source failing{&bytes};failing.failAt=offset;lbg1::Decoder faulty;
            faulty.beginCallback(reader,&failing,uint16_t(bytes.size()));auto result=run(faulty);
            require(result.error&&!failing.outside,"Injected callback failure ignored");++faultChecks;
        }
        corpus.push_back(std::move(bytes));reference.push_back(expected);
    }
    uint32_t seed=0x46cf1a29;
    for(unsigned iteration=0;iteration<4096;iteration++){
        unsigned which=randomWord(seed)%corpus.size();auto candidate=corpus[which];
        unsigned action=iteration%5;
        if(action==0)candidate.resize(randomWord(seed)%(candidate.size()+1));
        else if(action==1){size_t at=randomWord(seed)%candidate.size();candidate[at]^=uint8_t(1u<<(randomWord(seed)&7));}
        else if(action==2){for(unsigned n=0;n<4;n++)candidate[randomWord(seed)%candidate.size()]=uint8_t(randomWord(seed));}
        else if(action==3){candidate.push_back(uint8_t(randomWord(seed)));}
        else {candidate[5]=uint8_t(randomWord(seed));candidate[6]=uint8_t(randomWord(seed));}
        Source source{&candidate};lbg1::Decoder d;
        d.beginCallback(reader,&source,uint16_t(candidate.size()));auto out=run(d);
        require(!source.outside,"Mutation caused out-of-span callback read");
        if(out.error)++rejected;else ++validMutations;++mutations;
        require(d.begin(corpus[which].data(),uint16_t(corpus[which].size())),"Recovery begin failed");
        require(same(run(d),reference[which]),"Recovery after mutation changed output");
    }
    for(unsigned iteration=0;iteration<512;iteration++){
        std::vector<uint8_t> bytes(randomWord(seed)%257);
        for(auto& b:bytes)b=uint8_t(randomWord(seed));
        Source source{&bytes};lbg1::Decoder d;d.beginCallback(reader,&source,uint16_t(bytes.size()));run(d);
        require(!source.outside,"Random input read out of span");++mutations;
    }
    std::cout<<"{\"corpus_files\":"<<corpus.size()<<",\"callback_identity_checks\":"<<callbackChecks
        <<",\"injected_read_failures\":"<<faultChecks<<",\"pwm_contract_samples\":"<<pwmSamples
        <<",\"mutations\":"<<mutations<<",\"rejected_structured_mutations\":"<<rejected
        <<",\"valid_structured_mutations\":"<<validMutations<<",\"recovery_checks\":4096,\"outside_reads\":0}\n";
    return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
