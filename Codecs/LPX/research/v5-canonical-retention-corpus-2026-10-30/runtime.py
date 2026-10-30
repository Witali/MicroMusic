"""Explicit source loading and private atomic receipts for the replay driver."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import time

from saved_corpus import sha

HERE = Path(__file__).resolve().parent
CORE = '5a6cd1ab9593cac6f7e81756a639fa11d6c21276'


def load_module(name,path):
    spec = importlib.util.spec_from_file_location(name,Path(path).resolve())
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def save(path,value):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_symlink() or path.exists() and path.stat().st_nlink > 1:
        raise ValueError('Output aliases are forbidden')
    raw = (json.dumps(value,indent=2,allow_nan=False)+'\n').encode('utf-8')
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_bytes(raw)
    for index in range(6):
        try:
            os.replace(temporary,path)
            return
        except PermissionError:
            if index == 5:
                raise
            time.sleep(.01*(index+1))


def source_snapshot():
    return {path.name:sha(path.read_bytes()) for path in HERE.iterdir() if path.suffix in ('.py','.md')}


def full_audit_gate(study,audit,auditor_path,inputs):
    receipt = json.loads(inputs.read(audit/'audit-private.json'))
    for path in (audit/'audit.json',audit/'groups.json',auditor_path):
        inputs.read(path)
    binding_raw = inputs.read(study/'binding-private.json')
    if (receipt['status'] != 'passed' or receipt['completed_records'] != 118
            or receipt['expected_records'] != 118 or receipt['missing_records']
            or not receipt['all_final_worker_receipts_verified']
            or receipt['binding_sha256'] != sha(binding_raw)
            or receipt['auditor_sha256'] != sha(auditor_path.read_bytes())
            or receipt['source_core_commit'] != CORE):
        raise ValueError('A matching complete independent 118-record audit PASS is required')
    return receipt


def target_for(item,auditor,equal):
    reference = auditor.reference(item['record'])
    plan = auditor.C.plan_level(reference,item['saved']['mode'])
    target,clips = auditor.C.quantize_target(reference,plan)
    if clips:
        raise ValueError('The declared target level clipped')
    for name in ('policy','gain','gain_db','output_level_matches_original'):
        equal(plan[name],item['saved']['level'][name],'target-level-'+name)
    equal(sha(target.astype('<i2').tobytes()),item['saved']['target_reference_pcm16_sha256'],'target-hash')
    equal(len(target),item['record']['samples'],'whole-target-samples')
    return target
