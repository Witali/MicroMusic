// Bounded operators translated from refine_speech_compact.py,
// enhance_speech_compact.py and refine_speech_lpc.py. Strict ties and candidate
// order are intentional; a candidate must pass complete-reference gates.
#include "LpxRefinement.h"
#include <algorithm>
#include <cmath>
#include <deque>
#include <tuple>

namespace lpx {
static Pcm filtered(const std::vector<int>& signal,int pre,int bright) {
    Pcm out(signal.size());int dd=0,cc=0;
    for(size_t i=0;i<signal.size();++i) {
        dd=clamp(signal[i]+((pre*dd)>>14));int clipped=clamp(dd,-16384,16384);
        out[i]=clamp(clamp(clipped-((bright*cc)>>14),-16384,16384)*2,-32768,32767);cc=clipped;
    }
    return out;
}
RefinementResult refineHeader(const Stream& input,const QualityContext& context) {
    RefinementResult result;result.selected=result.raw=input;
    auto co=coefficientTrace(input);SynthesisState state;std::vector<int> signal;
    auto pcm=advance(input,co,0,input.samples,state,&signal);auto before=context.quality(pcm),after=before;
    using Pair=std::pair<int,int>;using Errors=std::pair<uint64_t,uint64_t>;
    struct Row { Pair pair;Errors errors; };
    std::vector<Row> cache;
    auto find=[&](Pair p)->int { for(int i=0;i<int(cache.size());++i)if(cache[i].pair==p)return i;return -1; };
    auto score=[&](Pair p)->int {
        int index=find(p);if(index>=0)return index;
        if(cache.size()>=256 || p.first<0 || p.first>16384 || p.second<0 || p.second>11469)return -1;
        auto out=filtered(signal,p.first,p.second);cache.push_back({p,{sse(context.reference,out),sse(context.reference,pwm(out))}});return cache.size()-1;
    };
    Pair initial(input.pre,input.bright),current=initial;score(initial);
    const int directions[8][2]={{-1,0},{1,0},{0,-1},{0,1},{-1,-1},{-1,1},{1,-1},{1,1}};
    for(int step=2048;step;step/=2)while(cache.size()<256) {
        int best=-1;
        for(const auto& direction:directions) {
            int index=score({current.first+direction[0]*step,current.second+direction[1]*step});
            if(index>=0 && (best<0 || std::tie(cache[index].errors,cache[index].pair)<std::tie(cache[best].errors,cache[best].pair)))best=index;
        }
        if(best<0 || cache[best].errors>=cache[find(current)].errors)break;
        current=cache[best].pair;
    }
    std::vector<int> ranked,eligible;
    for(int i=0;i<int(cache.size());++i)if(cache[i].errors.first<cache[0].errors.first)ranked.push_back(i);
    std::sort(ranked.begin(),ranked.end(),[&](int a,int b) { return std::tie(cache[a].errors,cache[a].pair)<std::tie(cache[b].errors,cache[b].pair); });
    for(int i:ranked)if(cache[i].errors.second<=cache[0].errors.second)eligible.push_back(i);
    std::vector<int> finalists;
    auto append=[&](int i) { if(std::find(finalists.begin(),finalists.end(),i)==finalists.end() && finalists.size()<16)finalists.push_back(i); };
    if(!ranked.empty())append(ranked[0]);
    if(!eligible.empty())for(int i=0;i<16;++i)append(eligible[i*(eligible.size()-1)/15]);
    for(int i:finalists) {
        auto p=cache[i].pair;auto trial=filtered(signal,p.first,p.second);auto measured=context.quality(trial);++result.fullEvaluations;
        Stream candidate=input;candidate.pre=p.first;candidate.bright=p.second;result.alternatives.push_back(candidate);
        if(noRegression(measured,before) && measured.error[0]<after.error[0]) { result.selected=candidate;after=measured; }
    }
    if(!ranked.empty()) { result.raw.pre=cache[ranked[0]].pair.first;result.raw.bright=cache[ranked[0]].pair.second; }
    result.localEvaluations=cache.size();return result;
}
static uint64_t trialLoss(const Stream& s,const std::vector<Coefficients>& co,
                          const Pcm& ref,int at,int stop,const SynthesisState& prefix,Pcm* output=nullptr) {
    auto state=prefix;auto pcm=advance(s,co,at,stop,state);auto loss=sse(ref,pcm,at);
    if(output)*output=std::move(pcm);return loss;
}
RefinementResult enhanceExtras(const Stream& input,const QualityContext& context,int cap) {
    RefinementResult result;result.selected=result.raw=input;
    Stream working=input;for(auto& pulse:working.extras)pulse=Pulse{{-1,0}};
    auto co=coefficientTrace(input); // Frozen for this operator.
    auto initial=context.quality(render(working)),current=initial;
    int capacity=extraCapacity(working,cap,(input.samples+39)/40);
    if(!capacity || !initial.error[0])return result;
    std::vector<Pulse> choices((input.samples+39)/40,Pulse{{-1,0}});
    std::vector<uint64_t> benefits(choices.size());SynthesisState prefix;
    for(int index=0;index<int(choices.size());++index) {
        int at=index*40,stop=std::min(input.samples,at+320);Pcm baseline;
        uint64_t original=trialLoss(working,co,context.reference,at,stop,prefix,&baseline),best=original;
        double scores[40];std::fill(scores,scores+40,-HUGE_VAL);int positions=std::min(40,input.samples-at);
        if(original) {
            for(int pos=0;pos<positions;++pos)for(int amplitude:{-4,4}) {
                working.extras[index]=Pulse{{pos,amplitude}};Pcm out;
                uint64_t loss=trialLoss(working,co,context.reference,at,stop,prefix,&out);++result.localEvaluations;
                double power=0,dot=0;
                for(int j=0;j<int(out.size());++j) { double delta=int(out[j])-int(baseline[j]);power+=delta*delta;dot+=(int(context.reference[at+j])-int(baseline[j]))*delta; }
                int center=clamp(int(std::nearbyint(amplitude*dot/(power+1))),-8,7);double ratio=double(center)/amplitude;
                scores[pos]=std::max(scores[pos],2*ratio*dot-ratio*ratio*power);
                if(loss<best) { best=loss;choices[index]=Pulse{{pos,amplitude}}; }
            }
            for(int candidate=0;candidate<std::min(6,positions);++candidate) {
                int pos=std::max_element(scores,scores+40)-scores;scores[pos]=-HUGE_VAL;
                for(int amplitude=-8;amplitude<=7;++amplitude)if(amplitude) {
                    working.extras[index]=Pulse{{pos,amplitude}};
                    uint64_t loss=trialLoss(working,co,context.reference,at,stop,prefix);++result.localEvaluations;
                    if(loss<best) { best=loss;choices[index]=Pulse{{pos,amplitude}}; }
                }
            }
        }
        benefits[index]=original-best;working.extras[index]=Pulse{{-1,0}};
        advance(working,co,at,std::min(input.samples,at+40),prefix);
    }
    std::vector<int> order;for(int i=0;i<int(benefits.size());++i)if(benefits[i])order.push_back(i);
    std::sort(order.begin(),order.end(),[&](int a,int b) { return benefits[a]!=benefits[b]?benefits[a]>benefits[b]:a<b; });
    for(int start=0;start<int(order.size()) && result.accepted<capacity && result.fullEvaluations<128;start+=16) {
        int count=std::min({16,capacity-result.accepted,int(order.size())-start});
        std::deque<std::vector<int>> todo;todo.emplace_back(order.begin()+start,order.begin()+start+count);
        while(!todo.empty() && result.fullEvaluations<128 && result.accepted<capacity) {
            auto group=todo.front();todo.pop_front();group.resize(std::min(int(group.size()),capacity-result.accepted));if(group.empty())continue;
            Stream trial=working;for(int i:group)trial.extras[i]=choices[i];auto pcm=render(trial);++result.fullEvaluations;
            bool good=sse(context.reference,pcm)<current.error[0];Quality measured;
            if(good) { measured=context.quality(pcm);good=!std::isfinite(current.stoi[0]) || (std::isfinite(measured.stoi[0]) && measured.stoi[0]>=current.stoi[0]-1e-12); }
            if(good) { working=std::move(trial);current=measured;result.accepted+=group.size(); }
            else if(group.size()>1) {
                int mid=group.size()/2;todo.emplace_front(group.begin()+mid,group.end());todo.emplace_front(group.begin(),group.begin()+mid);
            }
        }
    }
    result.selected=result.raw=working;return result;
}
static int activeExtras(const Stream& s) { int active=0;for(const auto& e:s.extras)active+=e[1]!=0;return active; }
static void fitCapacity(Stream& s,int cap,int start) {
    int capacity=extraCapacity(s,cap),active=activeExtras(s);if(active<=capacity)return;
    std::vector<int> order;for(int i=start/40;i<int(s.extras.size());++i)if(s.extras[i][1])order.push_back(i);
    std::sort(order.begin(),order.end(),[&](int a,int b) {
        auto key=[&](int i) { return std::make_tuple(i*40+s.extras[i][0]>=s.samples?0:1,i*40<start+480?0:1,std::abs(s.extras[i][1]),i); };
        return key(a)<key(b);
    });
    for(int i=0;i<std::min(active-capacity,int(order.size()));++i)s.extras[order[i]]=Pulse{{-1,0}};
}
static void adaptExcitation(Stream& s,const std::vector<Coefficients>& co,const Pcm& reference,
                            int start,int end,SynthesisState prefix,int capacity,int& evaluations) {
    int active=activeExtras(s);
    for(int at=start;at<end;at+=40) {
        int stop=std::min(s.samples,at+160);
        if(at%160==0) {
            int index=at/160;auto original=s.parameters[index],best=original;
            auto loss=trialLoss(s,co,reference,at,stop,prefix);++evaluations;
            for(int field=0;field<3;++field)for(int direction:{-1,1}) {
                auto proposal=original;
                proposal[field]=field==0?clamp(original[0]+direction,0,31):field==1?clamp(original[1]+direction,18,145):clamp(original[2]+2*direction,0,14);
                s.parameters[index]=proposal;auto trial=trialLoss(s,co,reference,at,stop,prefix);++evaluations;
                if(trial<loss) { loss=trial;best=proposal; }
            }
            s.parameters[index]=best;
        }
        {
            int index=at/40,valid=std::min(40,s.samples-at);auto original=s.extras[index],best=original;Pcm out;
            auto loss=trialLoss(s,co,reference,at,stop,prefix,&out);++evaluations;
            int peak=0,error=-1;bool positions[40]={};
            for(int j=0;j<valid;++j) { int delta=std::abs(int(reference[at+j])-int(out[j]));if(delta>error) { error=delta;peak=j; } }
            positions[peak]=true;
            if(original[1])for(int delta=-1;delta<=1;++delta) { int p=original[0]+delta;if(p>=0 && p<valid)positions[p]=true; }
            for(int pos=0;pos<valid;++pos)if(positions[pos])for(int amp=-8;amp<=7;++amp) {
                if(!(amp==-4 || amp==-2 || amp==0 || amp==2 || amp==4 || std::abs(amp-original[1])<=1))continue;
                if(amp && !original[1] && active>=capacity)continue;
                s.extras[index]=Pulse{{amp?pos:-1,amp}};
                auto trial=trialLoss(s,co,reference,at,stop,prefix);++evaluations;
                if(trial<loss) { loss=trial;best=s.extras[index]; }
            }
            s.extras[index]=best;active+=int(best[1]!=0)-int(original[1]!=0);
        }
        for(int half=0;half<2;++half) {
            int begin=at+half*20;if(begin>=end)break;stop=std::min(s.samples,begin+160);
            int index=begin/20;auto original=s.pulses[index],best=original;
            auto loss=trialLoss(s,co,reference,begin,stop,prefix);++evaluations;
            for(int pos=std::max(0,original[0]-2);pos<std::min({20,s.samples-begin,original[0]+3});++pos) {
                if(s.profile==4 && pos%5==2)continue;
                for(int amp=-8;amp<=8;++amp) {
                    if(s.profile==4?(amp!=-8 && amp!=8):(amp>7 || std::abs(amp-original[1])>2))continue;
                    s.pulses[index]=Pulse{{pos,amp}};auto trial=trialLoss(s,co,reference,begin,stop,prefix);++evaluations;
                    if(trial<loss) { loss=trial;best=s.pulses[index]; }
                }
            }
            s.pulses[index]=best;advance(s,co,begin,std::min(end,begin+20),prefix);
        }
    }
}
static std::vector<int> frameOrder(const Pcm& reference,const Pcm& pcm) {
    int frames=(reference.size()+319)/320;std::vector<int> ranked(frames);std::vector<uint64_t> losses(frames);
    for(int i=0;i<frames;++i) { ranked[i]=i;for(int j=i*320;j<std::min(int(reference.size()),i*320+320);++j) { int64_t d=int(reference[j])-int(pcm[j]);losses[i]+=d*d; } }
    if(frames<=64)return ranked;
    std::sort(ranked.begin(),ranked.end(),[&](int a,int b) { return losses[a]!=losses[b]?losses[a]>losses[b]:a<b; });
    std::vector<int> selected(ranked.begin(),ranked.begin()+32);
    for(int i=0;i<32;++i) { int f=i*(frames-1)/31;if(std::find(selected.begin(),selected.end(),f)==selected.end())selected.push_back(f); }
    for(int f:ranked) { if(selected.size()>=64)break;if(std::find(selected.begin(),selected.end(),f)==selected.end())selected.push_back(f); }
    std::sort(selected.begin(),selected.end());return selected;
}
RefinementResult refineLpc(const Stream& input,const QualityContext& context,int cap) {
    RefinementResult result;result.selected=result.raw=input;
    Stream working=input;auto co=coefficientTrace(working);auto pcm=render(working);
    auto before=context.quality(pcm),after=before;uint64_t rawLoss=before.error[0];
    for(int pass=0;pass<2 && before.error[0];++pass) {
        int changes=0;
        for(int frame:frameOrder(context.reference,pcm)) {
            int start=frame*320,stop=std::min(input.samples,start+1280);SynthesisState prefix;
            advance(working,co,0,start,prefix);
            struct Proposal { uint64_t loss;int field,delta; };
            std::vector<Proposal> proposals;
            for(int field=0;field<10;++field)for(int delta:{-1,1}) {
                Stream trial=working;auto& vec=trial.spectra[frame];vec[field]+=delta;
                if(vec[field]<0 || vec[field]>=(input.profile==4?32:64) || (field && vec[field]<=vec[field-1]) || (field<9 && vec[field]>=vec[field+1]))continue;
                auto trialCo=coefficientTrace(trial);auto loss=trialLoss(trial,trialCo,context.reference,start,stop,prefix);++result.localEvaluations;
                proposals.push_back({loss,field,delta});
            }
            std::sort(proposals.begin(),proposals.end(),[](const Proposal& a,const Proposal& b) { return std::tie(a.loss,a.field,a.delta)<std::tie(b.loss,b.field,b.delta); });
            for(int i=0;i<std::min(4,int(proposals.size()));++i) {
                Stream trial=working;trial.spectra[frame][proposals[i].field]+=proposals[i].delta;
                auto trialCo=coefficientTrace(trial);fitCapacity(trial,cap,start);if(compactBytes(trial)>cap)continue;
                int capacity=extraCapacity(trial,cap);
                adaptExcitation(trial,trialCo,context.reference,start,std::min(input.samples,start+480),prefix,capacity,result.localEvaluations);
                auto state=prefix;auto suffix=advance(trial,trialCo,start,input.samples,state);
                Pcm actual(pcm.begin(),pcm.begin()+start);actual.insert(actual.end(),suffix.begin(),suffix.end());
                auto loss=sse(context.reference,actual);if(loss>=after.error[0])continue;
                if(compactBytes(trial)>cap)continue;
                auto measured=context.quality(actual);++result.fullEvaluations;bool allowed=noRegression(measured,before);
                if(loss<rawLoss) { rawLoss=loss;result.raw=trial; }
                if(allowed) { working=std::move(trial);co=std::move(trialCo);pcm=std::move(actual);after=measured;++changes;++result.accepted;break; }
            }
        }
        if(!changes)break;
    }
    result.selected=working;return result;
}
static bool completeGate(const Measurement& next,const Measurement& baseline) {
    return next.score<=baseline.score+1e-12 && noRegression(next.quality,baseline.quality)
        && next.clipped<=baseline.clipped
        && next.diagnostic[0].within>=baseline.diagnostic[0].within
        && next.diagnostic[1].within>=baseline.diagnostic[1].within;
}
RefinementResult refinePitchGain(const Stream& input,const QualityContext& context,int cap) {
    RefinementResult result;result.selected=result.raw=input;
    auto co=coefficientTrace(input);auto pcm=render(input);auto baseline=context.measure(pcm);
    if(!baseline.quality.error[0] || compactBytes(input)>cap)return result;
    // LPC-whiten the actual reference, using the stream's frozen coefficient
    // trace. Autocorrelation only proposes periods; integer synthesis decides.
    std::vector<double> residual(input.samples),emphasized(input.samples);
    for(int at=0;at<input.samples;++at) {
        emphasized[at]=double(context.reference[at])/2-input.pre*(at?double(context.reference[at-1])/2:0)/16384;
        residual[at]=emphasized[at];
        for(int k=0;k<10 && k<at;++k)residual[at]+=co[at/20][k]*emphasized[at-k-1]/4096;
    }
    Stream working=input;uint64_t rawLoss=baseline.quality.error[0];
    for(int pass=0;pass<2;++pass) {
        bool changed=false;
        // At most 64 distributed/high-error 320-sample anchors: fixed work on
        // long recordings, with no reset or output-file subdivision.
        auto anchors=frameOrder(context.reference,pcm);
        for(int frame:anchors)for(int half=0;half<2;++half) {
            int at=frame*320+half*160;if(at>=input.samples)break;
            int index=at/160,stop=std::min(input.samples,at+320);SynthesisState prefix;
            advance(working,co,0,at,prefix);
            auto original=working.parameters[index];
            struct Period { double score;int lag; };
            std::vector<Period> periods;
            for(int lag=18;lag<=145;++lag) {
                double dot=0,energy=0;
                for(int j=at;j<std::min(input.samples,at+160);++j)if(j>=lag) {
                    dot+=residual[j]*residual[j-lag];energy+=residual[j-lag]*residual[j-lag];
                }
                periods.push_back({dot>0?dot*dot/(energy+1):0,lag});
            }
            std::sort(periods.begin(),periods.end(),[](const Period& a,const Period& b) {
                return a.score!=b.score?a.score>b.score:a.lag<b.lag;
            });
            std::vector<int> lags;
            auto lagChoice=[&](int lag) { if(lag>=18 && lag<=145 && std::find(lags.begin(),lags.end(),lag)==lags.end())lags.push_back(lag); };
            lagChoice(original[1]);for(int delta:{-2,-1,1,2})lagChoice(original[1]+delta);
            for(int i=0;i<3;++i)for(int delta:{0,-1,1})lagChoice(periods[i].lag+delta);
            struct Proposal { uint64_t loss;Parameters parameters; };
            std::vector<Proposal> proposals;
            auto originalLoss=trialLoss(working,co,context.reference,at,stop,prefix);++result.localEvaluations;
            // All eight representable pitch gains, jointly with nearby scale
            // values and several periods, rather than one open-loop estimate.
            for(int scale: {original[0],clamp(original[0]-1,0,31),clamp(original[0]+1,0,31)})
                for(int lag:lags)for(int gain=0;gain<=14;gain+=2) {
                    if(gain==0 && lag!=lags[0])continue;
                    Parameters p={{scale,lag,gain}};
                    if(p==original)continue;
                    working.parameters[index]=p;
                    auto loss=trialLoss(working,co,context.reference,at,stop,prefix);++result.localEvaluations;
                    if(loss<originalLoss)proposals.push_back({loss,p});
                }
            working.parameters[index]=original;
            std::sort(proposals.begin(),proposals.end(),[](const Proposal& a,const Proposal& b) {
                return std::tie(a.loss,a.parameters)<std::tie(b.loss,b.parameters);
            });
            if(proposals.empty())continue;
            // Refit excitation on four finalists with 160-sample lookahead.
            // Only a 160-sample block is copied; whole streams are not cloned
            // for every local parameter trial.
            std::array<Pulse,8> originalPulses,bestPulses;
            std::array<Pulse,4> originalExtras,bestExtras;
            for(int j=0;j<8;++j)originalPulses[j]=working.pulses[index*8+j];
            for(int j=0;j<4;++j)originalExtras[j]=working.extras[index*4+j];
            auto bestParameters=original;uint64_t bestLoss=originalLoss;
            for(int choice=0;choice<std::min(4,int(proposals.size()));++choice) {
                working.parameters[index]=proposals[choice].parameters;
                for(int j=0;j<8;++j)working.pulses[index*8+j]=originalPulses[j];
                for(int j=0;j<4;++j)working.extras[index*4+j]=originalExtras[j];
                adaptExcitation(working,co,context.reference,at,std::min(input.samples,at+160),prefix,extraCapacity(working,cap),result.localEvaluations);
                auto loss=trialLoss(working,co,context.reference,at,stop,prefix);++result.localEvaluations;
                if(loss<bestLoss && compactBytes(working)<=cap) {
                    bestLoss=loss;bestParameters=working.parameters[index];
                    for(int j=0;j<8;++j)bestPulses[j]=working.pulses[index*8+j];
                    for(int j=0;j<4;++j)bestExtras[j]=working.extras[index*4+j];
                }
            }
            working.parameters[index]=bestParameters;
            for(int j=0;j<8;++j)working.pulses[index*8+j]=bestLoss<originalLoss?bestPulses[j]:originalPulses[j];
            for(int j=0;j<4;++j)working.extras[index*4+j]=bestLoss<originalLoss?bestExtras[j]:originalExtras[j];
            changed|=bestLoss<originalLoss;
        }
        if(!changed)break;
        pcm=render(working);auto loss=sse(context.reference,pcm);
        auto measured=context.measure(pcm);++result.fullEvaluations;
        if(compactBytes(working)<=cap && completeGate(measured,baseline)) {
            if(loss<rawLoss) { rawLoss=loss;result.raw=working; }
            result.alternatives.push_back(working);
            result.selected=working;++result.accepted;
        }
    }
    return result;
}
}
