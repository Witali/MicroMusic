#pragma once
// Encoder policy only; the decoder sees ordinary legal V9 spectral indices.
// P3 quantizes the nondecreasing rank residual (index minus coefficient rank)
// to an even grid, preserving the mandatory one-index LSF separation. A small
// temporal dead zone reuses the previous transmitted vector on stable segments.
template<class T> inline void lpxQuantizeSpectrum(T* current,const int* previous,int accuracy) {
    if(accuracy!=3)return;
    int maximum=0;
    for(int j=0;j<10;++j){int residual=int(current[j])-j;int q=((residual+1)/2)*2;if(q<0)q=0;if(q>22)q=22;current[j]=T(q+j);
        if(previous){int d=int(current[j])-previous[j];if(d<0)d=-d;if(d>maximum)maximum=d;}}
    if(previous&&maximum<=2)for(int j=0;j<10;++j)current[j]=T(previous[j]);
}
