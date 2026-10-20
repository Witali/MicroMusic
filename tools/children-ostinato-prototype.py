"""Read-only Children accompaniment analysis; output is an ignored JSON report.

No firmware, bank or source events are changed. Quantization/reduction and
subsequent lossless compression are measured separately. No MIDI is retained.
"""
from collections import Counter
from pathlib import Path
import hashlib
import importlib.util
import json
import math

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'ATtiny13A/Music/reference/children/source-events.json'
STOP=107*16
DURATIONS=(1,2,3,4,6,8,16)


def module(name,filename):
    spec=importlib.util.spec_from_file_location(name,ROOT/'tools'/filename)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


reader=module('ostinato_reader','midi-reader.py')
packer=module('ostinato_packer','pack-score.py')


def selected_grid(notes,ppqn,tracks,mode,highest=False):
    events=[]
    for identity,note in enumerate(notes):
        if note[0] not in tracks or note[3]*4>=STOP*ppqn:continue
        if mode=='ceil-floor':
            start=math.ceil(note[3]*4/ppqn);end=math.floor(note[4]*4/ppqn)
        else:
            start=round(note[3]*4/ppqn);end=max(start+1,round(note[4]*4/ppqn))
        if start<min(STOP,end):events.append(dict(pitch=note[2],start=start,end=min(STOP,end),identity=identity,track=note[0]))
    grid=[]
    for unit in range(STOP):
        active=[e for e in events if e['start']<=unit<e['end']]
        key=(lambda e:(e['pitch'],e['start'])) if highest else (lambda e:(e['start'],-e['track'],e['pitch']))
        grid.append(max(active,key=key) if active else None)
    return grid


def symbols(grid):
    # Attack identity remains explicit even when pitch equals its predecessor.
    return [-1 if n is None else n['pitch'] if u==0 or grid[u-1] is None or n['identity']!=grid[u-1]['identity'] else -2 for u,n in enumerate(grid)]


def repair(data):
    """Byte-symbol RePair estimate, with an independently expanded equality check."""
    terminals=sorted(set(data));lookup={value:i for i,value in enumerate(terminals)}
    body=[lookup[v] for v in data];rules=[]
    while len(terminals)+len(rules)<255:
        frequencies=Counter(zip(body,body[1:]));best=None;occurrences=2
        for pair,count in frequencies.most_common():
            if count<=occurrences:break
            i=actual=0
            while i+1<len(body):
                if (body[i],body[i+1])==pair:actual+=1;i+=2
                else:i+=1
            if actual>occurrences:best=pair;occurrences=actual
        if best is None:break
        index=len(terminals)+len(rules);i=0;output=[]
        while i<len(body):
            if i+1<len(body) and (body[i],body[i+1])==best:output.append(index);i+=2
            else:output.append(body[i]);i+=1
        rules.append(best);body=output
    def expand(symbol):
        if symbol<len(terminals):return [terminals[symbol]]
        a,b=rules[symbol-len(terminals)];return expand(a)+expand(b)
    def depth(symbol):
        return 0 if symbol<len(terminals) else 1+max(map(depth,rules[symbol-len(terminals)]))
    assert [value for symbol in body for value in expand(symbol)]==list(data)
    return dict(rootBytes=len(body),pairRuleBytes=len(rules)*2,totalBytes=len(body)+len(rules)*2,
                terminalCount=len(terminals),ruleCount=len(rules),maximumNesting=max(map(depth,body),default=0),
                verifiedLossless=True,includesDecoderOrTerminalMap=False,root=body,rules=rules,terminals=terminals)


def timed_tokens(data):
    pitches=sorted({v for v in data if v>=0});rest=len(pitches);hold=rest+1
    pitch_index={pitch:i for i,pitch in enumerate(pitches)};stream=[];unit=0
    while unit<len(data):
        value=data[unit];end=unit+1
        if value==-1:
            while end<len(data) and data[end]==-1:end+=1
            pitch=rest
        else:
            while end<len(data) and data[end]==-2:end+=1
            pitch=hold if value==-2 else pitch_index[value]
        length=end-unit
        while length:
            duration=max(d for d in DURATIONS if d<=length)
            stream.append((pitch<<3)|DURATIONS.index(duration));length-=duration
            if pitch!=rest:pitch=hold
        unit=end
    return bytes(stream),pitches


def flat_pack(data):
    result=packer.pack(bytes(data),[bytes(data)],candidate_limit=96,max_entry_offset=255)
    return dict(storageBytes=len(result['storage']),playlistBytes=len(result['playlist']),
                totalBytes=len(result['storage'])+len(result['playlist']),verifiedLossless=result['report']['verifiedLossless'],
                maximumEntryOffset=max(result['offsets'].values()),globallyMinimal=False)


