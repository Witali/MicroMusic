from decode_ph20 import *
summary={}
for name in ('first','second','new_ru'):
 out=HERE/name;source=ROOT/name/'training.npz';d=model(source);m=json.loads((V18/'release/compact/decoder.json').read_text());base,pt,r,z,u,v=inspect(d,d['y'],m);summary[name]={'baseline':base,'baseline_stream_bytes':len(d['idx']),'seconds':len(d['y'])/FS,'results':{}}
 for tag,payload,src,expected in ([('harmonic','sound.ph20',source,'corrected.npy')] if (out/'sound.ph20').exists() else [])+([('joint','joint.ph20',out/'entropy_training.npz' if name=='first' else source,'joint_state.npy')] if (out/'joint.ph20').exists() else [])+([('entropy','entropy.ph20',out/'entropy_training.npz',None)] if (out/'entropy.ph20').exists() else [])+([('local','local.ph20',out/'local_training.npz',None)] if (out/'local.ph20').exists() else []):
  ds=model(src);b=(out/payload).read_bytes();i0,y0,yy=unpack(ds,b);assert np.array_equal(y0,ds['y'])
  if expected:assert np.array_equal(yy,np.load(out/expected))
  md,full=make_file(ds,m,b,out/(tag+'.ph2f'));dd,mm,ix,y,cy=read_file(out/(tag+'.ph2f'));assert np.array_equal(cy,yy) and np.array_equal(ix,i0) and np.array_equal(y,y0);assert np.array_equal(dd['a'],ds['a'])
  met,_,rr,zz,*_=inspect(ds,yy,m,pt);rz=render(dd,mm,cy);rz=f.e.lp(rz,3500)[:len(zz)];assert np.max(np.abs(rz-rz.mean()-zz))<1e-6
  rec=dict(**met,stream_bytes=len(b),full_file_bytes=full,model_bytes=md,full_kbps=full*8*FS/len(y)/1000,stream_kbps=len(b)*8*FS/len(y)/1000,raw_tokens=len(ix),corrected_samples=int(np.count_nonzero(y!=cy)),roundtrip=True)
  summary[name]['results'][tag]=rec;print(name,tag,rec,flush=True)
 for tag in ('decoder_entropy','decoder_local'):
  if (out/(tag+'.test.json')).exists():summary[name]['rom']=json.loads((out/(tag+'.test.json')).read_text())
 if (ROOT/name/'sound.lp10g').exists():summary[name]['baseline_full_file_bytes']=(ROOT/name/'sound.lp10g').stat().st_size
(HERE/'summary.json').write_text(json.dumps(summary,indent=2))
