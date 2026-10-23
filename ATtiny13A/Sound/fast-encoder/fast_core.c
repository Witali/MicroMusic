/* MicroMusic HQ3 native closed-loop evaluator.
 * Bit-exact 8-bit synthesis model and native STOI / spectral-loss metric.
 * No changes whatsoever to the AVR on-device firmware format.
 * Built against the dynamically installed FFTW3 library, with no external headers.
 * Copyright (c) 2026 MicroMusic contributors; MIT license.
 */
#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <math.h>
#include <limits.h>

/* public subset of FFTW3's C ABI */
typedef double fftw_complex[2];
typedef struct fftw_plan_s *fftw_plan;
extern fftw_plan fftw_plan_dft_r2c_1d(int,double*,fftw_complex*,unsigned);
extern void fftw_execute(const fftw_plan);
extern void fftw_destroy_plan(fftw_plan);
extern void *fftw_malloc(size_t);
extern void fftw_free(void*);
#define FFTW_ESTIMATE 64U
#define BANDS 15
#define FFTLEN 512
#define WIN 256
#define HOP 128
#define FRAMES_PER_SEG 30
#define CLIP_FACTOR 6.623413251903491
#define PI 3.14159265358979323846264338327950288

/* C model of model.py. Reproduces the AVR's signed-byte overflow. */
static inline int s8(int x) {return ((x+128)&255)-128;}
static inline unsigned mul_q4(int x,int k) {
  int a=s8(x);
  if(k<0) a=s8(-a);
  return (unsigned)((a*(k<0?-k:k))>>4)&255U;
}
int mlpc_decode(const uint8_t *frames,const uint16_t *dur,int nf,uint8_t *output,int capacity) {
  if(!frames||!dur||!output||nf<1) return -1;
  int n=0;
  for(int i=0;i<nf;i++) {if(dur[i]!=64 && dur[i]!=128 && dur[i]!=192 && dur[i]!=256)return -2; n+=dur[i]; if(n>capacity) return -3;}
  int state[8]={0}, k[8]={0},seed=0xa7,period=0,gain=0,phase=1,mode=0;
  int fi=0,next_t=dur[0]-1;
  for(int t=0;t<n;t++) {
    if(t==0 || t==next_t) {
      if(t!=0) {
        fi++;if(fi>=nf)fi=0;
        next_t+=dur[fi];
      }
      const uint8_t *f=frames+fi*6;
      period=f[0];gain=f[1]&15;mode=(f[1]>>4)&3;
      phase=period;
      for(int j=0;j<4;j++) {int v=f[2+j];k[j*2]=(v&15)-8;k[j*2+1]=(v>>4)-8;}
    }
    unsigned ex=0;
    if(period) {
      phase=(phase-1)&255;
      if(phase==0) {phase=period;ex=(unsigned)(2*gain)&255;}
      else {
        int lag=period-phase;
        if(lag==1)ex=(gain*(3-(mode&1)))&255;
        else if(lag==2)ex=(gain*(2-(mode>>1)))&255;
        else if(lag==3)ex=(-gain)&255;
      }
    } else {
      int low=seed&1;seed>>=1;if(low)seed^=0xb8;
      ex=((seed&1)?(-gain):gain)&255;
    }
    for(int j=7;j>=0;j--){
      int old=state[j], coef=k[j];ex=(ex-mul_q4(old,coef))&255;
      if(j<7)state[j+1]=(old+mul_q4((int)ex,coef))&255;
    }
    state[0]=(int)ex;output[t]=(uint8_t)((ex+128)&255);
  }
  return n;
}


/* Optional initial speech analysis in C. Produces a valid HQ3 frame grid
 * for entirely new WAV inputs; the native closed-loop optimizer then refines
 * every parameter using real STOI and the actual 8-bit decoder. */