def summarize(grid):
    data=symbols(grid);bars=[tuple(data[i:i+16]) for i in range(0,STOP,16)]
    normalized=[]
    for bar in bars:
        base=next((v for v in bar if v>=0),0)
        normalized.append(tuple(('pitch',v-base) if v>=0 else ('control',v) for v in bar))
    stream,pitches=timed_tokens(data)
    return dict(attacks=sum(v>=0 for v in data),exactBarPatterns=len(set(bars)),
                transpositionNormalizedBarPatterns=len(set(normalized)),pitches=pitches,
                timedCommandBytes=len(stream),flatTimedPacking=flat_pack(stream),
                hierarchicalGridEstimate=repair(data))


def symbol_packing(sequence):
    values=list(dict.fromkeys(sequence));ids=[values.index(value) for value in sequence]
    valid=[v for v in range(224) if v&7!=7]
    mapped=bytes(valid[v] for v in ids)
    assert [values[valid.index(v)] for v in mapped]==list(sequence)
    result=dict(symbolCount=len(values),symbols=values,rawSelectorBytes=len(ids),
                flatSelectors=flat_pack(mapped),selectorCodec='ranked byte alphabet0..223 excluding low-three-bits7; rank=byte-(byte>>3)')
    if len(values)<=28:
        runs=[]
        for value in ids:
            if runs and runs[-1][0]==value and runs[-1][1]<7:runs[-1][1]+=1
            else:runs.append([value,1])
        raw=bytes((value<<3)|(count-1) for value,count in runs)
        assert [values[value] for value,count in runs for _ in range(count)]==list(sequence)
        result.update(rleBytes=len(raw),rleFlat=flat_pack(raw),rleCodec='symbolIndex high5bits; runLength1..7 low3bits+1')
    return result


