"""Static workflow contract, including mutations that used to pass phrase checks."""
from pathlib import Path
import re
import unittest

CANON = '.agents/skills/goal-runner/references/laziness-ladder.md'
CONSUMERS = {
    'AGENTS.md': CANON,
    'docs/ENGINEERING_LOOP.md': CANON,
    'README.md': CANON,
    '.codex/agents/harness-goal-worker.toml': CANON,
    '.codex/agents/harness-goal-verifier.toml': CANON,
    '.agents/skills/goal-runner/SKILL.md': 'references/laziness-ladder.md',
}
EVIDENCE = {
    'templates/work-item.md': ('Переиспользование: проверенные пути', 'Для bugfix: первопричина, проверенные потребители'),
    '.agents/skills/goal-runner/references/delegation-contract.md':
        ('Existing implementation search:', 'Bugfix root cause and caller coverage:'),
}
RUNGS = (
    'Do nothing (YAGNI).', 'Existing codebase implementation.',
    'Standard library or language feature.', 'Native platform primitive.',
    'Existing project dependency.', 'One direct expression or line.', 'Minimum working code.',
)


def read_contract(root):
    return {name: (root/name).read_text(encoding='utf-8') for name in (CANON, *CONSUMERS, *EVIDENCE)}


def validate_contract(contents):
    errors = []
    ladder = contents[CANON]
    section = ladder.split('## ', 1)[0]
    headings = re.findall(r'(?m)^(\d+)\. \*\*([^*]+)\*\*', section)
    if headings != [(str(i), title) for i, title in enumerate(RUNGS, 1)]:
        errors.append('canonical rung order/numbering differs')
    for required in ('## Bugfix root cause and callers', 'Verify graph pointers against current source',
                     'coverage gaps', 'regression check', '## Safety floor', '## Two-pass code review'):
        if required not in ladder:
            errors.append('canonical rule missing: ' + required)
    for name, reference in CONSUMERS.items():
        text = contents[name]
        if reference not in text:
            errors.append(name + ': canonical reference missing')
        # Reject the former copied lists, not incidental mentions of YAGNI.
        if re.search(r'YAGNI\s*(?:→|,|;)', text) or re.search(r'\(1\).*YAGNI', text):
            errors.append(name + ': duplicated ladder list')
    for name, fields in EVIDENCE.items():
        for field in fields:
            if field not in contents[name]:
                errors.append(name + ': missing evidence field ' + field)
    return errors


class LazinessLadderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contents = read_contract(Path(__file__).resolve().parents[1])

    def test_current_contract(self):
        self.assertEqual(validate_contract(self.contents), [])

    def test_missing_reuse_rung_rejected(self):
        content = dict(self.contents)
        content[CANON] = '\n'.join(line for line in content[CANON].splitlines() if not line.startswith('2. **'))
        self.assertTrue(validate_contract(content))

    def test_reordered_rungs_rejected_even_when_all_phrases_remain(self):
        content = dict(self.contents)
        content[CANON] = content[CANON].replace(RUNGS[1], '__swap__').replace(RUNGS[2], RUNGS[1]).replace('__swap__', RUNGS[2])
        self.assertTrue(validate_contract(content))

    def test_renumbering_rejected(self):
        content = dict(self.contents)
        content[CANON] = content[CANON].replace('7. **', '8. **')
        self.assertTrue(validate_contract(content))

    def test_each_consumer_requires_canonical_reference(self):
        for name, reference in CONSUMERS.items():
            with self.subTest(name=name):
                content = dict(self.contents)
                content[name] = content[name].replace(reference, 'old-rules.md')
                self.assertTrue(validate_contract(content))

    def test_stale_duplicate_rejected_despite_valid_reference(self):
        content = dict(self.contents)
        content['AGENTS.md'] += '\nYAGNI → stdlib → native platform\n'
        self.assertTrue(validate_contract(content))

    def test_root_cause_rule_and_evidence_fields_required(self):
        mutations = [(CANON, '## Bugfix root cause and callers')]
        mutations += [(name, field) for name, fields in EVIDENCE.items() for field in fields]
        for name, field in mutations:
            with self.subTest(name=name, field=field):
                content = dict(self.contents)
                content[name] = content[name].replace(field, '')
                self.assertTrue(validate_contract(content))


if __name__ == '__main__':
    unittest.main()
