from viterbi49 import *
sys.path.insert(0,str(V48));from quad48 import quad
# Additional local passes, same starting point and number of passes as Viterbi.
def run(c):
 _,d,meta,ref,lv,x=data(c);md=model(d,meta);raw,rep,uniq,K,H,_=md;z=np.load(V48/c/'direct-quad.npy');idx=ids(z,raw,uniq);r=filt(ref.astype(float)/32768);r-=r.mean();rows=[]
 for j in range(2):
  t=time.time();ya,lag,beta=align(r,filt_raw(uniq[idx].ravel()));ee=ya-r;ch=quad(idx,ee,K,beta,lag,2*j,j==1);m=evaluate(ref,render(rep[idx],d,meta));rows.append(dict(passno=j+1,changes=int(ch),seconds=time.time()-t,**m));print(c,rows[-1],flush=True)
 (ROOT49/c/'quad-control.json').write_text(json.dumps(rows,indent=2))
 zz=np.load(ROOT49/c/'direct-viterbi.npy');zz,rows=optimize(zz,d,meta,ref,md,'snr',((6,96,24,False),));(ROOT49/c/'direct-729.json').write_text(json.dumps(rows,indent=2));np.save(ROOT49/c/'direct-729.npy',zz);wavfile.write(ROOT49/c/'direct-729.wav',48000,render(zz,d,meta))
if __name__=='__main__':run(sys.argv[1])
