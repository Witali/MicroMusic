/* Exact C lifetime reduction for the included KISS-derived faithful graph.
 * Copyright/BSD conditions remain in faithful_analysis.c and its table include.
 * Arithmetic/rounding are unchanged; load input pairs only when consumed.
 */
static faithful_complex compact_select_two(const faithful_context *s,unsigned first,unsigned second,unsigned j,unsigned which){
    faithful_complex input={s->a[2*second],second==5?0:s->a[2*second+1]},p=multiply(input,twiddle(4*j,0)),out;
    int64_t ar=s->a[2*first],ai=s->a[2*first+1];
    if(which==0){out.r=add(ar,p.r);out.i=add(ai,p.i);}
    else if(which==2){out.r=sub(ar,p.r);out.i=sub(ai,p.i);}
    else if(which==1){out.r=add(ar,p.i);out.i=sub(ai,p.r);}
    else{out.r=sub(ar,p.i);out.i=add(ai,p.r);}return out;
}
static faithful_complex compact_spectrum(const faithful_context *s,unsigned bin){
    unsigned low=bin&63,which=bin>>6;
    faithful_complex a=compact_select_two(s,0,4,low&15,low>>4),b=compact_select_two(s,1,5,low&15,low>>4);
    b=multiply(b,twiddle(low,0));
    {
        faithful_complex c={s->a[4],s->a[5]};c=multiply(c,twiddle(2*low,0));
        a.r=(which&1)?sub(a.r,c.r):add(a.r,c.r);a.i=(which&1)?sub(a.i,c.i):add(a.i,c.i);
    }
    {
        faithful_complex c={s->a[6],s->a[7]};c=multiply(c,twiddle(3*low,0));
        b.r=(which&1)?sub(b.r,c.r):add(b.r,c.r);b.i=(which&1)?sub(b.i,c.i):add(b.i,c.i);
    }
    if(which==0){a.r=add(a.r,b.r);a.i=add(a.i,b.i);}
    else if(which==2){a.r=sub(a.r,b.r);a.i=sub(a.i,b.i);}
    else if(which==1){a.r=add(a.r,b.i);a.i=sub(a.i,b.r);}
    else{a.r=sub(a.r,b.i);a.i=add(a.i,b.r);}return a;
}
