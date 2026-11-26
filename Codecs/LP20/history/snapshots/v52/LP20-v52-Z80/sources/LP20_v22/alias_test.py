from repack import *
import shutil
for name in ['first','second']:
 p=HERE/name/'seven';m=json.loads((HERE.parent/'LP20_v21_rollout'/name/'decoder.json').read_text());d=dict(np.load(p/'model.npz'));out=HERE/name/'seven_alias';buildcheck(d,out,m);shutil.copy(p/'metrics.json',out/'metrics.json');shutil.copy(p/'v22.wav',out/'v22.wav')