int mlpc_analyze(const float *ref, int n, int hop, uint8_t *frames,
                 uint16_t *durations, int capacity) {
  if (!ref || !frames || !durations || n < 256 || (n & 63) ||
      (hop!=64 && hop!=128 && hop!=256)) return -1;
  int nf=(n+hop-1)/hop;
  if(nf>capacity)return -2;
  for (int fi=0;fi<nf;fi++) {
    int start=fi*hop,len=(start+hop<=n?hop:n-start);
    if(len!=64 && len!=128 && len!=192 && len!=256)return -3;
    durations[fi]=(uint16_t)len;
    double y[256]={0},r[9]={0},a[9]={0},energy=0,avg=0;
    /* pre-emphasis and half-cosine window to estimate formants */
    for (int i=0;i<len;i++) {
      double cur=ref[start+i], prev=(start+i>0?ref[start+i-1]:0);
      double w=0.5-0.5*cos(2*PI*(i+0.5)/len);
      y[i]=(cur-0.65*prev)*w;
      energy+=cur*cur;
    }
    for(int k=0;k<=8;k++)
      for(int i=k;i<len;i++)r[k]+=y[i]*y[i-k];
    double variance=r[0];
    for(int m=1;m<=8;m++){
      double accum=r[m];
      for(int j=1;j<m;j++)accum+=a[j]*r[m-j];
      double reflection=variance>1e-12?-accum/variance:0;
      if(reflection>0.875)reflection=0.875;
      if(reflection< -0.875)reflection=-0.875;
      double tmp[9];memcpy(tmp,a,sizeof(a));
      for(int j=1;j<m;j++)a[j]=tmp[j]+reflection*tmp[m-j];
      a[m]=reflection;
      variance*=1-reflection*reflection;
      int q=(int)round(reflection*8)+8;
      if(q<0)q=0;
      if(q>15)q=15;
      uint8_t *row=frames+6*fi;
      if(m==1) memset(row,0,6);
      if(m&1)row[2+(m-1)/2]=(uint8_t)q;
      else row[2+(m-1)/2]|=(uint8_t)(q<<4);
    }
    /* periodicity: normalized autocorrelation of pre-emphasized speech */
    double best=0;int pitch=0;
    for(int lag=12;lag<=125 && lag<len/2;lag++){
      double cross=0,xa=0,xb=0;
      for(int i=lag;i<len;i++){
        double p=y[i],q=y[i-lag];cross+=p*q;xa+=p*p;xb+=q*q;
      }
      double correlation=cross/(sqrt(xa*xb)+1e-20);
      /* tie-break slightly favors lower integer period (female voices) */
      correlation-=lag*0.00045;
      if(correlation>best){best=correlation;pitch=lag;}
    }
    if(best<0.24)pitch=0;
    double rms=sqrt(energy/len);
    int gain=(int)round(rms*39);
    if(gain<1 && rms>0.002)gain=1;
    if(gain>15)gain=15;
    uint8_t *row=frames+6*fi;
    row[0]=(uint8_t)pitch;
    row[1]=(uint8_t)((0<<4)|gain);
  }
  return nf;
}

