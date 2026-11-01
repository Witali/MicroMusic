"""Reject scope drift/trimming and prove 24-bit external metadata stays wide."""
import unittest
import sys
from pathlib import Path
import tempfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_cases import planned_rows
from run_player import plan_rows,long_partition
from spi_player import ROOT,header,load,save


class WindowsBusy(PermissionError):
    winerror=32


def fixture():
    chains=[dict(id='long-%03d'%i,kind='long',profile=4 if i<4 else 6,samples=3786111,sizes=[100]*60)
            for i in range(1,7)]
    chains += [dict(id='short-p%d'%p,kind='short',profile=p,samples=160,sizes=[100]) for p in (4,6)]
    return dict(chains=chains,rows=planned_rows(chains))


class PlayerPlanContracts(unittest.TestCase):
    def test_fixed_plan_accepts_only_28_rows(self):
        value=fixture();self.assertEqual(len(plan_rows(value)),8)
        self.assertEqual(sum(row['storage']=='spi' for row in value['rows']),20)

    def test_long_c_or_duplicate_rows_fail(self):
        for change in ('long-c','duplicate'):
            value=fixture()
            if change=='long-c':value['rows'][0]['assembly']=False
            else:value['rows'][-1]=value['rows'][-2].copy()
            with self.assertRaises(ValueError):plan_rows(value)

    def test_trimmed_chain_fails(self):
        value=fixture();value['chains'][0]['samples']-=1
        with self.assertRaises(ValueError):plan_rows(value)

    def test_four_shards_preserve_exactly_six_complete_chains(self):
        ids=['long-%03d'%i for i in range(1,7)]
        groups=[long_partition(ids,shard) for shard in range(4)]
        self.assertEqual([2*len(group) for group in groups],[4,4,2,2])
        self.assertEqual(set.union(*groups),set(ids))
        self.assertEqual(sum(map(len,groups)),6)

    def test_external_metadata_does_not_narrow(self):
        text=header(dict(offsets=[0x010203],sizes=[65535]))
        self.assertIn('66051UL',text)
        self.assertIn('uint32_t lpx_spi_offsets',text)
        with self.assertRaises(ValueError):header(dict(offsets=[0xfffff0],sizes=[100]))

    def fresh(self):
        root=ROOT/'build/spi-player/save-contracts';root.mkdir(parents=True,exist_ok=True)
        # Retain these tiny ignored contract files; no recursive cleanup/rerun.
        return Path(tempfile.mkdtemp(dir=root))/'state.json'

    def test_transient_windows_replace_retries_only_the_write(self):
        target=self.fresh();original=Path.replace;calls=[]
        def replace(path,destination):
            calls.append(1)
            if len(calls)<3:raise WindowsBusy('transient sharing')
            return original(path,destination)
        with patch.object(Path,'replace',replace),patch('spi_player.time.sleep'):
            save(target,dict(value=1))
        self.assertEqual(len(calls),3);self.assertEqual(load(target),dict(value=1))

    def test_final_replace_failure_keeps_old_and_pending_bytes(self):
        target=self.fresh();save(target,dict(value=1))
        with patch.object(Path,'replace',side_effect=WindowsBusy('busy')),patch('spi_player.time.sleep'):
            with self.assertRaises(PermissionError):save(target,dict(value=2))
        self.assertEqual(load(target),dict(value=1))
        self.assertEqual(load(target.with_suffix('.json.writing')),dict(value=2))


if __name__=='__main__':unittest.main()
