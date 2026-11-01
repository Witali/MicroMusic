// Independent host-only version8 parser and exact v5/P6 expander.
// Uses no arithmetic backend changes and is not target firmware.
#include <stdint.h>
#include <vector>
#include <algorithm>
#include <string.h>
#ifdef _WIN32
#define S15_EXPORT __declspec(dllexport)
#else
#define S15_EXPORT __attribute__((visibility("default")))
#endif
namespace {
struct Reader {
    const uint8_t* p;size_t size,at;uint32_t acc;unsigned bits;
    Reader(const uint8_t* b,size_t n):p(b),size(n),at(0),acc(0),bits(0){}
    unsigned get(unsigned n){
        while(bits<n){if(at>=size)throw 1;acc|=(uint32_t)p[at++]<<bits;bits+=8;}
        unsigned v=acc&((1U<<n)-1);acc>>=n;bits-=n;return v;
    }
};
struct Writer {
    std::vector<uint8_t> bytes;uint32_t acc=0;unsigned bits=0,total=0;
    void put(unsigned x,unsigned n){
        if(n>8||x>=(1U<<n))throw 2;
        acc|=(uint32_t)x<<bits;bits+=n;total+=n;
        if(bits>=8){bytes.push_back((uint8_t)acc);acc>>=8;bits-=8;}
    }
    void finish(){if(bits){bytes.push_back((uint8_t)acc);acc=0;bits=0;}}
};
unsigned word(const uint8_t* p){return p[0]|(unsigned)p[1]<<8;}
unsigned rice(Reader& r,unsigned k,unsigned width){
    unsigned q=0;while(q<8&&!r.get(1))++q;
    return q==8?r.get(width):(q<<k)|r.get(k);
}
void putRice(Writer& w,unsigned value,unsigned k,unsigned width){
    unsigned q=value>>k;
    if(q>=8){w.put(0,8);w.put(value,width);}
    else{w.put(0,q);w.put(1,1);w.put(value&((1U<<k)-1),k);}
}
void getSpectrum(Reader& r,int* out,const int* old){
    if(!r.get(1)){if(!old)throw 3;for(unsigned i=0;i<10;i++)out[i]=old[i];return;}
    bool delta=r.get(1)!=0;if(delta&&!old)throw 3;
    for(unsigned i=0;i<10;i++){
        unsigned z=rice(r,delta?1:2,delta?7:6);
        int value=delta?old[i]+((z&1)?-(int)(z/2)-1:(int)(z/2)):(i?out[i-1]+1:0)+(int)z;
        if(value<0||value>=64||(i&&value<=out[i-1]))throw 3;
        out[i]=value;
    }
}
void putSpectrum(Writer& w,const int* vec,const int* old){
    if(old&&std::equal(vec,vec+10,old)){w.put(0,1);return;}
    Writer gap,delta;
    for(unsigned i=0;i<10;i++)putRice(gap,vec[i]-(i?vec[i-1]+1:0),2,6);
    if(old)for(unsigned i=0;i<10;i++){
        int d=vec[i]-old[i];putRice(delta,d>=0?2*d:-2*d-1,1,7);
    }
    bool useDelta=old&&delta.total<gap.total;
    w.put(1,1);w.put(useDelta,1);
    for(unsigned i=0;i<10;i++){
        int d=useDelta?vec[i]-old[i]:vec[i]-(i?vec[i-1]+1:0);
        unsigned z=useDelta?(d>=0?2*d:-2*d-1):d;
        putRice(w,z,useDelta?1:2,useDelta?7:6);
    }
}
}
extern "C" S15_EXPORT int lpx_s15_expand(const uint8_t* src,uint32_t length,
                                         uint8_t* dst,uint32_t capacity,uint32_t* written){
    if(!src||!dst||!written)return 1;*written=0;
    try {
        if(length<22||memcmp(src,"L4HY",4)||src[4]!=8||src[5]!=15||word(src+6)!=8000||
           word(src+16)!=320||word(src+18)!=320||word(src+12)>16384||word(src+14)>11469||
           length!=22+word(src+20))return 2;
        uint32_t n=src[8]|(uint32_t)src[9]<<8|(uint32_t)src[10]<<16|(uint32_t)src[11]<<24;
        if(!n||n>64000)return 2;
        Reader r(src+22,length-22);Writer w;int old[10],vec[10];bool hasOld=false;
        for(uint32_t fi=0;fi<(n+319)/320;fi++){
            getSpectrum(r,vec,hasOld?old:0);putSpectrum(w,vec,hasOld?old:0);
            unsigned scale=r.get(5),lag=r.get(7),gain=r.get(3);
            unsigned pos[16]={0};int amp[16]={0};
            for(unsigned group=0;group<4;group++){
                unsigned code=r.get(6),at=code+((code+2)>>2);
                unsigned index=group*4+at/20;pos[index]=at%20;amp[index]=r.get(1)?7:-8;
            }
            for(unsigned half=0;half<2;half++){
                w.put(scale,5);w.put(lag,7);w.put(gain,3);
                for(unsigned pair=0;pair<4;pair++){
                    unsigned a=half*8+pair*2,b=a+1,combo=pos[a]+20*pos[b];
                    w.put(combo&255,8);w.put(combo>>8,1);
                    w.put((unsigned)amp[a]&15,4);w.put((unsigned)amp[b]&15,4);
                }
            }
            std::copy(vec,vec+10,old);hasOld=true;
        }
        if(r.at!=r.size||r.acc)return 3;
        w.finish();if(w.bytes.size()>65513||capacity<22+w.bytes.size())return 4;
        memcpy(dst,src,20);dst[4]=5;dst[5]=6;dst[18]=160;dst[19]=0;
        dst[20]=(uint8_t)w.bytes.size();dst[21]=(uint8_t)(w.bytes.size()>>8);
        memcpy(dst+22,w.bytes.data(),w.bytes.size());*written=(uint32_t)(22+w.bytes.size());
        return 0;
    } catch(...) {return 3;}
}
