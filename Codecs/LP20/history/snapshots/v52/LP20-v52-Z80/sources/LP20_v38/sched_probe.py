from probe import *
import period_share as ps
# Set globals for baseline eight working banks.
builder.ALIAS8=True;builder.ALIAS_ZERO=False;builder.NB=9;builder.DP=18;builder.PTR_LO=19;builder.PTR_HI=21;builder.PAIR_LO=23;builder.PAIR_HI=24;builder.SHORTMAX=241;builder.THRESHOLD=24;builder.SHIFT=0x27
acts=builder.actions(); print('actions',len(acts),sum(x[0] for x in acts));_,ranges,tails=st.choose(acts,320,8,m['grid'],builder.emit); print(ranges,tails)
