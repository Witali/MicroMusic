// Experimental LG1 encoder. Exact anchor conversion/reference synthesis are
// derived from the project's production LpxAdaptiveDsp.cpp; no vendor code.
#include "encoder.h"
#include "LpxLpcStability.h"
#include <algorithm>
#include <cmath>
#include <fstream>
#include <limits>
#include <stdexcept>

namespace lbg1 { namespace {
using Co=lpx::Coefficients;
const double inf=std::numeric_limits<double>::infinity();
static const int16_t cosine[]={
#include "cos_table.inc"
};
static const uint16_t scaleTable[]={
#include "scale_table.inc"
};
static const int16_t logStarts[32]={-1,-1,-1,-1,-1,-1,0,0,0,0,256,406,512,662,768,918,1024,1158,1291,1414,1547,1674,1801,1928,2057,2185,2313,2441,2569,2697,2825,2953};
static const uint16_t exp2Table[17]={4096,4277,4467,4664,4871,5087,5312,5547,5793,6049,6317,6597,6889,7194,7512,7845,8192};
int clip(int v,int low=-32767,int high=32767){return std::max(low,std::min(high,v));}
void validateSource(const lpx::Stream& s){
    if(s.continuation||s.samples<1||s.samples>64000||s.rate!=8000||(s.profile!=4&&s.profile!=6)||s.pre<0||s.pre>16384||s.bright<0||s.bright>11469)
        throw std::runtime_error("Invalid standalone LG1 model metadata");
    const size_t frames=(s.samples+319)/320;
    if(s.spectra.size()!=frames||s.parameters.size()!=frames*2||s.pulses.size()!=frames*16||s.extras.size()!=frames*8)
        throw std::runtime_error("LG1 requires complete padded model arrays");
    if(s.initial.dd||s.initial.cc)throw std::runtime_error("LG1 standalone initial state must be zero");
    for(int v:s.initial.h)if(v)throw std::runtime_error("LG1 standalone history must be zero");
    for(int v:s.initial.ring)if(v)throw std::runtime_error("LG1 standalone excitation history must be zero");
    const int alphabet=s.profile==4?32:64;
    for(const auto& v:s.spectra)for(int j=0;j<10;j++)if(v[j]<0||v[j]>=alphabet||(j&&v[j]<=v[j-1]))throw std::runtime_error("Invalid LG1 source spectrum");
    for(const auto& p:s.parameters)if(p[0]<0||p[0]>31||p[1]<18||p[1]>145||p[2]<0||p[2]>14||(p[2]&1))throw std::runtime_error("Invalid LG1 source pitch/scale");
    for(const auto& p:s.pulses){
        if(p[0]<0||p[0]>=20||p[1]<-8||p[1]>(s.profile==4?8:7))throw std::runtime_error("Invalid LG1 source pulse");
        if(s.profile==4){int ordinal=p[0]-(p[0]+2)/5;if(ordinal+(ordinal+2)/4!=p[0]||(p[1]!=-8&&p[1]!=8))throw std::runtime_error("Invalid LG1 P4 pulse");}
    }
    for(const auto& e:s.extras)if(e[1]<-8||e[1]>7||(e[1]&&(e[0]<0||e[0]>=40)))throw std::runtime_error("Invalid LG1 source extra pulse");
}
int trajectoryStep(int q){
    if(q<0||q>3071)throw std::runtime_error("Log trajectory outside Q8 domain");
    const int node=(q&255)>>4,frac=q&15;
    const int base=exp2Table[node]+((int(exp2Table[node+1]-exp2Table[node])*frac+8)>>4);
    return (base*(1<<(q>>8))+2048)>>12;
}
struct Bits {
    std::vector<uint8_t> bytes;uint64_t count=0;
    void put(uint32_t value,int width){
        if(width<0||width>24||(width<24&&value>=(uint32_t(1)<<width)))throw std::runtime_error("Bit field does not fit");
        for(int i=0;i<width;i++,count++){
            if(!(count&7))bytes.push_back(0);
            bytes.back()|=((value>>i)&1)<<(count&7);
        }
    }
    void signedBits(int value,int width){put(uint32_t(value)&((uint32_t(1)<<width)-1),width);}
    void run(int length){
        if(length<1||length>400)throw std::runtime_error("Run length out of range");
        int z=0;while((1<<(z+1))<=length)++z;
        put(0,z);put(1,1);put(length-(1<<z),z);
    }
};
int runBits(int length){int z=0;while((1<<(z+1))<=length)++z;return 2*z+1;}
int polyMul(int value,int c){
    if(value>=-250000&&value<=250000)return (value*c)>>12;
    const int hi=value/16;return ((hi*c)>>8)+(((value-hi*16)*c)>>12);
}
Co anchor(const lpx::Spectrum& previous,const lpx::Spectrum& current,int profile,int t){
    int p[2][12]={{4096,4096},{4096,-4096}},shift=profile==4?5:4;
    for(int j=0;j<10;j++){
        int a=(previous[j]<<shift)+(1<<(shift-1)),b=(current[j]<<shift)+(1<<(shift-1));
        int norm=(a*(16-t)+b*t)>>2,index=norm>>4,frac=norm&15;
        int c=-(cosine[index]+(((cosine[index+1]-cosine[index])*frac)>>4));
        int* q=p[j&1];int n=2+j/2*2;
        q[n+1]=q[n-1];q[n]=q[n-2]+polyMul(q[n-1],c);
        for(int k=n-1;k>1;k--)q[k]=q[k-2]+polyMul(q[k-1],c)+q[k];
        q[1]+=polyMul(q[0],c);
    }
    Co out{};for(int j=0;j<10;j++)out[j]=clip((p[0][j+1]+p[1][j+1])/2);return out;
}
Co interpolate(const Co& a,const Co& b,int t){
    Co out{};for(int j=0;j<10;j++)out[j]=clip(a[j]+(int(b[j])-a[j])*t/8);return out;
}
int maxError(const Co& a,const Co& b){int result=0;for(int j=0;j<10;j++)result=std::max(result,std::abs(int(a[j])-b[j]));return result;}
struct Group {
    int begin=0,length=0,code=5,exponent=0,width=16,bits=0;
    int values[10]={};uint64_t error=0;Co decoded{};
};
int roundDivide(int value,int denominator){return value>=0?(value+denominator/2)/denominator:-((-value+denominator/2)/denominator);}
Group rawGroup(const Co& target,int begin,int length){
    Group g;g.begin=begin;g.length=length;g.code=5;g.width=16;g.bits=3+16*length;
    for(int j=begin;j<begin+length;j++)g.values[j-begin]=g.decoded[j]=target[j];return g;
}
Group bestGroup(const Co& target,const Co& base,int begin,int length,int tolerance,bool bfp){
    Group best=rawGroup(target,begin,length);
    if(!bfp)return best;
    Group zero;zero.begin=begin;zero.length=length;zero.code=6;zero.width=0;zero.bits=3;
    bool zeroFits=true;
    for(int j=begin;j<begin+length;j++){
        int d=int(base[j])-target[j];zeroFits=zeroFits&&std::abs(d)<=tolerance;zero.error+=int64_t(d)*d;zero.decoded[j]=base[j];
    }
    if(zeroFits)best=zero;
    const int widths[]={4,6,8,10,12};
    for(int code=0;code<5;code++)for(int e=0;e<=15;e++){
        Group g;g.begin=begin;g.length=length;g.code=code;g.exponent=e;g.width=widths[code];g.bits=7+length*g.width;
        if(g.bits>best.bits)continue;
        const int den=1<<e,lo=-(1<<(g.width-1)),hi=(1<<(g.width-1))-1;
        bool fits=true;
        for(int j=begin;j<begin+length;j++){
            int m=roundDivide(int(target[j])-base[j],den);m=clip(m,lo,hi);
            int restored=int(base[j])+m*den;
            if(restored< -32767||restored>32767){fits=false;break;}
            int d=restored-target[j];if(std::abs(d)>tolerance){fits=false;break;}
            g.values[j-begin]=m;g.decoded[j]=int16_t(restored);g.error+=int64_t(d)*d;
        }
        if(fits&&(g.bits<best.bits||(g.bits==best.bits&&g.error<best.error)))best=g;
    }
    return best;
}
struct VectorPacket {int plan=0,bits=1;bool changed=false;Co decoded{};std::vector<Group> groups;};
VectorPacket fixedPlan(const Co& target,const Co& base,int plan,int tolerance,bool bfp){
    VectorPacket v;v.plan=plan;v.changed=true;v.bits=3;v.decoded=base;
    const int group=plan==0?10:plan==1?5:2;
    for(int i=0;i<10;i+=group){
        auto g=bestGroup(target,base,i,group,tolerance,bfp);v.groups.push_back(g);v.bits+=g.bits;
        for(int j=i;j<i+group;j++)v.decoded[j]=g.decoded[j];
    }
    return v;
}
VectorPacket customPlan(const Co& target,const Co& base,int tolerance){
    int cost[11];Group choices[10];int lengths[10];cost[10]=0;
    for(int i=9;i>=0;i--){
        cost[i]=100000;
        for(int n=1;n<=10-i;n++){
            auto g=bestGroup(target,base,i,n,tolerance,true);int c=4+g.bits+cost[i+n];
            if(c<cost[i]){cost[i]=c;choices[i]=g;lengths[i]=n;}
        }
    }
    VectorPacket v;v.plan=3;v.changed=true;v.bits=3+cost[0];v.decoded=base;
    for(int i=0;i<10;i+=lengths[i]){
        v.groups.push_back(choices[i]);for(int j=i;j<i+lengths[i];j++)v.decoded[j]=choices[i].decoded[j];
    }
    return v;
}
std::vector<VectorPacket> vectorChoices(const Co& target,const Co& base,int tolerance,bool bfp){
    std::vector<VectorPacket> choices;
    if(maxError(target,base)<=tolerance){VectorPacket v;v.decoded=base;choices.push_back(v);}
    choices.push_back(fixedPlan(target,base,0,tolerance,bfp));
    if(bfp){
        choices.push_back(fixedPlan(target,base,1,tolerance,true));
        choices.push_back(fixedPlan(target,base,2,tolerance,true));
        choices.push_back(customPlan(target,base,tolerance));
        choices.push_back(fixedPlan(target,base,0,0,false));
    }
    std::stable_sort(choices.begin(),choices.end(),[](const VectorPacket& a,const VectorPacket& b){return a.bits<b.bits;});
    return choices;
}
bool stableSegment(const Co& a,const Co& b,int samples){
    for(int at=0;at<samples;at+=20)if(!lpxStableLpc(interpolate(a,b,2*(at/20)+1).data()))return false;
    return true;
}
struct Frame {bool changed=false,initial=false;Co start{},middle{},end{};VectorPacket first,second;};
bool selectFrame(Frame& frame,const Co& targetMiddle,const Co& targetEnd,const Co& base,
                 bool initial,int samples,int tolerance,bool bfp){
    frame=Frame{};frame.initial=initial;frame.start=base;
    if(!initial&&maxError(targetMiddle,base)<=tolerance&&maxError(targetEnd,base)<=tolerance&&lpxStableLpc(base.data())){
        frame.middle=frame.end=base;return true;
    }
    int best=100000;
    auto firsts=vectorChoices(initial?targetEnd:targetMiddle,base,tolerance,bfp);
    for(const auto& first:firsts){
        if(initial){
            if(!lpxStableLpc(first.decoded.data()))continue;
            if(first.bits<best){best=first.bits;frame.changed=true;frame.first=first;frame.middle=frame.end=first.decoded;}
            continue;
        }
        if(!stableSegment(base,first.decoded,std::min(samples,80)))continue;
        if(samples<=80){
            if(first.bits<best){best=first.bits;frame.changed=true;frame.first=first;frame.middle=frame.end=first.decoded;}
            continue;
        }
        for(const auto& second:vectorChoices(targetEnd,first.decoded,tolerance,bfp)){
            if(!stableSegment(first.decoded,second.decoded,std::min(80,samples-80)))continue;
            if(samples>160&&!lpxStableLpc(second.decoded.data()))continue;
            if(first.bits+second.bits<best){best=first.bits+second.bits;frame.changed=true;frame.first=first;frame.second=second;frame.middle=first.decoded;frame.end=second.decoded;}
        }
    }
    return best<100000;
}
void writeVector(Bits& w,const VectorPacket& v,EncoderStats& stats){
    w.put(v.changed,1);if(!v.changed){++stats.repeatAnchors;return;}
    w.put(v.plan,2);++stats.planCounts[v.plan];
    for(const auto& g:v.groups){
        if(v.plan==3)w.put(g.length-1,4);
        w.put(g.code,3);++stats.widthCounts[g.code];
        if(g.code<5){w.put(g.exponent,4);++stats.exponentCounts[g.exponent];}
        if(g.code==6)continue;
        for(int j=0;j<g.length;j++)w.signedBits(g.values[j],g.width);
    }
}
struct Command {int mode,length,start,slope;Command(int m=0,int n=1,int s=0,int d=0):mode(m),length(n),start(s),slope(d){}};
struct CommandPlan {std::vector<Command> commands;std::vector<int> values;};
double levelError(int predicted,int actual){
    if(!predicted||!actual)return predicted==actual?0:inf;
    return std::abs(20*std::log10(double(predicted)/actual));
}
CommandPlan scalePlan(const lpx::Stream& s,bool trajectories,double tolerance){
    int n=(s.samples+159)/160;CommandPlan plan;plan.commands.resize(n);plan.values.resize(n);
    std::vector<int> best(n+1,0);
    for(int i=n-1;i>=0;i--){
        auto& choice=plan.commands[i];choice.start=s.parameters[i][0];best[i]=7+best[i+1];
        if(!trajectories)continue;
        for(int length=2;length<=n-i;length++){
            int cost=2+runBits(length)+5*length+best[i+length];
            if(cost<best[i]){best[i]=cost;choice=Command{3,length,s.parameters[i][0],0};}
        }
        bool sameBoundary=true,constantFits=true;
        for(int length=2;length<=n-i;length++){
            int end=i+length-1;
            sameBoundary=sameBoundary&&((s.parameters[end][2]==0)==(s.parameters[i][2]==0));
            if(!sameBoundary)break;
            constantFits=constantFits&&levelError(scaleTable[s.parameters[i][0]*8],scaleTable[s.parameters[end][0]*8])<=tolerance+1e-12;
            if(constantFits){
                int cost=7+runBits(length)+best[i+length];
                if(cost<best[i]){best[i]=cost;choice=Command{1,length,s.parameters[i][0],0};}
            }
            int q0=logStarts[s.parameters[i][0]],qe=logStarts[s.parameters[end][0]];
            if(q0<0||qe<0)continue;
            const double slopeExact=double(qe-q0)/(length-1);
            const int center=int(std::lround(slopeExact));
            for(int slope=center-1;slope<=center+1;slope++){
                if(slope< -2048||slope>2047)continue;
                int last=q0+(length-1)*slope;if(last<0||last>3071)continue;
                bool fits=true;
                for(int j=0;j<length;j++)if(levelError(trajectoryStep(q0+j*slope),scaleTable[s.parameters[i+j][0]*8])>tolerance+1e-12){fits=false;break;}
                if(fits){
                    int cost=19+runBits(length)+best[i+length];
                    if(cost<best[i]){best[i]=cost;choice=Command{2,length,s.parameters[i][0],slope};}
                }
            }
        }
    }
    for(int i=0;i<n;){
        const auto& c=plan.commands[i];
        for(int j=0;j<c.length;j++)plan.values[i+j]=c.mode==2?trajectoryStep(logStarts[c.start]+j*c.slope):scaleTable[(c.mode==3?s.parameters[i+j][0]:c.start)*8];
        i+=c.length;
    }
    return plan;
}
int pitchFieldBits(const lpx::Parameters& p){return 3+(p[2]?7:0);}
CommandPlan pitchPlan(const lpx::Stream& s,bool trajectories){
    int n=(s.samples+159)/160;CommandPlan plan;plan.commands.resize(n);std::vector<int> best(n+1,0),rawPrefix(n+1,0);
    for(int i=0;i<n;i++)rawPrefix[i+1]=rawPrefix[i]+pitchFieldBits(s.parameters[i]);
    for(int i=n-1;i>=0;i--){
        auto& choice=plan.commands[i];choice.start=s.parameters[i][1];best[i]=2+pitchFieldBits(s.parameters[i])+best[i+1];
        if(!trajectories)continue;
        for(int length=2;length<=n-i;length++){
            int cost=2+runBits(length)+rawPrefix[i+length]-rawPrefix[i]+best[i+length];
            if(cost<best[i]){best[i]=cost;choice=Command{3,length,s.parameters[i][1],0};}
        }
        bool constant=true,linear=true;
        int slope=i+1<n?s.parameters[i+1][1]-s.parameters[i][1]:0;
        for(int length=2;length<=n-i;length++){
            int end=i+length-1;
            if(s.parameters[end][2]!=s.parameters[i][2])break;
            constant=constant&&(!s.parameters[i][2]||s.parameters[end][1]==s.parameters[i][1]);
            if(constant){int cost=2+pitchFieldBits(s.parameters[i])+runBits(length)+best[i+length];
                if(cost<best[i]){best[i]=cost;choice=Command{1,length,s.parameters[i][1],0};}}
            linear=linear&&s.parameters[i][2]!=0&&slope>=-128&&slope<=127&&s.parameters[end][1]==s.parameters[i][1]+(length-1)*slope;
            if(linear){int cost=20+runBits(length)+best[i+length];
                if(cost<best[i]){best[i]=cost;choice=Command{2,length,s.parameters[i][1],slope};}}
        }
    }
    return plan;
}
void pitchLiteral(Bits& w,const lpx::Parameters& p){w.put(p[2]/2,3);if(p[2])w.put(p[1]-18,7);}
int16_t referenceSample(const lpx::Stream& source,const std::vector<Co>& co,const std::vector<int>& steps,
                        lpx::SynthesisState& state,int j,int pulsePosition,int pulseAmplitude){
    const auto& p=source.parameters[j/160];const auto& extra=source.extras[j/40];
    int q=clip((p[2]*state.ring[(j-p[1])&255]+8)>>4,-32,31);
    q=clip(q+(j%20==pulsePosition?pulseAmplitude:0)+(j%40==extra[0]?extra[1]:0),-32,31);state.ring[j&255]=q;
    int acc=0;for(int k=0;k<10;k++)acc+=(co[j/20][k]*state.h[k])>>12;
    int value=clip(q*steps[j/160]-acc);
    for(int k=9;k;k--)state.h[k]=state.h[k-1];state.h[0]=value;
    state.dd=clip(value+((source.pre*state.dd)>>14));int c=clip(state.dd,-16384,16384);
    int out=clip(c-((source.bright*state.cc)>>14),-16384,16384);state.cc=c;return int16_t(clip(out*2,-32768,32767));
}
}

EncoderOptions variant(const std::string& name){
    EncoderOptions o;
    if(name=="exact")return o;
    if(name=="bfp-exact"){o.groupedBfp=true;return o;}
    if(name=="bfp-quality"){o.groupedBfp=true;o.coefficientError=8;return o;}
    if(name=="bfp-compact"){o.groupedBfp=true;o.coefficientError=32;return o;}
    if(name=="trajectory-quality"){o.trajectories=true;o.levelErrorDb=.05;return o;}
    if(name=="trajectory-compact"){o.trajectories=true;o.levelErrorDb=.25;return o;}
    if(name=="combined-quality"){o.groupedBfp=o.trajectories=true;o.coefficientError=8;o.levelErrorDb=.05;return o;}
    if(name=="combined-compact"){o.groupedBfp=o.trajectories=true;o.coefficientError=32;o.levelErrorDb=.25;return o;}
    throw std::runtime_error("Unknown LG1 experiment variant");
}

lpx::Stream readModel(const std::string& path){
    std::ifstream f(path);lpx::Stream s;
    if(!(f>>s.samples>>s.profile>>s.pre>>s.bright)||s.samples<1||s.samples>64000||(s.profile!=4&&s.profile!=6)||s.pre<0||s.pre>16384||s.bright<0||s.bright>11469)throw std::runtime_error("Invalid model header");
    int frames=(s.samples+319)/320;
    s.spectra.resize(frames);s.parameters.resize(frames*2);s.pulses.resize(frames*16);s.extras.resize(frames*8);
    const int alphabet=s.profile==4?32:64;
    for(auto& v:s.spectra)for(int j=0;j<10;j++)if(!(f>>v[j])||v[j]<0||v[j]>=alphabet||(j&&v[j]<=v[j-1]))throw std::runtime_error("Invalid model spectrum");
    for(auto& p:s.parameters){for(int& x:p)if(!(f>>x))throw std::runtime_error("Missing block parameter");
        if(p[0]<0||p[0]>31||p[1]<18||p[1]>145||p[2]<0||p[2]>14||(p[2]&1))throw std::runtime_error("Invalid block parameter");}
    for(auto& p:s.pulses){if(!(f>>p[0]>>p[1])||p[0]<0||p[0]>=20||p[1]<-8||p[1]>8)throw std::runtime_error("Invalid pulse");
        if(s.profile==4){int encoded=p[0]-(p[0]+2)/5;if(encoded+(encoded+2)/4!=p[0]||(p[1]!=-8&&p[1]!=8))throw std::runtime_error("Invalid P4 pulse");}
        else if(p[1]>7)throw std::runtime_error("Invalid P6 amplitude");}
    for(auto& e:s.extras)if(!(f>>e[0]>>e[1])||e[1]<-8||e[1]>7||(e[1]&&(e[0]<0||e[0]>=40)))throw std::runtime_error("Invalid extra pulse");
    f>>std::ws;if(!f.eof())throw std::runtime_error("Trailing model text");return s;
}

EncoderResult encode(const lpx::Stream& source,const EncoderOptions& options){
    validateSource(source);
    if(options.coefficientError<0||options.coefficientError>32||!std::isfinite(options.levelErrorDb)||options.levelErrorDb<0||options.levelErrorDb>.25
       ||(!options.groupedBfp&&options.coefficientError)||(!options.trajectories&&options.levelErrorDb))throw std::runtime_error("Unsupported experimental error budget");
    if(source.accuracy==3){auto canonical=lpx::canonicalAccuracy(source);canonical.accuracy=0;return encode(canonical,options);}
    const int frameCount=(source.samples+319)/320,blockCount=(source.samples+159)/160;
    std::vector<Co> middles(frameCount),ends(frameCount);
    for(int f=0;f<frameCount;f++){
        const auto& previous=source.spectra[f?f-1:0];
        middles[f]=anchor(previous,source.spectra[f],source.profile,8);ends[f]=anchor(previous,source.spectra[f],source.profile,16);
    }
    std::vector<bool> forced(frameCount,false);std::vector<Frame> frames(frameCount);
    for(int attempt=0;attempt<=frameCount;attempt++){
        Co previous{};int failed=-1;
        for(int f=0;f<frameCount;f++){
            int samples=std::min(320,source.samples-f*320);
            if(!selectFrame(frames[f],middles[f],ends[f],previous,f==0,samples,forced[f]?0:options.coefficientError,options.groupedBfp&&!forced[f])){failed=f;break;}
            previous=frames[f].end;
        }
        if(failed<0)break;
        bool progress=!forced[failed]||(failed&&!forced[failed-1]);forced[failed]=true;if(failed)forced[failed-1]=true;
        if(!progress||attempt==frameCount)throw std::runtime_error("No stable anchor path, including exact fallback");
    }
    EncoderResult result;result.stats.forcedRawFrames=std::count(forced.begin(),forced.end(),true);
    result.coefficients.resize((source.samples+19)/20);
    for(int j=0;j<int(result.coefficients.size());j++){
        int at=j*20,f=at/320,within=at%320;const auto& frame=frames[f];
        result.coefficients[j]=!frame.changed||frame.initial||within>=160?frame.end:
            within<80?interpolate(frame.start,frame.middle,2*(within/20)+1):interpolate(frame.middle,frame.end,2*((within-80)/20)+1);
        if(!lpxStableLpc(result.coefficients[j].data()))throw std::runtime_error("Unstable rendered coefficient vector");
    }
    const auto original=lpx::coefficientTrace(source);
    if(original.size()!=result.coefficients.size())throw std::runtime_error("Coefficient trace length mismatch");
    for(size_t i=0;i<original.size();i++)for(int k=0;k<10;k++){
        int error=std::abs(int(original[i][k])-result.coefficients[i][k]);result.stats.coefficientMaxError=std::max(result.stats.coefficientMaxError,error);result.stats.changedCoefficients+=error!=0;
    }
    if(!options.groupedBfp&&original!=result.coefficients)throw std::runtime_error("Exact anchor representation differs from production");
    auto scales=scalePlan(source,options.trajectories,options.levelErrorDb);auto pitches=pitchPlan(source,options.trajectories);
    result.excitationSteps=scales.values;
    for(int i=0;i<blockCount;i++)result.stats.maximumLevelErrorDb=std::max(result.stats.maximumLevelErrorDb,levelError(scales.values[i],scaleTable[source.parameters[i][0]*8]));
    bool enhanced=false;for(const auto& e:source.extras)enhanced=enhanced||e[1]!=0;
    Bits w;int scaleStart=0,scaleNext=0,pitchStart=0,pitchNext=0;
    for(int at=0;at<source.samples;at+=40){
        int f=at/320,within=at%320;
        uint64_t before=w.count;
        if(within==0){w.put(frames[f].changed,1);if(frames[f].changed)writeVector(w,frames[f].first,result.stats);else ++result.stats.repeatFrames;}
        if(within==80&&frames[f].changed&&!frames[f].initial)writeVector(w,frames[f].second,result.stats);
        result.stats.spectrumBits+=w.count-before;
        if(at%160==0){
            int b=at/160;before=w.count;
            if(b==scaleNext){scaleStart=b;const auto& c=scales.commands[b];w.put(c.mode,2);++result.stats.scaleCommands[c.mode];
                if(c.mode==3)w.run(c.length);else{w.put(c.start,5);if(c.mode==2)w.signedBits(c.slope,12);if(c.mode==1||c.mode==2)w.run(c.length);}scaleNext=b+c.length;}
            if(scales.commands[scaleStart].mode==3)w.put(source.parameters[b][0],5);
            result.stats.scaleBits+=w.count-before;before=w.count;
            if(b==pitchNext){pitchStart=b;const auto& c=pitches.commands[b];w.put(c.mode,2);++result.stats.pitchCommands[c.mode];
                if(c.mode==3)w.run(c.length);else{pitchLiteral(w,source.parameters[b]);if(c.mode==2)w.signedBits(c.slope,8);if(c.mode==1||c.mode==2)w.run(c.length);}pitchNext=b+c.length;}
            if(pitches.commands[pitchStart].mode==3)pitchLiteral(w,source.parameters[b]);
            result.stats.pitchBits+=w.count-before;
        }
        before=w.count;const auto& a=source.pulses[at/20];const auto& b=source.pulses[at/20+1];
        if(source.profile==4){for(const auto* pulse:{&a,&b}){w.put((*pulse)[0]-((*pulse)[0]+2)/5,4);w.put((*pulse)[1]>0,1);}}
        else{w.put((a[0]&3)|((b[0]&3)<<2),4);w.put((a[0]>>2)+5*(b[0]>>2),5);w.put(a[1]&15,4);w.put(b[1]&15,4);}
        result.stats.pulseBits+=w.count-before;before=w.count;
        if(enhanced){const auto& e=source.extras[at/40];w.put(e[1]!=0,1);if(e[1]){w.put(e[0],6);w.put(e[1]&15,4);}}
        result.stats.extraBits+=w.count-before;
    }
    if(w.bytes.size()>65522)throw std::runtime_error("LG1 payload exceeds bounded length");
    result.bytes.assign(13,0);result.bytes[0]='L';result.bytes[1]='G';result.bytes[2]=source.profile|(enhanced?128:0);
    auto word=[&](int at,int value){result.bytes[at]=value&255;result.bytes[at+1]=(value>>8)&255;};
    word(3,8000);word(5,source.samples);word(7,source.pre);word(9,source.bright);word(11,w.bytes.size());
    result.bytes.insert(result.bytes.end(),w.bytes.begin(),w.bytes.end());
    result.pcm.resize(source.samples);auto state=source.initial;
    for(int j=0;j<source.samples;j++){
        const auto& pulse=source.pulses[j/20];result.pcm[j]=referenceSample(source,result.coefficients,result.excitationSteps,state,j,pulse[0],pulse[1]);
    }
    return result;
}

lpx::Stream refitPulses(const lpx::Stream& source,const EncoderResult& parameters,
                       const lpx::Pcm& reference,PulseRefitStats& stats){
    validateSource(source);
    if(reference.size()!=size_t(source.samples)||parameters.pcm.size()!=reference.size()||parameters.coefficients.size()!=size_t((source.samples+19)/20)
       ||parameters.excitationSteps.size()!=size_t((source.samples+159)/160)||stats.lookahead<20||stats.lookahead>640)throw std::runtime_error("Pulse refit length/domain mismatch");
    for(int step:parameters.excitationSteps)if(step<0||step>4095)throw std::runtime_error("Pulse refit excitation step out of range");
    lpx::Stream fitted=source;auto state=source.initial;
    for(int start=0;start<source.samples;start+=20){
        const int valid=std::min(20,source.samples-start),stop=std::min(source.samples,start+stats.lookahead);
        lpx::SynthesisState prefix[21];uint64_t prefixLoss[21]={};prefix[0]=state;
        for(int t=0;t<valid;t++){
            prefix[t+1]=prefix[t];int sample=referenceSample(fitted,parameters.coefficients,parameters.excitationSteps,prefix[t+1],start+t,20,0);
            int64_t delta=sample-reference[start+t];prefixLoss[t+1]=prefixLoss[t]+delta*delta;
        }
        auto evaluate=[&](int position,int amplitude,uint64_t bound){
            ++stats.evaluations;int from=std::min(position,valid);auto trial=prefix[from];uint64_t loss=prefixLoss[from];
            if(loss>=bound)return loss;
            for(int j=start+from;j<stop;j++){
                const auto& future=fitted.pulses[j/20];
                int sample=referenceSample(fitted,parameters.coefficients,parameters.excitationSteps,trial,j,
                                          j<start+20?position:future[0],j<start+20?amplitude:future[1]);
                int64_t delta=sample-reference[j];loss+=delta*delta;if(loss>=bound)break;
            }
            return loss;
        };
        auto chosen=fitted.pulses[start/20];uint64_t best=evaluate(chosen[0],chosen[1],std::numeric_limits<uint64_t>::max());
        const int positions=source.profile==4?16:20,amplitudes=source.profile==4?2:16;
        for(int p=0;p<positions;p++){
            int position=source.profile==4?p+(p+2)/4:p;if(position>=valid)continue;
            for(int a=0;a<amplitudes;a++){
                int amplitude=source.profile==4?(a?8:-8):a-8;
                if(position==chosen[0]&&amplitude==chosen[1])continue;
                uint64_t loss=evaluate(position,amplitude,best);
                if(loss<best){best=loss;chosen=lpx::Pulse{{position,amplitude}};}
            }
        }
        fitted.pulses[start/20]=chosen;stats.changedPulses+=chosen!=source.pulses[start/20];
        for(int t=0;t<valid;t++)referenceSample(fitted,parameters.coefficients,parameters.excitationSteps,state,start+t,chosen[0],chosen[1]);
    }
    return fitted;
}
}
