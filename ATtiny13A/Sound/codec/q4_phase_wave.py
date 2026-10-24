"""PC study: a full periodic excitation through the exact byte-state lattice.

Frequency is a 16-bit phase increment. The 32-point wave uses eight fractional
interpolation steps. This is not an AVR implementation or a Flash-fit claim.
"""
import numpy as np
from numba import njit

SCHEMA='q4-phase-wave-study-v1'


def validate(steps,gains,durations,coefficients,modes,waves,offsets,resets):
    arrays=tuple(map(np.asarray,(steps,gains,durations,coefficients,modes,waves,offsets,resets)))
    p,g,d,k,m,b,o,r=arrays
    if any(a.dtype.kind not in 'iu' for a in arrays):raise ValueError('Integer controls required')
    if (p.ndim!=1 or not len(p) or any(a.shape!=p.shape for a in (g,d,m,o,r))
            or np.any(p<0) or np.any(p>65535) or np.any(g<0) or np.any(g>15)
            or not np.all(np.isin(d,[64,128,192,256])) or k.shape!=(len(p),8)
            or np.any(k < -15) or np.any(k>15) or b.ndim!=2 or b.shape[1]!=32
            or not 1<=len(b)<=8 or np.any(b < -7) or np.any(b>7)
            or np.any(m<0) or np.any(m>=len(b)) or np.any(o<0) or np.any(o>65535)
            or not np.all(np.isin(r,[0,1]))):raise ValueError('Invalid phase-wave controls')
    return arrays


@njit(cache=True)
def trace(steps,durations,offsets,resets):
    """Frozen Q3 T1 frame convention; the last sample loads frame zero."""
    rows=np.empty(int(durations.sum()),np.int32);phases=np.empty(len(rows),np.uint16)
    frame=phase=0;next_t=int(durations[0])-1
    for n in range(len(rows)):
        if n==0 or n==next_t:
            if n:
                frame+=1
                if frame==len(steps):frame=0
                next_t+=int(durations[frame])
            if n==0 or resets[frame]:phase=int(offsets[frame])
        rows[n]=frame;phases[n]=phase
        phase=(phase+int(steps[frame]))&65535
    return rows,phases


@njit(cache=True)
def state_multiply(value,coefficient,state_bits,nearest):
    limit=128 if state_bits==0 else 32768
    if coefficient<0:value=((-value+limit)&(2*limit-1))-limit
    product=value*abs(coefficient)
    if nearest:
        result=(product+8)>>4 if product>=0 else -((-product+8)>>4)
    else:result=product>>4
    return ((result+limit)&(2*limit-1))-limit


@njit(cache=True)
def filter_signal(excitation,rows,coefficients,tilt_shift=1,state_bits=0,nearest=False,fraction_bits=0):
    output=np.empty(len(rows),np.uint8);counts=np.zeros(4,np.int64)
    states=np.zeros(8,np.int32);previous=0;limit=128 if state_bits==0 else 32768
    for n in range(len(output)):
        row=rows[n];ex=np.int64(excitation[n])
        if state_bits>=fraction_bits:ex<<=state_bits-fraction_bits
        else:ex>>=fraction_bits-state_bits
        for j in range(7,-1,-1):
            old=int(states[j]);k=int(coefficients[row,j])
            counts[2]+=int(old==-limit and k<0)
            raw=ex-state_multiply(old,k,state_bits,nearest)
            counts[0]+=int(raw < -limit or raw>=limit);ex=((raw+limit)&(2*limit-1))-limit
            if j<7:
                counts[2]+=int(ex==-limit and k<0)
                raw=old+state_multiply(ex,k,state_bits,nearest)
                counts[1]+=int(raw < -limit or raw>=limit);states[j+1]=((raw+limit)&(2*limit-1))-limit
        states[0]=ex;raw=ex+previous-(previous>>tilt_shift)
        counts[3]+=int(raw < -limit or raw>=limit);previous=((raw+limit)&(2*limit-1))-limit
        sample=previous>>state_bits
        counts[3]+=int(sample < -128 or sample>127);output[n]=(sample+128)&255
    return output,counts


@njit(cache=True)
def render(steps,gains,durations,coefficients,modes,waves,offsets,resets,tilt_shift=1,state_bits=0,nearest=False,excitation_shift=0):
    rows,phases=trace(steps,durations,offsets,resets);excitation=np.empty(len(rows),np.int32);seed=0xa7
    for n in range(len(rows)):
        row=rows[n];gain=np.int64(gains[row])
        if steps[row]:
            phase=np.int64(phases[n]);index=phase>>11;fraction=(phase>>8)&7;mode=np.int64(modes[row])
            a=np.int64(waves[mode,index]);b=np.int64(waves[mode,(index+1)&31])
            excitation[n]=(a*8+(b-a)*fraction)*gain
        else:
            low=seed&1;seed>>=1
            if low:seed^=0xb8
            excitation[n]=(-gain if seed&1 else gain)*8
    return filter_signal(excitation,rows,coefficients,tilt_shift,state_bits,nearest,3+excitation_shift)


