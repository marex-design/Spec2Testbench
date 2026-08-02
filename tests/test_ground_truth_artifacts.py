from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'experiments' / 'ground_truth' / 'ground_truth_manifest.yaml'

def test_ground_truth_manifest_integrity():
    data = yaml.safe_load(MANIFEST.read_text(encoding='utf-8'))
    cases = data['cases']
    ids = [case['case_id'] for case in cases]
    assert len(ids) == len(set(ids))
    assert data['framework_result_not_used_for_labels'] is True
    eligible = [case for case in cases if case['ground_truth_label'] != 'GROUND_TRUTH_UNCERTAIN']
    assert len({case['parent_circuit_id'] for case in eligible}) >= 10
    for case in cases:
        assert case.get('ground_truth_label')
        assert case.get('justification')
        assert 'framework' not in str(case.get('independent_reference', {}).get('method', '')).lower()
        if case['ground_truth_label'] == 'GROUND_TRUTH_NONCOMPLIANT':
            assert case.get('targeted_metric', {}).get('name')
        if case['ground_truth_label'] != 'GROUND_TRUTH_UNCERTAIN':
            assert case.get('targeted_metric', {}).get('unit') is not None
            parent = ROOT / 'benchmark' / 'analogcoder_pro' / f"{case['parent_circuit_id']}.cir"
            assert parent.exists()

def test_controlled_variants_manifest_is_well_formed():
    manifest = yaml.safe_load((ROOT / 'experiments' / 'controlled_violations' / 'manifest.yaml').read_text(encoding='utf-8'))
    cases = manifest['cases']
    assert 20 <= len(cases) <= 50
    assert len({case['parent_circuit_id'] for case in cases}) >= 10
    for case in cases:
        parent = ROOT / 'benchmark' / 'analogcoder_pro' / f"{case['parent_circuit_id']}.cir"
        generated_dir = str(case.get('generated_dir', ''))
        mutated_netlist = str(case.get('mutated_netlist', ''))
        specification = str(case.get('specification', ''))
        assert parent.exists()
        assert generated_dir.replace('\\', '/').startswith('experiments/controlled_violations/generated_cases/')
        assert mutated_netlist.replace('\\', '/').startswith('experiments/controlled_violations/generated_cases/')
        assert mutated_netlist.endswith('mutated_netlist.cir')
        assert specification.endswith('specification.yaml')