struct MLPC {
  int n, n10, hlen, filter_prepad, remove_start, max_stft, keep_count, band_n;
  double *filter; double *clean10; double *resamp; double *sig_sil;
  uint8_t *keep;
  double *refBand; /* shape [band][stft frame] */
  double *candBand;
  double *refSpec; int nspec;
  double *fftIn512; fftw_complex *fftOut512;fftw_plan plan512;
  double *fftIn256; fftw_complex *fftOut256;fftw_plan plan256;
  int b_lo[BANDS],b_hi[BANDS];
  double hanning[WIN],hann_stoi[WIN];
  double *xsegMean,*xsegNorm; /* reserve */
};
static void resample(struct MLPC *c,const double *input,double *result){
  /* scipy.signal.resample_poly(x,4,3,window=oct_filter) */
  for(int j=0;j<c->n10;j++){
    int t=(j+c->remove_start)*3 - c->filter_prepad;
    int v=t-c->hlen+1; int i_min = (v>=0 ? (v+3)/4 : v/4); /* ceil signed */
    int i_max=t/4;
    if(t<0){i_max=-1;}
    if(i_min<0)i_min=0;
    if(i_max>=c->n)i_max=c->n-1;
    double sum=0;
    for(int i=i_min;i<=i_max;i++){
      int hi=t-i*4;
      if(hi>=0 && hi<c->hlen)sum+=input[i]*c->filter[hi];
    }
    result[j]=4.0*sum;
  }
}
static void calc_keep(struct MLPC*c){
  int fr=(c->n10-WIN-1)/HOP+1;
  if(fr<0)fr=0;
  double maximum=-10000000.0;
  for(int f=0;f<fr;f++){
    double q=0;for(int i=0;i<WIN;i++){double v=c->clean10[f*HOP+i]*c->hann_stoi[i];q+=v*v;}
    double db=20.0*log10(sqrt(q)+2.220446049250313e-16);
    c->resamp[f]=db;if(db>maximum)maximum=db;
  }
  c->keep_count=0;
  for(int f=0;f<fr;f++) {uint8_t flag=(maximum-40.0-c->resamp[f]<0);c->keep[f]=flag;c->keep_count+=flag;}
}
static int overlap_add(struct MLPC*c,const double *src,double *dest){
  memset(dest,0,((c->keep_count+1)*HOP+WIN)*sizeof(double));
  int index=0;
  int nfr=(c->n10-WIN-1)/HOP+1;
  if(nfr<0)nfr=0;
  for(int f=0;f<nfr;f++)if(c->keep[f]){
    for(int i=0;i<WIN;i++)dest[index*HOP+i]+=src[f*HOP+i]*c->hann_stoi[i];
    index++;
  }
  return c->keep_count>0?(c->keep_count-1)*HOP+WIN:0;
}
static int make_stft_bands(struct MLPC*c,const double *src,int n,double *dest){
  int frame_n=(n-WIN-1)/HOP+1;if(frame_n<0)frame_n=0;
  for(int f=0;f<frame_n;f++){
    memset(c->fftIn512,0,FFTLEN*sizeof(double));
    for(int j=0;j<WIN;j++) c->fftIn512[j]=src[f*HOP+j]*c->hann_stoi[j];
    fftw_execute(c->plan512);
    for(int b=0;b<BANDS;b++){
      double energy=0.0;
      for(int k=c->b_lo[b];k<c->b_hi[b];k++){
        double re=c->fftOut512[k][0],im=c->fftOut512[k][1];energy+=re*re+im*im;
      }
      dest[b*c->max_stft+f]=sqrt(energy);
    }
  }
  return frame_n;
}
static void make_log_spectrum(struct MLPC*c,const double *src,int len,double *dest) {
  int frames=(len+256-1)/128; /* actual strided output len after pad */
  for(int f=0;f<frames;f++){
    /* x is padded 128 zeros before and after */
    for(int i=0;i<WIN;i++){
      int pos=f*128+i-128;
      c->fftIn256[i]=(pos>=0 && pos<len?src[pos]:0.0)*c->hanning[i];
    }
    fftw_execute(c->plan256);
    for(int k=0;k<=128;k++){
      double re=c->fftOut256[k][0],im=c->fftOut256[k][1];
      double mag=sqrt(re*re+im*im);
      dest[f*129+k]=log(mag>0.006?mag:0.006);
    }
  }
}
static double calc_stoi(struct MLPC*c,const uint8_t *pcm){
  for(int i=0;i<c->n;i++)c->sig_sil[i]=((int)pcm[i]-128)/128.0;
  resample(c,c->sig_sil,c->resamp);
  int n=overlap_add(c,c->resamp,c->sig_sil);
  int nf=make_stft_bands(c,c->sig_sil,n,c->candBand);
  if(nf<FRAMES_PER_SEG)return 0.00001;
  double correlation=0;
  int segments=nf-FRAMES_PER_SEG+1;
  for(int b=0;b<BANDS;b++){
    const double *x=c->refBand+b*c->max_stft;
    const double *y=c->candBand+b*c->max_stft;
    for(int s=0;s<segments;s++){
      double xx=0,yy=0;
      for(int k=s;k<s+FRAMES_PER_SEG;k++){xx+=x[k]*x[k];yy+=y[k]*y[k];}
      double alpha=sqrt(xx)/(sqrt(yy)+2.220446049250313e-16);
      double mx=0,my=0;
      double a[FRAMES_PER_SEG],v[FRAMES_PER_SEG];
      for(int k=0;k<FRAMES_PER_SEG;k++){
        a[k]=x[s+k];
        double v0=y[s+k]*alpha,limit=a[k]*CLIP_FACTOR;
        v[k]=v0<limit?v0:limit;
        mx+=a[k];my+=v[k];
      }
      mx/=FRAMES_PER_SEG;my/=FRAMES_PER_SEG;
      double cov=0,vx=0,vy=0;
      for(int k=0;k<FRAMES_PER_SEG;k++){
        double dx=a[k]-mx,dy=v[k]-my;
        cov+=dx*dy;vx+=dx*dx;vy+=dy*dy;
      }
      correlation+=cov/((sqrt(vx)+2.220446049250313e-16)*(sqrt(vy)+2.220446049250313e-16));
    }
  }
  return correlation/(BANDS*segments);
}
static double calc_spectral(struct MLPC*c,const uint8_t *pcm){
  int frames=c->nspec;
  double sum=0;
  for(int f=0;f<frames;f++){
    for(int i=0;i<WIN;i++){
      int pos=f*HOP+i-128;
      c->fftIn256[i]=(pos>=0 && pos<c->n?((int)pcm[pos]-128)/128.0:0.0)*c->hanning[i];
    }
    fftw_execute(c->plan256);
    for(int k=0;k<=128;k++){
      double re=c->fftOut256[k][0],im=c->fftOut256[k][1];
      double mag=sqrt(re*re+im*im);
      double v=log(mag>0.006?mag:0.006);
      sum+=fabs(v-c->refSpec[f*129+k]);
    }
  }
  return sum/((double)frames*129);
}
struct MLPC* mlpc_create(const float *ref,int n,const double *fir,int hlen) {
  if(!ref || !fir || n<512 || n>100000 || hlen<3 || hlen>2048 || (hlen&1)==0)return NULL;
  struct MLPC*c=calloc(1,sizeof(*c));if(!c)return NULL;
  c->n=n;c->n10=(n*4+2)/3;c->hlen=hlen;
  c->filter_prepad=3-((hlen-1)/2)%3;
  c->remove_start=((hlen-1)/2+c->filter_prepad)/3;
  c->filter=malloc(hlen*sizeof(double));memcpy(c->filter,fir,hlen*sizeof(double));
  c->clean10=calloc(c->n10+1024,sizeof(double));
  c->resamp=calloc(c->n10+1024,sizeof(double));
  c->sig_sil=calloc(c->n10+1024,sizeof(double));
  c->keep=calloc(c->n10/128+10,1);
  c->max_stft=c->n10/128+10;
  c->refBand=calloc(BANDS*c->max_stft,sizeof(double));
  c->candBand=calloc(BANDS*c->max_stft,sizeof(double));
  c->nspec=n/128+1;
  c->refSpec=calloc(c->nspec*129,sizeof(double));
  c->fftIn512=fftw_malloc(FFTLEN*sizeof(double));
  c->fftOut512=fftw_malloc((FFTLEN/2+1)*sizeof(fftw_complex));
  c->fftIn256=fftw_malloc(WIN*sizeof(double));
  c->fftOut256=fftw_malloc((WIN/2+1)*sizeof(fftw_complex));
  if(!c->clean10||!c->resamp||!c->sig_sil||!c->keep||!c->refBand||!c->candBand||!c->refSpec||!c->fftIn512||!c->fftOut512||!c->fftIn256||!c->fftOut256) {free(c);return NULL;}
  c->plan512=fftw_plan_dft_r2c_1d(FFTLEN,c->fftIn512,c->fftOut512,FFTW_ESTIMATE);
  c->plan256=fftw_plan_dft_r2c_1d(WIN,c->fftIn256,c->fftOut256,FFTW_ESTIMATE);
  for(int i=0;i<WIN;i++){
    c->hanning[i]=0.5*(1-cos(2*PI*i/(WIN-1))); /* np.hanning(256) */
    c->hann_stoi[i]=0.5*(1-cos(2*PI*(i+1)/(WIN+1))); /* np.hanning(258)[1:-1] */
  }
  for(int b=0;b<BANDS;b++){
    double center=150.0*pow(2,((double)b)/3.0);
    double low=center/pow(2,1.0/6.0),high=center*pow(2,1.0/6.0);
    int lo=(int)round(low/(10000.0/512));
    int hi=(int)round(high/(10000.0/512));
    if(lo<0)lo=0;
    if(hi>256)hi=256;
    c->b_lo[b]=lo;c->b_hi[b]=hi;
  }
  double *src=malloc(n*sizeof(double));
  for(int i=0;i<n;i++)src[i]=ref[i];
  resample(c,src,c->clean10);
  calc_keep(c);
  /* We need resampled reference retained, and can reuse resamp as work output. */
  int n_sil=overlap_add(c,c->clean10,c->sig_sil);
  c->band_n=make_stft_bands(c,c->sig_sil,n_sil,c->refBand);
  make_log_spectrum(c,src,n,c->refSpec);
  free(src);
  if(c->band_n<FRAMES_PER_SEG){fprintf(stderr,"Reference too short for STOI\n");}
  return c;
}
void mlpc_destroy(struct MLPC*c){
  if(!c)return;
  if(c->plan512)fftw_destroy_plan(c->plan512);
  if(c->plan256)fftw_destroy_plan(c->plan256);
  free(c->filter);free(c->clean10);free(c->resamp);free(c->sig_sil);free(c->keep);
  free(c->refBand);free(c->candBand);free(c->refSpec);
  if(c->fftIn512)fftw_free(c->fftIn512);
  if(c->fftOut512)fftw_free(c->fftOut512);
  if(c->fftIn256)fftw_free(c->fftIn256);
  if(c->fftOut256)fftw_free(c->fftOut256);
  free(c);
}
int mlpc_metrics(struct MLPC*c,const uint8_t*pcm,int n,double*out3) {
  if(!c||!pcm||n!=c->n||!out3)return -1;
  out3[0]=calc_stoi(c,pcm);
  out3[1]=calc_spectral(c,pcm);
  int click=0;for(int i=1;i<n;i++)if(abs((int)pcm[i]-(int)pcm[i-1])>=48)click++;
  out3[2]=click;
  return 0;
}

