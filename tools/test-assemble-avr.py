"""Check the X-pointer encodings used to save Flash in native music kernels."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('assembler',Path(__file__).with_name('assemble-avr.py'))
assembler=importlib.util.module_from_spec(spec);spec.loader.exec_module(assembler)


class PointerEncodingTests(unittest.TestCase):
    def assemble(self,text):
        scratch=Path(__file__).resolve().parents[1]/'build'
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            source=Path(directory)/'test.S';source.write_text(text,encoding='utf-8')
            return assembler.assemble(source)[0]

    def test_standard_x_forms(self):
        # AVR instruction-set encodings, independent of this assembler.
        self.assertEqual(self.assemble('ld r16, X\nld r17, X+\nld r18, -X\nst X, r19\nst X+, r20\nst -X, r21\n'),
            bytes.fromhex('0c911d912e913c934d935e93'))

    def test_modified_pointer_register_operands_are_rejected(self):
        for instruction in ('ld r26, X+','ld r27, -X','st X+, r26','st -X, r27'):
            with self.subTest(instruction=instruction),self.assertRaises(AssertionError):
                self.assemble(instruction+'\n')


if __name__=='__main__':unittest.main()
