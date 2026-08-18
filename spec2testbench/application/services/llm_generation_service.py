from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from spec2testbench.domain.entities.specification import Specification
from spec2testbench.domain.entities.testbench_plan import TestbenchPlan
from .llm_testbench_plan_validator import LLMTestbenchPlanValidator

@dataclass
class LLMGenerationOutcome:
    parsed_plan: Optional[TestbenchPlan]
    validation: dict[str,Any]
    repair_history: list[dict[str,Any]]=field(default_factory=list)
    raw_response: Any=None
    provider_metadata: dict[str,Any]=field(default_factory=dict)

class LLMGenerationService:
    def __init__(self,provider,validator=None,max_retries:int=1):
        self.provider=provider
        self.validator=validator or LLMTestbenchPlanValidator()
        self.max_retries=max_retries

    def _metadata(self) -> dict[str,Any]:
        return dict(getattr(self.provider,'last_call_metadata',{}) or {})

    def _stamp_framework_provenance(self, plan: TestbenchPlan) -> TestbenchPlan:
        stamped=plan.model_copy(deep=True)
        stamped.provider_mode=str(getattr(self.provider,'mode','UNKNOWN'))
        stamped.scientific_llm_evidence=bool(getattr(self.provider,'scientific_llm_evidence',False))
        return stamped

    def generate_plan(self, specification: Specification, netlist_path: Path, deterministic_plan: dict[str,Any]) -> LLMGenerationOutcome:
        history=[]
        payload={'case_id':specification.case_id,'specification':specification.canonical_dict(),'deterministic_plan':deterministic_plan}
        raw=self.provider.generate(payload)
        for attempt in range(self.max_retries+1):
            try:
                plan=TestbenchPlan.model_validate_json(raw) if isinstance(raw,str) else TestbenchPlan.model_validate(raw)
                plan=self._stamp_framework_provenance(plan)
            except Exception as exc:
                if attempt>=self.max_retries:
                    return LLMGenerationOutcome(None,{'status':'INVALID','issues':[{'code':'JSON_SCHEMA_ERROR','message':str(exc)}]},history,raw,self._metadata())
                history.append({'attempt':attempt,'reason':'JSON_SCHEMA_ERROR'})
                raw=self.provider.generate({**payload,'repair':history[-1]})
                continue
            val=self.validator.validate(plan,specification,netlist_path)
            if val['status']=='VALID':
                return LLMGenerationOutcome(plan,val,history,raw,self._metadata())
            if attempt>=self.max_retries:
                return LLMGenerationOutcome(plan,val,history,raw,self._metadata())
            history.append({'attempt':attempt,'reason':'VALIDATOR_REJECTION','issues':val['issues']})
            raw=self.provider.generate({**payload,'repair':history[-1]})
        return LLMGenerationOutcome(None,{'status':'INVALID','issues':[{'code':'UNKNOWN'}]},history,raw,self._metadata())
