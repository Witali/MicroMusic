"""Resumable private-corpus benchmark for bounded v5 LPC/excitation refinement."""
import argparse,ast,hashlib,importlib.metadata,json,time
from pathlib import Path
import numpy as np
import soundfile as sf
from batch_decoder import BatchSession
import speech_compact as compact
from standard_metrics import error_metrics,pwm_duties,pwm_pcm16
from refine_speech_lpc import refine
ROOT=Path.cwd();BUILD=(ROOT/"build").resolve()
def sha(b):return hashlib.sha256(b).hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def load(p):return json.loads(Path(p).read_text())
def save(path,value):
 path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+".writing")
 tmp.write_text(json.dumps(value,indent=2,allow_nan=False)+"\n",encoding="utf-8",newline="\n");tmp.replace(path)
def wav(p):
 x,rate=sf.read(p,dtype="int16");assert rate==8000 and x.ndim==1;return x
def quality(x,y):
 q={"pcm16":error_metrics(x,y,True),"pwm8":error_metrics(x,pwm_pcm16(y),True)}
 for v in q.values():
  if v["stoi"] is not None and not np.isfinite(v["stoi"]):v["stoi"]=None
 return q
def floors(a,b):
 for domain in ("pcm16","pwm8"):
  if a[domain]["error_energy"]>b[domain]["error_energy"]:return False
  s,t=a[domain]["stoi"],b[domain]["stoi"]
  if t is not None and (s is None or s<t-1e-12):return False
 return True
def sources():
 tools=ROOT/"Codecs/LPX/01_ACTIVE_Q0_CODEC/tools";files=set();pending=[Path(__file__).resolve()]
 while pending:
  p=pending.pop()
  if p in files:continue
  files.add(p)
  for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
   names=[n.name for n in node.names] if isinstance(node,ast.Import) else [node.module] if isinstance(node,ast.ImportFrom) and node.module else []
   for name in names:
    target=tools/(name.split(".")[0]+".py")
    if target.is_file() and target not in files:pending.append(target)
 files.update(p for p in (ROOT/"Codecs/LPX/01_ACTIVE_Q0_CODEC/src").glob("*") if p.is_file())
 return {str(p.relative_to(ROOT)).replace("\\","/"):sha(p.read_bytes()) for p in sorted(files)}
