from pathlib import Path
import build_packed as p, opt_build as b
import sys
span=int(sys.argv[1]);levels=int(sys.argv[2]);b.widths_for=lambda period,levels:tuple(period//2+round((i-levels//2)*span/(levels//2)) for i in range(levels))
p.build(sys.argv[3],sys.argv[4],128,20,levels,1)
