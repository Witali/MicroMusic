"""Lossless musical-event JSON import for external SMF MIDI files.

Tracks, event order, ticks, channel messages, metadata and SysEx payloads are
retained as structured data. No MIDI binary is copied into the repository.
"""
from pathlib import Path
from collections import defaultdict
import argparse
import hashlib
import json
import struct

SCHEMA='micromusic-midi-events'


def describe_parts(document):
    """Add human-readable track/instrument summaries without discarding events."""
    labels=json.loads(Path(__file__).with_name('gm-instruments.json').read_text(encoding='utf-8'))
    names={row['program']:row['name'] for row in labels['programs']}
    timeline=defaultdict(list)
    for track in document['tracks']:
        for event in track['events']:
            if event['type']=='programChange':timeline[event['channel']].append(event)
    for events in timeline.values():events.sort(key=lambda e:e['tick'])
    for track in document['tracks']:
        events=track['events'];attacks=[e for e in events if e['type']=='noteOn' and e['velocity']>0]
        titles=[e['text'] for e in events if e['type']=='text' and e['metaType']==3]
        instruments=set()
        for note in attacks:
            changes=[e for e in timeline[note['channel']] if e['tick']<=note['tick']]
            program=changes[-1]['program'] if changes else 0
            instruments.add((note['channel'],program))
        track['name']=titles[0] if titles else f'Track {track["index"]}'
        track['summary']=dict(noteOnCount=len(attacks),channels=sorted({e['channel'] for e in events if 'channel' in e}),
            pitchRange=[min(e['note'] for e in attacks),max(e['note'] for e in attacks)] if attacks else None,
            firstNoteTick=min((e['tick'] for e in attacks),default=None),endTick=max((e['tick'] for e in events),default=0),
            instruments=[dict(channel=c,program=p,name='GM percussion' if c==9 else names[p],percussion=c==9)
                         for c,p in sorted(instruments)])
    document['numbering']='Zero-based MIDI channels0..15 and General MIDI programs0..127; channel9 is percussion'
    document['tempoMap']=[dict(track=t['index'],tick=e['tick'],microsecondsPerQuarter=e['microsecondsPerQuarter'],bpm=60_000_000/e['microsecondsPerQuarter'])
                          for t in document['tracks'] for e in t['events'] if e['type']=='tempo']
    document['timeSignatures']=[dict(track=t['index'],tick=e['tick'],numerator=e['numerator'],denominator=e['denominator'])
                               for t in document['tracks'] for e in t['events'] if e['type']=='timeSignature']
    return document


def vlq(data, position):
    value=0
    for _ in range(4):
        if position>=len(data):raise ValueError('Truncated MIDI VLQ')
        byte=data[position];position+=1;value=value*128+(byte&127)
        if byte<128:return value,position
    raise ValueError('MIDI VLQ exceeds four bytes')


