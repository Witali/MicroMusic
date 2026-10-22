#!/usr/bin/env python3
"""Buffer-occupancy model from a hypothetical measured 4-category AVR cycle profile.
This proves neither the timing of C++ code nor the real ISR phase on a chip.
Its purpose is to consume REAL measurement results collected by the profiling sketch.
"""
import argparse, json

def simulate(n:int,costs:list[int],isr:int=80,prebuffer:int=384,target:int=480,
             ring:int=512,stall_interval:int=0,stall_cycles:int=0):
    assert n>0 and len(costs)==4 and all(c>0 for c in costs)
    assert 0<prebuffer<target<ring
    level=min(prebuffer,n);made=level;played=0;next_irq=2000;now=0
    underruns=0;min_level=level;max_level=level;first_bad=None
    def tick():
        nonlocal next_irq,now,played,level,underruns,min_level,first_bad
        if level:
            level-=1;played+=1
        elif made<n:
            underruns+=1
            if first_bad is None:first_bad=played
        next_irq+=2000
        # ISR overhead consumes cycles in foreground time; account conservatively
        now+=isr
        min_level=min(level,min_level)
    while played<n:
        if level<target and made<n:
            i=made
            cat=3 if i%160==0 else 2 if i%80==0 else 1 if i%20==0 else 0
            delay=costs[cat]
            if stall_interval and i%stall_interval==0:delay+=stall_cycles
            done=now+delay
            while next_irq<=done:
                # fire interrupt at an ideal 2,000-cycle wall-clock cadence
                now=max(now,next_irq)
                tick()
                if played==n:break
            now=max(now,done)
            if level<ring-1 and made<n:
                level+=1;made+=1
        else:
            now=max(now,next_irq)
            tick()
        max_level=max(level,max_level)
    return {'samples':n,'cpu_mhz':16,'sample_rate':8000,'buffer_bytes':ring,
            'costs_cycles_by_category':costs,'extra_isr_cycles':isr,
            'underruns':underruns,'first_bad_sample':first_bad,
            'minimum_buffer_level':min_level,'maximum_buffer_level':max_level}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--samples',type=int,default=80000)
    p.add_argument('--cycles',type=int,nargs=4,default=[700,1300,10000,25000],metavar=('NORMAL','SUB20','BLOCK80','FRAME160'))
    p.add_argument('--isr',type=int,default=80)
    p.add_argument('--stall-every',type=int,default=0)
    p.add_argument('--stall-cycles',type=int,default=0)
    a=p.parse_args();print(json.dumps(simulate(a.samples,a.cycles,a.isr,stall_interval=a.stall_every,stall_cycles=a.stall_cycles),indent=2))