/* Total native multi-candidate search, using the same 0.015 spectral & 0.0025 click penalties as HQ2. */
static int stream_len(const uint8_t *fr,const uint16_t *d,int nf) {
  int total=0;uint8_t old[4]={0};
  for(int j=0;j<nf;j++){
    const uint8_t *row=fr+6*j;
    total+=2; /* pitch+header */
    if(d[j]==192 || row[0]>=64)total++; /* extended pitch */
    int lo=memcmp(row+2,old,2)!=0,hi=memcmp(row+4,old+2,2)!=0;
    if(j==0||(lo&&hi)){total+=4;}
    else if(lo||hi)total+=2;
    memcpy(old,row+2,4);
  }
  return total;
}
int mlpc_stream_bytes(const uint8_t*fr,const uint16_t*d,int nf){return stream_len(fr,d,nf);}
/* mutate and retain best in-place after one sweep; native C calculates exact STOI */
int mlpc_optimize(struct MLPC*c,uint8_t*fr,const uint16_t*d,int nf,int budget,int max_evals,int seed,double spec_weight,double*before3,double*after3){
  if(!c||!fr||!d||nf<1||max_evals<1||budget<1)return -1;
  uint8_t *pcm=malloc(c->n), *row;
  if(!pcm)return -2;
  mlpc_decode(fr,d,nf,pcm,c->n);
  double cur[3]={0}; mlpc_metrics(c,pcm,c->n,cur);
  if(before3)memcpy(before3,cur,sizeof(cur));
  double objective=cur[0]-spec_weight*cur[1]-.0025*cur[2];
  int maxclick=cur[2],evals=0,accepted=0;
  unsigned rng=(unsigned)seed;if(!rng)rng=0xa7b4ce21u;
  while(evals<max_evals){
    /* xorshift32 reproducible pseudo-random scan */
    rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;
    int i=(int)(rng%(unsigned)nf);
    row=fr+i*6;
    uint8_t original[6],winner[6];memcpy(original,row,6);memcpy(winner,row,6);
    int p0=original[0],g0=original[1]&15,m0=(original[1]>>4)&3;
    double top=objective,newbest[3]={cur[0],cur[1],cur[2]};
    for(int selector=0;selector<11 && evals<max_evals;selector++){
      /* Explore pitch/gain, excitation and all coefficient nibbles. */
      if(selector==0){
        int pp[12]={p0-3,p0-2,p0-1,p0+1,p0+2,p0+3,p0/2,p0*2,0,p0-5,p0+5,p0};
        for(int ii=0;ii<12&&evals<max_evals;ii++){
          int p=pp[ii];if(p<0||p>126||(p>0&&p<8))continue;
          memcpy(row,original,6);row[0]=(uint8_t)p;
          if(stream_len(fr,d,nf)>budget)continue;
          mlpc_decode(fr,d,nf,pcm,c->n);double m[3];mlpc_metrics(c,pcm,c->n,m);evals++;
          double v=m[0]-spec_weight*m[1]-.0025*m[2];
          if(m[2]<=maxclick && v>top+0.000002){top=v;memcpy(winner,row,6);memcpy(newbest,m,sizeof(m));}
        }
      } else if(selector==1){
        for(int gg=0;gg<=15&&evals<max_evals;gg++){
          memcpy(row,original,6);row[1]=(uint8_t)((m0<<4)|gg);
          mlpc_decode(fr,d,nf,pcm,c->n);double m[3];mlpc_metrics(c,pcm,c->n,m);evals++;
          double v=m[0]-spec_weight*m[1]-.0025*m[2];
          if(m[2]<=maxclick && v>top+0.000002){top=v;memcpy(winner,row,6);memcpy(newbest,m,sizeof(m));}
        }
      } else if(selector==2){
        for(int mm=0;mm<4&&evals<max_evals;mm++){
          memcpy(row,original,6);row[1]=(uint8_t)((mm<<4)|g0);
          mlpc_decode(fr,d,nf,pcm,c->n);double m[3];mlpc_metrics(c,pcm,c->n,m);evals++;
          double v=m[0]-spec_weight*m[1]-.0025*m[2];
          if(m[2]<=maxclick && v>top+0.000002){top=v;memcpy(winner,row,6);memcpy(newbest,m,sizeof(m));}
        }
      } else {
        int idx=selector-3;
        int curk=(original[2+idx/2]>>(4*(idx&1)))&15;
        for(int dv=-3;dv<=3&&evals<max_evals;dv++) {
          int v=curk+dv;if(v<0||v>15)continue;
          memcpy(row,original,6);
          int off=2+idx/2;
          row[off]=idx%2?(uint8_t)((row[off]&15)|(v<<4)):(uint8_t)((row[off]&240)|v);
          if(stream_len(fr,d,nf)>budget)continue;
          mlpc_decode(fr,d,nf,pcm,c->n);double m[3];mlpc_metrics(c,pcm,c->n,m);evals++;
          double vscore=m[0]-spec_weight*m[1]-.0025*m[2];
          if(m[2]<=maxclick && vscore>top+0.000002){top=vscore;memcpy(winner,row,6);memcpy(newbest,m,sizeof(m));}
        }
      }
    }
    memcpy(row,winner,6);
    if(top>objective+0.000002){objective=top;memcpy(cur,newbest,sizeof(cur));accepted++;}
    /* End sweep once evals reaches desired search budget. */
  }
  free(pcm);
  if(after3)memcpy(after3,cur,sizeof(cur));
  return accepted;
}
