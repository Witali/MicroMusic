from pathlib import Path
import struct, collections, statistics
R=None

def unpack(data):
 magic,ver,fl,rate,n,pre,bright,frm,block=struct.unpack_from('<4sBBHIHHHH',data)
 assert (magic,ver,rate,frm,block)==(b'L3AV',1,8000,160,80)
 o=20; b=[]; frames=[];total=0
 for i in range(0,n,160):
  start=o;tag=data[o];o+=1
  ncoef={0:0,1:10+(not(fl&2)),2:5,3:10,5:13+(not(fl&2)),6:10,7:5}[tag]
  o+=ncoef
  frames.append(data[start:o]);assert o<=len(data)
  for j in range(2):
   startblock=i+j*80
   if startblock>=n:continue
   nblock=min(80,n-startblock)
   m,scale=data[o:o+2];o+=2
   assert m in (2,3,4,5,6,0),m
   bs=(nblock*m+7)//8
   raw=data[o:o+bs];o+=bs
   if m==0:
    b.append({'bits':m,'scale':scale,'q':[0]*nblock,'bytes':bytes(data[o-bs-2:o]),'start':startblock})
    continue
   q=[];val=used=0
   for by in raw:
    val|=by<<used;used+=8
    while used>=m and len(q)<nblock:
     q.append((val&((1<<m)-1))-(1<<(m-1)));val>>=m;used-=m
   assert len(q)==nblock
   b.append({'bits':m,'scale':scale,'q':q,'bytes':bytes(data[o-bs-2:o]),'start':startblock})
 assert o==len(data),(o,len(data))
 assert sum(len(x['q']) for x in b)==n
 return {'sampleCount':n,'blocks':b,'frames':frames,'raw':data}

if __name__=='__main__':
 import argparse
 a=argparse.ArgumentParser();a.add_argument('files',nargs='+');args=a.parse_args()
 for filename in args.files:
  doc=unpack(Path(filename).read_bytes());blocks=doc['blocks']
  q=[s for bl in blocks for s in bl['q']]
  print(Path(filename).name,'bytes=',len(doc['raw']),'samples=',len(q),
        'blocks=',len(blocks),'modes=',dict(collections.Counter(z['bits'] for z in blocks)))
  for length in (2,3,4,8):
   pieces=[tuple(z['q'][i:i+length]) for z in blocks for i in range(0,len(z['q'])//length*length,length)]
   count=collections.Counter(pieces)
   print(' pattern_length=',length,'pieces=',len(pieces),'unique=',len(count),
         'repeated_pieces=',sum(v-1 for v in count.values()))