def from_midi(path):
    path=Path(path);raw=path.read_bytes()
    if len(raw)<14 or raw[:4]!=b'MThd':raise ValueError('Truncated or missing MIDI header')
    size,fmt,count,division=struct.unpack_from('>IHHH',raw,4)
    if size<6 or size+8>len(raw) or fmt not in (0,1) or not count or not division or division&32768:
        raise ValueError('Unsupported MIDI header, format or PPQN')
    result=dict(schema=SCHEMA,version=1,format=fmt,ppqn=division,
        source=dict(fileName=path.name,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()),tracks=[])
    if size>6:result['headerExtraHex']=raw[14:8+size].hex()
    cursor=8+size
    for index in range(count):
        if cursor+8>len(raw) or raw[cursor:cursor+4]!=b'MTrk':raise ValueError('Missing MIDI track')
        length=int.from_bytes(raw[cursor+4:cursor+8],'big')
        if cursor+8+length>len(raw):raise ValueError('Truncated MIDI track')
        data=raw[cursor+8:cursor+8+length];cursor+=8+length
        events=[];position=tick=0;running=None
        while position<len(data):
            delta,position=vlq(data,position);tick+=delta
            if position>=len(data):raise ValueError('Missing MIDI event status')
            status=data[position]
            if status>=128:position+=1
            elif running is not None:status=running
            else:raise ValueError('Missing running MIDI status')
            event=dict(tick=tick,delta=delta,status=status)
            if status==255:
                if position>=len(data):raise ValueError('Truncated meta event')
                kind=data[position];position+=1;length,position=vlq(data,position)
                if position+length>len(data):raise ValueError('Truncated meta payload')
                payload=data[position:position+length];position+=length;running=None
                event.update(type='meta',metaType=kind,dataHex=payload.hex())
                if kind==81:
                    if len(payload)!=3 or not int.from_bytes(payload,'big'):
                        raise ValueError('MIDI tempo must contain three bytes and be positive')
                    event.update(type='tempo',microsecondsPerQuarter=int.from_bytes(payload,'big'))
                elif kind==88 and len(payload)==4:event.update(type='timeSignature',numerator=payload[0],denominator=2**payload[1],clocksPerClick=payload[2],thirtySecondsPerQuarter=payload[3])
                elif kind in (1,2,3,4,5,6,7):event.update(type='text',text=payload.decode('cp1252',errors='replace'))
                elif kind==47:event['type']='endOfTrack'
            elif status in (240,247):
                length,position=vlq(data,position)
                if position+length>len(data):raise ValueError('Truncated SysEx payload')
                event.update(type='systemExclusive',dataHex=data[position:position+length].hex());position+=length;running=None
            elif 128<=status<=239:
                running=status;op=status&240;length=1 if op in (192,208) else 2
                if position+length>len(data):raise ValueError('Truncated channel event')
                values=data[position:position+length];position+=length
                if any(v>=128 for v in values):raise ValueError('Invalid channel data byte')
                event['channel']=status&15
                if op in (128,144):event.update(type='noteOff' if op==128 else 'noteOn',note=values[0],velocity=values[1])
                elif op==160:event.update(type='polyphonicPressure',note=values[0],pressure=values[1])
                elif op==176:event.update(type='controlChange',controller=values[0],value=values[1])
                elif op==192:event.update(type='programChange',program=values[0])
                elif op==208:event.update(type='channelPressure',pressure=values[0])
                elif op==224:event.update(type='pitchBend',value=values[0]+128*values[1])
            else:raise ValueError(f'Unsupported MIDI status {status}')
            events.append(event)
        result['tracks'].append(dict(index=index,events=events))
    if cursor<len(raw):result['trailingDataHex']=raw[cursor:].hex()
    return describe_parts(result)


def load(path):
    path=Path(path)
    if path.suffix.lower()!='.json':return from_midi(path)
    result=json.loads(path.read_text(encoding='utf-8-sig'))
    if result.get('schema')!=SCHEMA or result.get('version')!=1 or type(result.get('ppqn')) is not int or result['ppqn']<=0:
        raise ValueError('Unsupported musical event JSON')
    for track in result['tracks']:
        previous=0
        for event in track['events']:
            if type(event['tick']) is not int or event['tick']<previous:raise ValueError('JSON event ticks must be ordered integers')
            if event.get('type')=='tempo' and (type(event.get('microsecondsPerQuarter')) is not int or not 1<=event['microsecondsPerQuarter']<=0xffffff):
                raise ValueError('JSON tempo must be a positive three-byte integer')
            previous=event['tick']
    return result


def notes(document):
    all_notes=[];tempos=[]
    for track in document['tracks']:
        active=defaultdict(list);tick=0
        for event in track['events']:
            tick=event['tick'];kind=event['type']
            if kind=='tempo':tempos.append((tick,event['microsecondsPerQuarter']))
            elif kind in ('noteOn','noteOff'):
                key=(event['channel'],event['note']);velocity=event['velocity']
                if kind=='noteOn' and velocity>0:active[key].append((tick,velocity))
                elif active[key]:
                    start,level=active[key].pop(0)
                    if tick>start:all_notes.append((track['index'],key[0],key[1],start,tick,level))
        for (channel,pitch),items in active.items():
            for start,level in items:
                if tick>start:all_notes.append((track['index'],channel,pitch,start,tick,level))
    tempos.sort()
    return all_notes,document['ppqn'],round(60_000_000/(tempos[0][1] if tempos else 500000))


def main():
    import sys
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args()
    if args.output.suffix.lower()!='.json':parser.error('Output must be .json')
    try:document=describe_parts(load(args.input))
    except (ValueError,IndexError,KeyError,OSError,struct.error) as error:parser.exit(1,f'Conversion failed: {error}\n')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(document,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(f'{len(document["tracks"])} tracks, {sum(t["summary"]["noteOnCount"] for t in document["tracks"])} note attacks → {args.output}')


if __name__=='__main__':main()