def run(args):
 start=time.perf_counter();source=sources();source_key=sha(canonical(source));manifest_path=args.manifest.resolve();manifest=load(manifest_path)
 assert manifest["schema"]=="lpx-v5-joint-corpus-private-v1"
 cases=manifest["cases"]
 if args.subset:
  subset=load(args.subset);wanted=set(subset["ids"] if isinstance(subset,dict) else subset)
  cases=[c for c in cases if c["id"] in wanted];assert len(cases)==len(wanted)
 if args.limit_cases:cases=cases[:args.limit_cases]
 output=args.output.resolve();assert output.is_relative_to(BUILD) and output!=BUILD
 output.mkdir(parents=True,exist_ok=True)
 settings={"frame_limit":args.frame_limit,"spectral_candidates":args.spectral_candidates,"lookahead":args.lookahead,"excitation_horizon":args.excitation_horizon,"passes":args.passes,"refit":not args.no_refit}
 counters={"fits_executed":0,"fits_reused":0,"serialized_receiver_checks":0};rows=[]
 env={"source_sha256":source,"packages":{name:importlib.metadata.version(name) for name in ("numpy","numba","scipy","pystoi","soundfile")}}
 report={"schema":"lpx-v5-lpc-corpus-v1","status":"running","manifest_sha256":sha(manifest_path.read_bytes()),"environment":env,"settings":settings,"growth_percent":args.budgets,"case_count":len(cases),"expected_variants":len(cases)*2*len(args.budgets),"counters":counters,"cases":rows}
 with BatchSession("batch",speech=True,speech_compact=True,compact_only=True) as receiver:
  for ci,case in enumerate(cases):
   reference=wav(case["reference"]["path"]);assert sha(reference.astype("<i2").tobytes())==case["reference"]["pcm16_sha256"]
   for profile in case["profiles"]:
    for budget in profile["budgets"]:
     growth=budget["growth_percent"]
     if growth not in args.budgets:continue
     dest=output/case["id"]/str(profile["profile"])/f"growth-{growth:02d}"
     parts={k:[] for k in ("incumbent","candidate","raw")};sizes={k:0 for k in parts};segment_rows=[]
     for index,(segment,cap) in enumerate(zip(budget["incumbent"]["segments"],budget["segment_caps"])):
      assert segment["index"]==index;begin=segment["start"];n=segment["samples"];ref=reference[begin:begin+n]
      blob=Path(segment["path"]).read_bytes();assert sha(blob)==segment["stream_sha256"] and len(blob)==segment["file_bytes"]<=cap
      identity=sha(canonical([source_key,settings,sha(ref.astype("<i2").tobytes()),sha(blob),cap]))
      folder=dest/f"segment-{index:03d}";folder.mkdir(parents=True,exist_ok=True)
      cache_path=folder/"cache.json";cached=None
      if cache_path.exists():
       try:
        c=load(cache_path);candidate=(folder/"candidate.l4hy").read_bytes();raw=(folder/"raw.l4hy").read_bytes();tool=load(folder/"tool-report.json")
        if c["fingerprint"]==identity and c["candidate_sha256"]==sha(candidate) and c["raw_sha256"]==sha(raw) and c["report_sha256"]==sha(canonical(tool)):cached=(candidate,raw,tool)
       except (OSError,ValueError,KeyError):pass
      if cached is None:
       candidate,pcm,tool,raw=refine(ref,blob,receiver,cap,**settings);counters["fits_executed"]+=1
       assert np.array_equal(pcm,compact.decode_model(candidate))
       (folder/"input.l4hy").write_bytes(blob);(folder/"candidate.l4hy").write_bytes(candidate);(folder/"raw.l4hy").write_bytes(raw)
       save(folder/"tool-report.json",tool);save(cache_path,{"fingerprint":identity,"candidate_sha256":sha(candidate),"raw_sha256":sha(raw),"report_sha256":sha(canonical(tool))})
      else:candidate,raw,tool=cached;counters["fits_reused"]+=1
      for tag,content in (("incumbent",blob),("candidate",candidate),("raw",raw)):
       assert len(content)<=cap
       fields=compact.unpack(content);assert fields[0]==n and fields[1]==profile["profile"]
       model=compact.decode_model(content);received=receiver.decode_one_s16(content,n)
       assert received is not None and np.array_equal(received,model)
       assert np.array_equal(receiver.decode_one(content,n),pwm_duties(model))
       parts[tag].append(model);sizes[tag]+=len(content);counters["serialized_receiver_checks"]+=1
      segment_rows.append({"index":index,"start":begin,"samples":n,"cap_bytes":cap,"input_bytes":len(blob),"input_sha256":sha(blob),"candidate_bytes":len(candidate),"candidate_sha256":sha(candidate),"raw_bytes":len(raw),"raw_sha256":sha(raw)})
     arrays={k:np.concatenate(v) for k,v in parts.items()};measures={k:quality(reference,y) for k,y in arrays.items()}
     assert measures["incumbent"]==budget["incumbent"]["metrics"]
     eligible=[k for k in parts if floors(measures[k],measures["incumbent"])]
     chosen=min(eligible,key=lambda k:(measures[k]["pcm16"]["error_energy"],measures[k]["pwm8"]["error_energy"],sizes[k],("incumbent","candidate","raw").index(k)))
     selected=arrays[chosen]
     for tag,y in arrays.items():sf.write(dest/f"{tag}.wav",y,8000,subtype="PCM_16")
     sf.write(dest/"selected.wav",selected,8000,subtype="PCM_16")
     for seg in segment_rows:
      content=Path(budget["incumbent"]["segments"][seg["index"]]["path"]).read_bytes() if chosen=="incumbent" else (dest/f'segment-{seg["index"]:03d}'/(chosen+".l4hy")).read_bytes()
      (dest/f'segment-{seg["index"]:03d}.l4hy').write_bytes(content)
     row={k:case[k] for k in ("id","kind","cohort","language","condition","samples")}|{"profile":profile["profile"],"growth_percent":growth,"incumbent_tag":budget["incumbent_tag"],"original_bytes":profile["original_bytes"],"incumbent_bytes":sizes["incumbent"],"candidate_bytes":sizes["candidate"],"raw_bytes":sizes["raw"],"file_bytes":sizes[chosen],"complete_stream_cap_bytes":budget["complete_stream_cap_bytes"],"original_metrics":profile["original_metrics"],"incumbent":measures["incumbent"],"candidate":measures["candidate"],"raw":measures["raw"],"selected":measures[chosen],"selected_variant":chosen,"quality_improved":measures[chosen]["pcm16"]["error_energy"]<measures["incumbent"]["pcm16"]["error_energy"],"reference_pcm16_sha256":case["reference"]["pcm16_sha256"],"output_pcm16_sha256":sha(selected.astype("<i2").tobytes()),"output_pwm_sha256":sha(pwm_duties(selected).tobytes()),"segments":segment_rows}
     rows.append(row);save(dest/"report.json",row);report["elapsed_seconds"]=time.perf_counter()-start;save(output/"results.json",report)
     print(json.dumps({"case_index":ci+1,"cases":len(cases),"profile":profile["profile"],"growth_percent":growth,"quality_improved":row["quality_improved"],"selected_variant":chosen,"file_bytes":row["file_bytes"]}),flush=True)
 assert sources()==source,"Source changed during benchmark; rerun with stable code."
 report.update(status="complete",completed_variants=len(rows),elapsed_seconds=time.perf_counter()-start);save(output/"results.json",report)
 print(json.dumps({"completed_variants":len(rows),"counters":counters,"elapsed_seconds":report["elapsed_seconds"]}),flush=True)
if __name__=="__main__":
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("--manifest",type=Path,default=Path("build/v5-joint/corpus/strong-private.json"));p.add_argument("--subset",type=Path);p.add_argument("--output",type=Path,required=True);p.add_argument("--limit-cases",type=int);p.add_argument("--budgets",type=int,nargs="+",default=[0,5,10],choices=(0,5,10));p.add_argument("--frame-limit",type=int,default=32);p.add_argument("--spectral-candidates",type=int,default=2);p.add_argument("--lookahead",type=int,default=640);p.add_argument("--excitation-horizon",type=int,default=80);p.add_argument("--passes",type=int,default=1);p.add_argument("--no-refit",action="store_true")
 run(p.parse_args())
