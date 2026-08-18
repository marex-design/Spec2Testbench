from __future__ import annotations
from pathlib import Path
from typing import Any
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.domain.entities.testbench_plan import TestbenchPlan
from spec2testbench.infrastructure.simulator.netlist_parser import NetlistParser
from .llm_metric_registry import get_metric_definition

class LLMTestbenchPlanValidator:
    def validate(self, plan: TestbenchPlan, specification: Specification, netlist_path: Path) -> dict[str,Any]:
        issues=[]; parsed=NetlistParser().parse(Path(netlist_path)); whitelist={n.lower() for n in parsed.nodes}|{'0'}
        expected=specification.case_id or specification.name
        if plan.case_id != expected: issues.append({'code':'CASE_ID_MISMATCH','message':f'{plan.case_id} != {expected}'})
        allowed_metrics=set(specification.verification_metric_names())
        for m in plan.measurements:
            if m.metric_name not in allowed_metrics: issues.append({'code':'METRIC_NOT_REQUESTED','metric':m.metric_name})
            definition=get_metric_definition(m.metric_name)
            if definition and m.analysis_type not in definition.compatible_analysis_types: issues.append({'code':'METRIC_ANALYSIS_MISMATCH','metric':m.metric_name})
            for node in (m.input_node,m.output_node):
                if node and node.lower() not in whitelist: issues.append({'code':'UNKNOWN_NODE','node':node})
        for s in plan.stimuli:
            if s.target_node.lower() not in whitelist: issues.append({'code':'UNKNOWN_NODE','node':s.target_node})
        for n in plan.observed_nodes:
            if n.lower() not in whitelist: issues.append({'code':'UNKNOWN_NODE','node':n})
        return {'status':'VALID' if not issues else 'INVALID','issues':issues,'expected_case_id':expected,'specification_sha256':specification.sha256()}
