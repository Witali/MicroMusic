#include "LpxPacking.h"
#include <algorithm>
#include <utility>

namespace lpx {
void V9PacketWriter::put(int value,int width) {
    for(int i=0;i<width;++i,++written) {
        partial|=((value>>i)&1)<<used;
        if(++used==8) { pending.push_back(partial);partial=0;used=0; }
    }
}
void V9PacketWriter::rice(int value,int k,int width) {
    int q=value>>k;
    if(q>=8) { put(0,8);put(value,width); }
    else { put(0,q);put(1,1);put(value&((1<<k)-1),k); }
}
static int riceCost(int v,int k,int width) { return v>>k>=8?8+width:(v>>k)+1+k; }
static void spectrum(V9PacketWriter& w,const Spectrum& current,const Spectrum* old,int bits) {
    if(old && current==*old) { w.put(0,1);return; }
    int gaps[10],deltas[10],gc=0,dc=old?0:100000;
    for(int j=0;j<10;++j) {
        gaps[j]=current[j]-(j?current[j-1]+1:0);
        int delta=old?current[j]-(*old)[j]:0;deltas[j]=delta>=0?2*delta:-2*delta-1;
        gc+=riceCost(gaps[j],bits==5?1:2,bits);
        if(old)dc+=riceCost(deltas[j],bits==5?0:1,bits+1);
    }
    bool useDelta=dc<gc;w.put(1,1);w.put(useDelta,1);
    for(int j=0;j<10;++j)w.rice(useDelta?deltas[j]:gaps[j],(bits==5?1:2)-int(useDelta),bits+int(useDelta));
}
static int active(const Stream& s) { int n=0;for(const auto& p:s.extras)n+=p[1]!=0;return n; }
bool V9PacketWriter::append(const Stream& s) {
    if(s.accuracy==3){auto canonical=canonicalAccuracy(s);canonical.accuracy=0;return append(canonical);}
    const int count=(s.samples+319)/320;
    if(finished || partialFrame || s.samples<1 || (s.profile!=4 && s.profile!=6)
       || (profile && profile!=s.profile) || int(s.spectra.size())!=count
       || int(s.parameters.size())<count*2 || int(s.pulses.size())<count*16
       || int(s.extras.size())<count*8 || (!enhanced && active(s)))return false;
    profile=s.profile;
    for(int f=0;f<count;++f) {
        uint64_t before=written;spectrum(*this,s.spectra[f],hasPrevious?&previous:nullptr,profile==4?5:6);
        spectral+=written-before;previous=s.spectra[f];hasPrevious=true;++frames;
        for(int half=0;half<2;++half) {
            int base=f*320+half*160;if(base>=s.samples)break;
            const auto& p=s.parameters[f*2+half];put(p[0],5);put(p[2]/2,3);if(p[2])put(p[1]-18,7);
            for(int group=0;group<4 && base+group*40<s.samples;++group) {
                const auto& a=s.pulses[base/20+group*2];const auto& b=s.pulses[base/20+group*2+1];
                if(profile==4)for(const auto* pulse:{&a,&b}) { put((*pulse)[0]-((*pulse)[0]+2)/5,4);put((*pulse)[1]>0,1); }
                else { put((a[0]&3)|((b[0]&3)<<2),4);put((a[0]>>2)+5*(b[0]>>2),5);put(a[1]&15,4);put(b[1]&15,4); }
                if(enhanced) { const auto& e=s.extras[base/40+group];put(e[1]!=0,1);if(e[1]) { put(e[0],6);put(e[1]&15,4); } }
            }
        }
    }
    partialFrame=s.samples%320!=0;return true;
}
std::vector<uint8_t> V9PacketWriter::drain() { std::vector<uint8_t> result;result.swap(pending);return result; }
std::vector<uint8_t> V9PacketWriter::finish() {
    if(!finished && used)pending.push_back(partial);
    finished=true;partial=0;used=0;return drain();
}
int spectralBits(const Stream& s) {
    if(s.accuracy==3){auto canonical=canonicalAccuracy(s);canonical.accuracy=0;return spectralBits(canonical);}
    V9PacketWriter w(false);
    for(size_t f=0;f<s.spectra.size();++f)spectrum(w,s.spectra[f],f?&s.spectra[f-1]:nullptr,s.profile==4?5:6);
    return w.bits();
}
int compactBytes(const Stream& s) {
    int n=active(s),frames=s.spectra.size();
    int bits=spectralBits(s)+frames*(s.profile==4?110:166)+(n?frames*8+n*10:0);
    return 22+(bits+7)/8;
}
int extraCapacity(const Stream& s,int cap,int slots) {
    if(!s.allowExtras)return 0;
    int f=s.spectra.size();if(slots<0)slots=s.extras.size();
    return std::max(0,std::min(slots,((cap-22)*8-spectralBits(s)-f*(s.profile==4?110:166)-f*8)/10));
}
std::vector<uint8_t> v9Header(uint32_t samples,int profile,int rate,int pre,int bright,bool enhanced,uint32_t payload) {
    bool wide=samples>64000;std::vector<uint8_t> bytes(wide?17:13,0);
    auto word=[&](int at,uint32_t v) { bytes[at]=v;bytes[at+1]=v>>8; };
    auto dword=[&](int at,uint32_t v) { word(at,v);word(at+2,v>>16); };
    bytes[0]='L';bytes[1]='9';bytes[2]=profile|(wide?64:0)|(enhanced?128:0);word(3,rate);
    if(wide) { dword(5,samples);word(9,pre);word(11,bright);dword(13,payload); }
    else { word(5,samples);word(7,pre);word(9,bright);word(11,payload); }
    return bytes;
}
std::vector<uint8_t> packV9(const Stream& s) {
    bool enhanced=active(s)>0;V9PacketWriter writer(enhanced);if(!writer.append(s))return {};
    auto payload=writer.finish();auto bytes=v9Header(s.samples,s.profile,s.rate,s.pre,s.bright,enhanced,payload.size());
    bytes.insert(bytes.end(),payload.begin(),payload.end());return bytes;
}
}
