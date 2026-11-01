"""Scope identity, interval ambiguity and private-source projection contracts."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).parents[2]
spec = importlib.util.spec_from_file_location("inline_mapper", ROOT / "web-player/scripts/map-native-inline-scopes.py")
mapper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mapper)
scopes = mapper.SCOPES


def die(offset, tag, parent, ranges=(), **attrs):
    return {"offset": offset, "tag": "DW_TAG_"+tag, "parent": parent, "ranges": list(ranges), "attributes": attrs}


def tree():
    return {1: die(1, "subprogram", None, [(2, 100)], name="outer", decl_file="web-player/native/outer.c", decl_line=1),
            2: die(2, "inlined_subroutine", 1, [(10, 20), (30, 40)], abstract_origin=10),
            10: die(10, "subprogram", None, name="helper", decl_file="web-player/native/helper.h", decl_line=2)}


class ScopeTests(unittest.TestCase):
    def test_ranges_are_half_open_and_keep_discontiguous_gaps(self):
        index = scopes.ScopeIndex(tree(), [(2, 100)])
        self.assertEqual(list(index.at([2, 10, 19, 20, 30, 40, 100])),
                         [((1,),), ((1, 2),), ((1, 2),), ((1,),), ((1, 2),), ((1,),), ()])
        self.assertEqual(index.stats["discontiguousScopes"], 1)

    def test_incomparable_paths_remain_ambiguous_even_at_different_depths(self):
        nodes = tree()
        nodes[3] = die(3, "inlined_subroutine", 2, [(12, 18)], abstract_origin=10)
        nodes[4] = die(4, "inlined_subroutine", 1, [(11, 19)], abstract_origin=10)
        self.assertEqual(list(scopes.ScopeIndex(nodes, [(2, 100)]).at([13])), [((1, 2, 3), (1, 4))])

    def test_dead_function_descendants_do_not_overlay_live_code(self):
        nodes = tree()
        nodes[1]["dead"] = True
        nodes[3] = die(3, "subprogram", None, [(2, 100)])
        index = scopes.ScopeIndex(nodes, [(2, 100)])
        self.assertEqual(list(index.at([15])), [((3,),)])
        self.assertEqual(index.stats["deadScopes"], 1)

    def test_invalid_hierarchy_and_origin_references_fail(self):
        nodes = tree()
        nodes[2]["ranges"] = [(1, 20)]
        with self.assertRaises(AssertionError):
            scopes.ScopeIndex(nodes, [(2, 100)])
        self.assertEqual(scopes.attribute(tree(), 2, "name"), "helper")
        nodes = tree()
        nodes[10]["attributes"] = {"abstract_origin": 2}
        with self.assertRaises(AssertionError):
            scopes.attribute(nodes, 2, "name")
        with self.assertRaises(AssertionError):
            scopes.attribute({}, 10, "name")

    def test_resolved_dump_ranges_and_null_scopes_are_parsed(self):
        text = '''Compile Unit: version = 0x0004
0x00000001: DW_TAG_compile_unit
0x00000002:   DW_TAG_subprogram
                DW_AT_low_pc (0x00000002)
                DW_AT_high_pc (0x00000064)
                DW_AT_name ("outer")
0x00000003:     DW_TAG_inlined_subroutine
                  DW_AT_abstract_origin (0x00000010 "helper")
                  DW_AT_ranges (0x00000000
                    [0x0000000a, 0x00000014)
                    [0x0000001e, 0x00000028))
0x00000004:     NULL
0x00000010:   DW_TAG_subprogram
                DW_AT_name ("helper")
0x00000011:   NULL
'''
        nodes = scopes.parse_scopes(text)
        self.assertEqual(nodes[3]["parent"], 2)
        self.assertEqual(nodes[3]["ranges"], [(10, 20), (30, 40)])
        self.assertEqual(nodes[16]["parent"], 1)
        self.assertEqual(scopes.attribute(nodes, 3, "name"), "helper")
        for broken in [text.replace("0x0004", "0x0005", 1), text+"0x00000003: DW_TAG_subprogram\n",
                       text.replace("[0x0000000a, 0x00000014)", "[0x00000014, 0x0000000a)")]:
            with self.assertRaises(AssertionError):
                scopes.parse_scopes(broken)

    def test_project_projection_never_copies_foreign_paths_or_symbols(self):
        nodes = tree()
        known = {"web-player/native/outer.c": 10, "web-player/native/helper.h": 3}
        self.assertEqual(mapper.frame(2, nodes, known),
                         {"kind": "project", "function": "helper", "source": "web-player/native/helper.h", "line": 2})
        nodes[10]["attributes"]["decl_file"] = "foreign/location.cc"
        self.assertEqual(mapper.frame(2, nodes, known), {"kind": "support"})
        nodes[10]["attributes"]["decl_file"] = "web-player/native/helper.h"
        nodes[10]["attributes"]["decl_line"] = 99
        self.assertEqual(mapper.frame(2, nodes, known), {"kind": "unresolved"})
        self.assertIsNone(mapper.project_path("web-player/native/../other.c", 1, known))

    def test_scope_boundaries_do_not_carry_a_source_into_another_function(self):
        nodes = {1: die(1, "subprogram", None, [(2, 10)]), 2: die(2, "subprogram", None, [(12, 20)])}
        index = scopes.ScopeIndex(nodes, [(2, 10), (12, 20)])
        mapping = {"version": 3, "sources": ["web-player/native/outer.c"], "names": [],
                   "mappings": ",".join("".join(mapper.LABELS.vlq(v) for v in r) for r in [[2, 0, 0, 0], [12, 0, 1, 0]])}
        tagged, contexts, expected, _ = mapper.scope_map(mapping, index, 0, [(2, 10), (12, 20)])
        rows = mapper.LABELS.decode_map(tagged)
        at = {r["offset"]: r for r in rows}
        self.assertIsNone(at[10]["position"])
        self.assertIsNone(at[12]["position"])
        self.assertEqual(at[14]["position"][2], 1)
        self.assertEqual(mapper.LABELS.check_labels(rows, expected), (2, 2))

    def test_wasm_geometry_requires_matching_function_counts(self):
        header, functions, code = b"\0asm\1\0\0\0", b"\3\2\1\0", b"\x0a\4\1\2\0\x0b"
        self.assertEqual(scopes.code_layout(header+functions+code), (14, [(2, 4)]))
        for invalid in [header+functions+code[:-1], header+functions+functions+code,
                        header+b"\3\3\2\0\0"+code, header+b"\2\1\1"+functions+code]:
            with self.assertRaises(AssertionError):
                scopes.code_layout(invalid)


if __name__ == "__main__":
    unittest.main()