def main():
    notes,ppqn,bpm=reader.read_midi(SOURCE)
    source=json.loads(SOURCE.read_text(encoding='utf-8'))
    strict=selected_grid(notes,ppqn,(2,3),'ceil-floor')
    nearest=selected_grid(notes,ppqn,(2,3),'nearest')
    bars=[-1 if nearest[u] is None else nearest[u]['pitch'] for u in range(0,STOP,16)]
    terminals=sorted(set(bars));root_ids=bytes(terminals.index(v) for v in bars)
    rle=[]
    for value in root_ids:
        if rle and rle[-1][0]==value and rle[-1][1]<7:rle[-1][1]+=1
        else:rle.append([value,1])
    rle_bytes=bytes((value<<3)|(count-1) for value,count in rle)
    decoded=[terminals[value] for value,count in rle for _ in range(count)]
    assert decoded==bars
    exact_attacks={(u,n['pitch']) for u,n in enumerate(nearest) if n is not None and (u==0 or nearest[u-1] is None or n['identity']!=nearest[u-1]['identity'])}
    generated={(bar*16+quarter*4,pitch) for bar,pitch in enumerate(bars) if pitch>=0 for quarter in range(4)}
    bass_symbols=symbols(selected_grid(notes,ppqn,(4,),'nearest'))
    bass_bars=[tuple(bass_symbols[u:u+16]) for u in range(0,STOP,16)]
    bass_native=symbol_packing(bass_bars)
    for bar in set(bass_bars):
        onsets=[u for u,v in enumerate(bar) if v>=0]
        assert len({v for v in bar if v>=0})<=1
        assert onsets in ([],[0],[0,4,8,12])
        assert all(v==-2 or v>=0 for v in bar)
    bass_native.update(verifiedSameAttacksAndGates=True,rhythmTypes=['quarter attacks, full-quarter gate','one attack at bar0, then hold','whole bar HOLD'],
                       dictionaryBytes=len(bass_native['symbols']),description='One packed byte per symbol: rootIndex0..2 plus rhythmType0..2; unchanged345 selected bass attacks.')
    glyphs=[]
    for bar in bass_bars:
        onsets=[u for u,v in enumerate(bar) if v>=0]
        if not onsets:glyphs.append(3);continue
        root=(37,34,29).index(bar[onsets[0]])
        glyphs.append(root|(4 if len(onsets)==4 else 0))
    fixed_blocks={}
    for width in (2,4,8):
        padded=glyphs+[3]*((-len(glyphs))%width)
        blocks=[tuple(padded[i:i+width]) for i in range(0,len(padded),width)]
        dictionary=list(dict.fromkeys(blocks));playlist=[dictionary.index(v) for v in blocks]
        assert [v for index in playlist for v in dictionary[index]][:len(glyphs)]==glyphs
        entry_bytes=math.ceil(width*3/8)
        selector_bits=max(1,(len(dictionary)-1).bit_length())
        fixed_blocks[str(width)]=dict(dictionary=dictionary,playlist=playlist,uniqueBlocks=len(dictionary),
            dictionaryBytes=len(dictionary)*entry_bytes,selectorBits=selector_bits,
            packedSelectorBytes=math.ceil(len(playlist)*selector_bits/8),
            totalBytes=len(dictionary)*entry_bytes+math.ceil(len(playlist)*selector_bits/8),
            nibbleSelectorTotalBytes=len(dictionary)*entry_bytes+math.ceil(len(playlist)/2) if len(dictionary)<=16 else None,
            verifiedExact=True,includesDecoder=False)
    bass_native.update(glyphs=glyphs,glyphCounts=dict(Counter(glyphs)),
        glyphEncoding='bits0..1:root(0=C#2/37,1=A#1/34,2=F1/29,3=HOLD); bit2=quarter retrigger',
        fixedBlockPacking=fixed_blocks)
    strings_grid=selected_grid(notes,ppqn,(5,),'nearest',highest=True)
    strings_bars=[-1 if strings_grid[u] is None else strings_grid[u]['pitch'] for u in range(0,STOP,16)]
    reduced_strings=symbol_packing(strings_bars)
    combined=symbol_packing(list(zip(bars,[bass_native['symbols'].index(v) for v in bass_bars],strings_bars)))
    combined['macroTableBytes']=len(combined['symbols'])*2
    combined['assumesMacroFields']='echoPitch4bits, bassSymbol3bits, stringPitch5bits; remaining4bits spare; pitch maps separate'
    combined['packedPayloadAndMacroTableBytes']=combined['flatSelectors']['totalBytes']+combined['macroTableBytes']
    report=dict(sourceFile=SOURCE.relative_to(ROOT).as_posix(),sourceJsonSha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        originalMidiSha256=source['source']['sha256'],ppqn=ppqn,quarterBpm=bpm,sourceQuarterBeats=428,
        unmodifiedCompleteLeadNotes=sum(n[0]==1 for n in notes),
        sourceEchoNotesBeforeEnd=sum(n[0] in (2,3) and n[3]<428*ppqn for n in notes),
        exactCeilFloorEcho=summarize(strict),nearestGridEcho=summarize(nearest),
        nativeLosslessBass=bass_native,reducedSustainedStrings=dict(losslessAgainstMidi=False,
            description='Highest active source pitch at bar boundary; sustain until next changed bar pitch or silence; main piano unchanged',**reduced_strings),
        combinedBarMacro=dict(losslessAgainstMidi=False,description='Reduced echo and strings plus exact nearest-grid bass; shared bar selectors avoid three independent play cursors',**combined),
        independentVoices={name:summarize(selected_grid(notes,ppqn,tracks,'nearest',highest))
                           for name,tracks,highest in [('lead',(1,),True),('bass',(4,),False),('strings',(5,),True)]},
        explicitMusicalReduction=dict(losslessAgainstMidi=False,description='Sample latest principal pitch at each source bar start; four quarter-note attacks per bar, each with an eighth-note gate; silent source bar starts stay silent. Main melody is unchanged.',
            barPitches=bars,pitchMapBytes=len(terminals),rawNibbleSelectorsBytes=math.ceil(len(bars)/2),
            rleBytes=len(rle_bytes),rleFlatPacking=flat_pack(rle_bytes),selectorFlatPacking=flat_pack(bytes(v<<3 for v in root_ids)),
            hierarchicalSelectors=repair(root_ids),generatedAttacks=len(generated),
            exactNearestGridOnsetsAndPitchesRetained=len(generated&exact_attacks),
            sourceNearestGridAttacks=len(exact_attacks),includesAvrDecoder=False),
        conclusions=['Exact echo needs substantially more than70-100B under the tested lossless schemes.',
                     'Transposition only reduces38 exact ceil/floor bar patterns to36, so it alone does not solve storage.',
                     'Independent per-part compression avoids unified-stream HOLD fragmentation but requires separate cursors/counters in AVR.',
                     'Hierarchical estimates exclude decoder and per-part nesting stacks; these cannot be treated as free within64B SRAM.',
                     'The short bar-root option is a declared accompaniment reduction followed by verified lossless packing, not lossless MIDI compression.'])
    target=ROOT/'build/children-ostinato-analysis.json';target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({name:report[name] for name in ('unmodifiedCompleteLeadNotes','sourceEchoNotesBeforeEnd')},indent=2))
    for key in ('exactCeilFloorEcho','nearestGridEcho'):
        row=report[key];print(key,'attacks',row['attacks'],'bars',row['exactBarPatterns'],'flat',row['flatTimedPacking']['totalBytes'],'hierarchical',row['hierarchicalGridEstimate']['totalBytes'])
    reduced=report['explicitMusicalReduction'];print('reduced selectors',reduced['selectorFlatPacking']['totalBytes'],'RLE+flat',reduced['rleFlatPacking']['totalBytes'],'pitchMap',reduced['pitchMapBytes'])


if __name__=='__main__':main()
