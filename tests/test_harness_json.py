import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import harness_json as hj


class HarnessJsonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.rows = [{'id': i, 'name': 'worker'} for i in range(1000)]
        self.raw = json.dumps(self.rows, indent=2).encode()

    def compress(self, raw=None, **kwargs):
        # Character count is a deterministic test double; integration uses o200k_base.
        return hj.compress_bytes(self.raw if raw is None else raw, self.root, count=len, **kwargs)

    def test_small_and_invalid_inputs_unchanged(self):
        for raw in (b'{"a":1}', b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1e999}', b'not json', b'\xff'):
            with self.subTest(raw=raw):
                self.assertEqual(self.compress(raw)[0], raw)
        self.assertFalse((self.root/'.harness').exists())

    def test_tokenizer_unavailable_passes_original(self):
        with patch.object(hj, 'token_counter', side_effect=ImportError):
            output, meta = hj.compress_bytes(self.raw, self.root)
        self.assertEqual(output, self.raw)
        self.assertEqual(meta['mode'], 'original')

    def test_dependency_failure_uses_verified_compact_json(self):
        def unavailable(_):
            raise ImportError
        output, meta = self.compress(candidate=unavailable)
        self.assertEqual(meta['mode'], 'json')
        self.assertIn(b'Retrieve original bytes:', output)
        self.assertEqual(hj.retrieve(self.root, hj.digest(self.raw)), self.raw)

    def test_exact_table_roundtrip(self):
        table = '[1000]{id:int,name:string}\n' + '\n'.join(f'{i},worker' for i in range(1000))
        output, meta = self.compress(candidate=lambda _: table)
        self.assertEqual(meta['mode'], 'table')
        self.assertEqual(hj.decode_table(table), self.rows)
        self.assertTrue(output.endswith(table.encode()))

    def test_loss_markers_wrong_types_and_rows_rejected(self):
        bad = [
            '[1]{id:int,name:string}\n0,worker',
            '[1000]{id:int,name:string}\n' + '\n'.join(f'{i},<<ccr:abcdef>>' for i in range(1000)),
            '[1000]{id:bool,name:string}\n' + '\n'.join('true,worker' for _ in range(1000)),
            '[1000]{id:int,name:string}\n' + '\n'.join(f'{i+1},worker' for i in range(1000)),
        ]
        for table in bad:
            with self.subTest(table=table[:60]):
                _, meta = self.compress(candidate=lambda _: table)
                self.assertEqual(meta['mode'], 'json')

    def test_nested_and_non_array_inputs_never_go_to_headroom(self):
        def forbidden(_):
            raise AssertionError('not a flat array')
        for value in ({'rows': self.rows}, [{'nested': self.rows}]):
            raw = json.dumps(value, indent=2).encode()
            output, meta = self.compress(raw, candidate=forbidden)
            self.assertEqual(meta['mode'], 'json')
            self.assertNotIn('headroom', meta)

    def test_storage_failure_falls_back(self):
        with patch.object(hj, 'save_original', side_effect=OSError):
            output, meta = self.compress(candidate=lambda _: 'bad')
        self.assertEqual(output, self.raw)
        self.assertEqual(meta['mode'], 'original')

    def test_retrieval_rejects_tamper_and_traversal(self):
        key = hj.save_original(self.root, self.raw)
        self.assertEqual(hj.retrieve(self.root, key), self.raw)
        for bad in ('../secret', 'a'*63, 'A'*64):
            with self.assertRaises(ValueError):
                hj.retrieve(self.root, bad)
        path = self.root/'.harness/runtime/json-originals'/f'{key}.json'
        path.write_bytes(b'corrupt')
        with self.assertRaises(ValueError):
            hj.retrieve(self.root, key)
        self.assertEqual(self.compress(candidate=lambda _: 'bad')[0], self.raw)

    def test_low_savings_returns_original_without_cache(self):
        raw = json.dumps(self.rows, separators=(',', ':')).encode()
        output, meta = self.compress(raw, candidate=lambda _: 'bad')
        self.assertEqual(output, raw)
        self.assertEqual(meta['reason'], 'insufficient_savings')
        self.assertFalse((self.root/'.harness').exists())

    def test_boundary_includes_envelope_cost(self):
        def count(text):
            return 8000 if text == self.raw.decode() else 6801
        output, _ = hj.compress_bytes(self.raw, self.root, count=count, candidate=lambda _: 'bad')
        self.assertEqual(output, self.raw)
        def count_at_limit(text):
            return 8000 if text == self.raw.decode() else 6800
        _, meta = hj.compress_bytes(self.raw, self.root, count=count_at_limit, candidate=lambda _: 'bad')
        self.assertEqual(meta['savedPercent'], 15.0)

    def test_table_strings_escaping_and_numeric_types(self):
        table = '[1]{text:string,count:int,rate:float,flag:bool}\n"hello, ""world""\nnext",9007199254740993,1.0,true'
        expected = [{'text': 'hello, "world"\nnext', 'count': 9007199254740993, 'rate': 1.0, 'flag': True}]
        self.assertEqual(hj.canonical(hj.decode_table(table)), hj.canonical(expected))
        self.assertNotEqual(hj.canonical(1), hj.canonical(True))
        self.assertNotEqual(hj.canonical(1), hj.canonical(1.0))


if __name__ == '__main__':
    unittest.main()
