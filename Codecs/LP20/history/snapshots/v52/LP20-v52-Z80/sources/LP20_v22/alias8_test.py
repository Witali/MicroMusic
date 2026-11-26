from repack import *
os.environ['LP20_ALIAS8']='1'
for name in ['first','second']:
 p=HERE/name/'exact';m=json.loads((HERE.parent/'LP20_v21_rollout'/name/'decoder.json').read_text());d=dict(np.load(p/'model.npz'));out=HERE/name/'exact_alias';buildcheck(d,out,m)
