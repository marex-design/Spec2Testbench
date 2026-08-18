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

class LLMGenerationService:
    def __init__(self,provider,validator=None,max_retries:int=1): self.provider=provider; self.validator=validator or LLMTestbenchPlanValidator(); self.max_retries=max_retries
    def generate_plan(self, specification: Specification, netlist_path: Path, deterministic_plan: dict[str,Any]) -> LLMGenerationOutcome:
        history=[]; payload={'case_id':specification.case_id,'specification':specification.canonical_dict(),'deterministic_plan':deterministic_plan}
        raw=self.provider.generate(payload)
        for attempt in range(self.max_retries+1):
            try: plan=TestbenchPlan.model_validate_json(raw) if isinstance(raw,str) else TestbenchPlan.model_validate(raw)
            except Exception as exc:
                if attempt>=self.max_retries: return LLMGenerationOutcome(None,{'status':'INVALID','issues':[{'code':'JSON_SCHEMA_ERROR','message':str(exc)}]},history,raw)
                history.append({'attempt':attempt,'reason':'JSON_SCHEMA_ERROR'}); raw=self.provider.generate({**payload,'repair':history[-1]}); continue
            val=self.validator.validate(plan,specification,netlist_path)
            if val['status']=='VALID': return LLMGenerationOutcome(plan,val,history,raw)
            if attempt>=self.max_retries: return LLMGenerationOutcome(plan,val,history,raw)
            history.append({'attempt':attempt,'reason':'VALIDATOR_REJECTION','issues':val['issues']}); raw=self.provider.generate({**payload,'repair':history[-1]})
        return LLMGenerationOutcome(None,{'status':'INVALID','issues':[{'code':'UNKNOWN'}]},history,raw)
