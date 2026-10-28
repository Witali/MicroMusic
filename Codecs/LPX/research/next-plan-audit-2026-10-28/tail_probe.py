import json
from batch_decoder import BatchSession
from speech_compact import repack,decode_model
from test_speech_v4 import fixture
rows=[]
with BatchSession('batch',speech=True,speech_compact=True,compact_only=True) as only, BatchSession('batch',speech=True,speech_compact=True) as common:
 for profile in (4,6):
  for n in (20,160,180,200,220,240,260,280,300,319,320,340,480,500):
   blob=repack(fixture(profile,n))[0];model=decode_model(blob)
   rows.append({'profile':profile,'samples':n,'model_samples':len(model),'common_accepts':common.decode_one_s16(blob,n) is not None,'compact_accepts':only.decode_one_s16(blob,n) is not None})
print(json.dumps(rows))
