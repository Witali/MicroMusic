"""Deterministic hand-authored legal fields; no signal fitting or codec imports."""
VECTORS=((1,3,5,7,9,11,13,15,17,19),(1,2,4,6,8,10,13,17,23,29),
    (0,1,2,3,4,7,12,18,25,31),(2,5,8,11,14,17,20,23,26,29))
SCALES=(8,12,16)
POSITIONS=(0,4,8,13,18)
ORIGINAL_EXTRAS=(30,39)
SAMPLES,START,END,HORIZON,CAPACITY=640,200,240,160,1


def cases(profile):
    if profile not in (4,6):raise ValueError('Expected profile 4 or 6')
    index=0
    for spectral_index in range(4):
        for scale in SCALES:
            for position in POSITIONS:
                for original in ORIGINAL_EXTRAS:
                    yield dict(profile=profile,index=index,spectral_index=spectral_index,scale=scale,
                        mandatory_position=position,original_extra_position=original)
                    index+=1


def fields(case,target=False):
    profile=case['profile'];factor=1 if profile==4 else 2;amp=8 if profile==4 else 7
    vector=[factor*v for v in VECTORS[case['spectral_index']]]
    spectra=[vector.copy(),vector.copy()];params=[[case['scale'],40,0] for _ in range(4)]
    pulses=[[5,amp if not i%2 else -amp] for i in range(32)]
    pulses[10][0]=case['mandatory_position']
    extras=[[-1,0] for _ in range(16)]
    extras[5]=[case['mandatory_position'] if target else case['original_extra_position'],-amp]
    return spectra,params,pulses,extras


def old_positions(peak,original,valid=40):
    return sorted({peak}|{p for p in (original-1,original,original+1) if 0<=p<valid})
