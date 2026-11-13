"""Fail-closed source pairing and a small native API regression smoke check."""
from pathlib import Path
import contextlib,io,shutil,tempfile,unittest
from verify_compact_error_guard import ACTIVE,REPO,GuardAudit,SMOKE,guard_variants
from verify_compact_error_guard_avr import prepare_private_source


class CompactErrorGuardTests(unittest.TestCase):
    def test_pairing_changes_only_the_compact_guard_and_round_trips(self):
        source=(ACTIVE/'src/Lpx4HybridCore.cpp').read_text(encoding='utf-8')
        with_check,without,present=guard_variants(source)
        self.assertEqual(source,with_check if present else without)
        self.assertEqual(guard_variants(with_check),(with_check,without,True))
        self.assertEqual(guard_variants(without),(with_check,without,False))
        boundary='\n#else\n int16_t decoded=0;'
        start=with_check.index('bool Lpx4HybridCore::decodeCode(int8_t& q){')
        self.assertEqual(with_check[with_check.index(boundary,start):],without[without.index(boundary,start):])
        self.assertEqual(with_check.count(' if(error_)return false;'),without.count(' if(error_)return false;')+1)
        build=REPO/'build';build.mkdir(exist_ok=True)
        before=(ACTIVE/'src/Lpx4HybridCore.cpp').read_bytes()
        with tempfile.TemporaryDirectory(prefix='compact-guard-copy-',dir=build) as folder:
            private_repo,private=prepare_private_source(Path(folder),without)
            self.assertEqual((private/'src/Lpx4HybridCore.cpp').read_text(),without)
            self.assertTrue((private_repo/'Codecs/common/pwm_gain.h').is_file())
            self.assertTrue((private.parent/'validation/attiny88/sim_player.c').is_file())
        self.assertEqual((ACTIVE/'src/Lpx4HybridCore.cpp').read_bytes(),before)

    def test_unreviewed_extra_guard_or_changed_clipping_fails_closed(self):
        source=(ACTIVE/'src/Lpx4HybridCore.cpp').read_text(encoding='utf-8')
        with_check,_,_=guard_variants(source)
        bad=with_check.replace(' if(error_)return false;\n if(decoded < -32)',
             ' if(error_)return false;\n if(error_)return false;\n if(decoded < -32)',1)
        with self.assertRaises(ValueError):guard_variants(bad)
        with self.assertRaises(ValueError):guard_variants(with_check.replace(' if(decoded < -32)decoded=-32;',' if(decoded < -31)decoded=-31;',1))

    @unittest.skipUnless(shutil.which('g++'),'Native C++ compiler unavailable')
    def test_native_api_smoke_includes_malformed_tails_and_source_switches(self):
        build=REPO/'build';build.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='compact-guard-test-',dir=build) as folder:
            with contextlib.redirect_stdout(io.StringIO()):
                report=GuardAudit(Path(folder)).run(SMOKE)
            self.assertTrue(report['all_api_traces_exact'])
            self.assertTrue(report['noncompact_preprocessed_exact'])
            for key in ('valid','malformed_or_mutated','callback_eof','source_switch'):
                self.assertGreater(report['counts'][key],0)
            self.assertGreater(report['counts']['api_rows_compared'],report['counts']['trace_comparisons'])


if __name__=='__main__':unittest.main()
