"""Independent fixed-point, phase, excitation and inverse-analysis contracts."""
import itertools
import hashlib
import json
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
import q4_phase_wave as codec
from q4_voice_patterns import multiply as byte_multiply


class PhaseWaveTests(unittest.TestCase):
    def test_byte_floor_profile_matches_every_legacy_product(self):
        for value,k in itertools.product(range(-128,128),range(-15,16)):
            self.assertEqual(codec.state_multiply(value,k,0,False),byte_multiply(value,k))

    def test_word_products_match_signed_negation_and_both_rounding_rules(self):
        values=[-32768,-32767,-2048,-129,-128,-127,-17,-16,-15,-1,0,1,15,16,17,127,128,2047,32767]
        for value,k,nearest in itertools.product(values,range(-15,16),(False,True)):
            operand=(((-value)+32768)%65536)-32768 if k<0 else value
            product=operand*abs(k)
            expected=(1 if product>=0 else -1)*((abs(product)+8)//16) if nearest else product//16
            expected=((expected+32768)%65536)-32768
            self.assertEqual(codec.state_multiply(value,k,4,nearest),expected)

    def fixture(self):
        p=np.array([1000,2000,0,50000],np.uint16);g=np.array([2,3,1,1],np.uint8)
        d=np.array([64,128,192,256],np.uint16);k=np.zeros((4,8),np.int8)
        m=np.array([0,1,0,1],np.uint8);b=np.zeros((2,32),np.int8)
        b[0]=np.resize(np.array([-7,-3,0,4,7,2],np.int8),32);b[1]=-b[0]
        o=np.array([65000,1234,50000,456],np.uint16);r=np.array([0,1,0,0],np.uint8)
        return p,g,d,k,m,b,o,r

    def test_full_phase_and_noise_excitation_match_scalar_reference_in_all_precisions(self):
        values=self.fixture();p,g,d,k,m,b,o,r=values
        codec.validate(*values);rows,phases=codec.trace(p,d,o,r)
        frame=0;phase=int(o[0]);next_frame=int(d[0])-1;seed=0xa7;expected=[]
        for n in range(int(d.sum())):
            if n==next_frame:
                frame=(frame+1)%len(p);next_frame+=int(d[frame])
                if r[frame]:phase=int(o[frame])
            self.assertEqual(int(rows[n]),frame);self.assertEqual(int(phases[n]),phase)
            if p[frame]:
                index=phase//2048;fraction=(phase//256)%8;mode=int(m[frame])
                a=int(b[mode,index]);c=int(b[mode,(index+1)%32])
                value=(a*8+(c-a)*fraction)*int(g[frame])//8
            else:
                seed=(seed//2)^(0xb8 if seed%2 else 0)
                value=-int(g[frame]) if seed%2 else int(g[frame])
            expected.append(value+128);phase=(phase+int(p[frame]))%65536
        for bits,nearest in itertools.product((0,4,8),(False,True)):
            actual,counts=codec.render(*values,tilt_shift=0,state_bits=bits,nearest=nearest)
            np.testing.assert_array_equal(actual,np.asarray(expected,np.uint8))
            self.assertFalse(np.any(counts))

    def test_inverse_is_the_inverse_of_an_independent_floating_lattice(self):
        values=self.fixture();p,g,d,_,m,b,o,r=values
        k=np.array([[-6,4,-2,6,0,-4,2,-2],[8,-4,4,-2,6,0,-4,2],
            [-8,2,-6,0,4,-2,2,0],[-10,6,0,-2,2,-4,0,2]],np.int8)
        rows,_=codec.trace(p,d,o,r);x=np.sin(np.arange(len(rows))*.17)*.15
        excitation=codec.inverse(x,k,rows);states=np.zeros(8);previous=0.;recovered=[]
        for n,source in enumerate(excitation):
            value=source
            for j in range(7,-1,-1):
                old=states[j];coefficient=float(k[rows[n],j])/16
                value-=coefficient*old
                if j<7:states[j+1]=old+coefficient*value
            states[0]=value;value+=previous*.5;previous=value;recovered.append(value/128)
        np.testing.assert_allclose(recovered,x,rtol=1e-12,atol=1e-12)

    def test_validation_rejects_truncated_and_unstable_models(self):
        values=self.fixture()
        for position,replacement in ((0,np.array([1.])),(3,np.full((4,8),16,np.int8)),
                (5,np.zeros((2,16),np.int8)),(6,np.array([0])),(7,np.array([0,1,2,0]))):
            changed=list(values);changed[position]=replacement
            with self.assertRaises(ValueError):codec.validate(*changed)

    def test_legacy_excitation_and_byte_filter_reproduce_qualified_whole_phrase(self):
        from q4_voice_patterns import render as old_render
        model=json.loads((ROOT/'ATtiny13A/Sound/research/q3-adaptive/half-pitch/model.json').read_text())
        f=np.asarray(model['frames'],np.uint8);d=np.asarray(model['durations'],np.uint16)
        b=np.asarray(model['pulsebook'],np.int8);h=np.asarray(model['fractions'],np.uint8)
        k=np.empty((len(f),8),np.int8)
        k[:,::2]=((f[:,2:]&15).astype(np.int16)-8)*2
        k[:,1::2]=((f[:,2:]>>4).astype(np.int16)-8)*2
        rows,excitation=codec.legacy_excitation(f[:,0],f[:,1]&15,d,f[:,1]>>4,b,h)
        expected,counts=old_render(f[:,0],f[:,1]&15,np.arange(len(f)),d,h,k,f[:,1]>>4,b)
        actual,got=codec.filter_signal(excitation,rows,k)
        np.testing.assert_array_equal(expected,actual);np.testing.assert_array_equal(counts,got)
        self.assertEqual(hashlib.sha256(actual.tobytes()).hexdigest(),
            '6e7460448faded3cb63371b9c4729b4c81ad69c6560eef40cef7973179efa836')


if __name__=='__main__':unittest.main()