@njit(cache=True)
def legacy_excitation(pitches,gains,durations,modes,waves,halves,pitch_bits=1,phase_mode=0,phase_modes=None):
    """One-bit legacy or explicitly selected two-bit period fractions."""
    rows=np.empty(int(durations.sum()),np.int32);excitation=np.empty(len(rows),np.int32)
    seed,phase,frame,next_t=0xa7,1,0,int(durations[0])-1
    period=gain=mode=cycle_extra=half=0;fraction_acc=3;cycle_period=0
    for n in range(len(rows)):
        if n==0 or n==next_t:
            if n:
                frame+=1
                if frame==len(pitches):frame=0
                next_t+=int(durations[frame])
            old_period=period;period=int(pitches[frame]);half=int(halves[frame])
            active_mode=phase_mode if phase_modes is None else int(phase_modes[frame])
            if active_mode==0 or active_mode==3 or n==0 or old_period==0 or period==0:
                cycle_extra=0;fraction_acc=3;phase=period;cycle_period=period
                if (active_mode==2 or active_mode==3) and period:phase=1
            gain=int(gains[frame]);mode=int(modes[frame])
        ex=0
        if period:
            phase=(phase-1)&255
            if not phase:
                if pitch_bits==1:
                    if half:cycle_extra^=1
                    else:cycle_extra=0
                else:
                    total=fraction_acc+half;cycle_extra=total>>2;fraction_acc=total&3
                phase=period+cycle_extra;cycle_period=phase;ex=int(waves[mode,0])*gain
            else:
                lag=cycle_period-phase
                if lag<16:ex=int(waves[mode,lag])*gain
        else:
            low=seed&1;seed>>=1
            if low:seed^=0xb8
            ex=-gain if seed&1 else gain
        rows[n]=frame;excitation[n]=ex
    return rows,excitation


@njit(cache=True)
def inverse(reference,coefficients,rows,scale=128.):
    """Floating inverse for training hints only, never a decoder oracle."""
    output=np.empty(len(reference),np.float64);states=np.zeros(8,np.float64);previous=0.
    for n in range(len(reference)):
        sample=reference[n]*scale;value=sample-previous*.5;previous=sample
        next_states=np.zeros(8,np.float64);next_states[0]=value
        for j in range(8):
            old=states[j];k=coefficients[rows[n],j]/16.
            if j<7:next_states[j+1]=old+k*value
            value+=k*old
        output[n]=value;states=next_states
    return output


@njit(cache=True)
def normal_equations(target,rows,phases,steps,gains,modes,count):
    matrix=np.zeros((count*32,count*32),np.float64);rhs=np.zeros(count*32,np.float64)
    for n in range(len(target)):
        row=rows[n]
        if not steps[row] or not gains[row]:continue
        phase=int(phases[n]);index=phase>>11;fraction=((phase>>8)&7)/8.
        left=int(modes[row])*32+index;right=int(modes[row])*32+((index+1)&31)
        a=int(gains[row])*(1.-fraction);b=int(gains[row])*fraction
        matrix[left,left]+=a*a;matrix[right,right]+=b*b
        matrix[left,right]+=a*b;matrix[right,left]+=a*b
        rhs[left]+=a*target[n];rhs[right]+=b*target[n]
    return matrix,rhs


@njit(cache=True)
def assign(target,rows,phases,steps,gains,modes,waves,offsets,aligned):
    """Inverse-error initialization of selectors, gains and optional phases."""
    new_g=gains.copy();new_m=modes.copy();new_o=offsets.copy()
    for row in range(len(steps)):
        if not steps[row] or not gains[row]:continue
        samples=np.flatnonzero(rows==row);best=1e300
        for mode in range(len(waves)):
            for rotation in range(32 if aligned else 1):
                numerator=denominator=0.
                for n in samples:
                    phase=(int(phases[n])+rotation*2048)&65535
                    index=phase>>11;fraction=((phase>>8)&7)/8.
                    a=float(waves[mode,index]);b=float(waves[mode,(index+1)&31]);value=a+(b-a)*fraction
                    numerator+=target[n]*value;denominator+=value*value
                gain=max(1,min(15,int(round(numerator/max(denominator,1e-12)))))
                loss=0.
                for n in samples:
                    phase=(int(phases[n])+rotation*2048)&65535
                    index=phase>>11;fraction=((phase>>8)&7)/8.
                    a=float(waves[mode,index]);b=float(waves[mode,(index+1)&31])
                    delta=target[n]-gain*(a+(b-a)*fraction);loss+=delta*delta
                if loss<best:
                    best=loss;new_g[row]=gain;new_m[row]=mode
                    new_o[row]=(int(offsets[row])+rotation*2048)&65535
    return new_g,new_m,new_o
