from adaptive45 import *
for clip in ('first','second'):
 base=BASE/'input'/clip;d=dict(np.load(base/'model.npz'));meta=json.loads((base/'decoder.json').read_text());ref=wavfile.read(base/'reference.wav')[1];x=d['target'];v=render(x,d,meta);m=metrics(ref,v);print(clip,json.dumps(m),flush=True);wavfile.write(ROOT/clip/'direct-pwm.wav',48000,v);(ROOT/clip/'direct-pwm.json').write_text(json.dumps(m,indent=2))
