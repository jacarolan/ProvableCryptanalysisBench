import unittest
from fractions import Fraction
from pathlib import Path
import tempfile

from run.check import check, parse_axioms, source_policy
from run.evaluate import evaluate


class PolicyTests(unittest.TestCase):
    def test_missing_submission_is_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = check(Path(tmp) / 'missing.lean')
            self.assertEqual(record['status'], 'rejected')
            self.assertIn('FileNotFoundError', record['error'])

    def test_accept_plain_proof_source(self):
        source_policy('import GGM.Certificate\nnamespace Submission\n-- sorry in comments is harmless\ndef x := 1\nend Submission\n')

    def test_reject_bypasses(self):
        for bad in ['sorry', 'admit', 'axiom magic : False', '#eval IO.println "spoof"',
                    'unsafe def x := 1', 'native_decide', 'run_tac pure ()',
                    'set_option debug.skipKernelTC true', '@[implemented_by x]']:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                source_policy('import GGM.Certificate\n' + bad)

    def test_import_shadowing_rejected(self):
        for imports in ['import Mathlib', 'import GGM.Certificate Evil', 'import GGM.Certificate\nimport Evil']:
            with self.assertRaises(ValueError):
                source_policy(imports)

    def test_nested_comments(self):
        source_policy('import GGM.Certificate\n/- outer /- inner -/ sorry -/\ndef x := 1')

    def test_axiom_audit_is_transitive_allowlist(self):
        text = "'Submission.certificate' depends on axioms: [propext, Classical.choice, Quot.sound]"
        self.assertEqual(len(parse_axioms(text)), 3)
        for name in ['sorryAx', 'Submission.cheat', 'Lean.ofReduceBool']:
            with self.assertRaises(ValueError):
                parse_axioms(f"'Submission.certificate' depends on axioms: [{name}]")
        with self.assertRaises(ValueError):
            parse_axioms('compiled without audit')


class BoundTests(unittest.TestCase):
    def test_large_parameter_no_attack_execution(self):
        expr = {'op': 'add', 'a': {'op': 'order'}, 'b': {'op': 'constant', 'value': 1}}
        self.assertEqual(evaluate(expr, (1 << 4096) - 1), 1 << 4096)

    def test_sqrt_and_fraction(self):
        expr = {'op': 'div', 'a': {'op': 'sqrtOrder'}, 'denominator': 3}
        self.assertEqual(evaluate(expr, 101), Fraction(10, 3))
        expr['denominator'] = 0
        self.assertEqual(evaluate(expr, 101), 0)


if __name__ == '__main__':
    unittest.main()
