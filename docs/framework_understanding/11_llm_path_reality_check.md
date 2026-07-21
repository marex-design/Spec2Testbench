# Phase 11 - LLM Path Reality Check

## What is actually implemented?

| LLM capability | Implemented | Tested in inspected tests | Used in canonical paper campaign | Evidence |
| --- | --- | --- | --- | --- |
| Provider abstraction | Yes | Indirectly | No | `infrastructure/llm/llm_client.py` |
| Multiple providers | Yes | Not directly inspected | No | OpenAI, DeepSeek, Groq, Gemini, Anthropic enums and client init |
| Prompt building for testbench generation | Yes | Not directly inspected | No | `testbench/prompts/testbench_prompts.py` referenced by generator |
| Text-to-spec extraction | Yes | Not directly inspected | No | `TestBenchGenerator.generate_from_text()` |
| LLM testbench generation | Yes | No clear direct unit evidence inspected | No | `_generate_with_llm()` |
| LLM multimodal waveform diagnosis | Yes | yes, repository contains multimodal tests | No | `WaveformChecker`, `diagnose` CLI |
| Automatic repair loop with multiple retries | Not clearly evidenced | No | No | no retry loop observed in inspected files |
| LLM threshold modification | No evidence | No | No | generator pulls thresholds from specification |
| LLM circuit modification | No evidence | No | No | LLM generates testbench/spec interpretation, not circuit mutation |
| Same checker after LLM generation | Yes | indirect | not used canonically | pipeline still routes through `SpecChecker` |

## Answers to requested questions

1. Provider/model usable:
   - OpenAI, DeepSeek, Groq, Gemini, Anthropic.
2. Prompts built:
   - in `testbench/prompts/testbench_prompts.py`.
3. Information sent:
   - spec-derived prompt context from `Specification.to_prompt_context()` and prompt builders.
4. LLM generates:
   - testbench planning payload and natural-language extraction to spec.
5. Response parsing:
   - JSON parsed by `json.loads(...)`.
6. Error repair:
   - not clearly implemented as an automatic retry/repair loop in inspected core files.
7. Number of attempts:
   - no confirmed retry budget observed.
8. Can LLM modify thresholds:
   - not in the inspected runtime path.
9. Can LLM modify evaluated circuit:
   - no evidence found.
10. Do LLM outputs pass through same checker:
   - yes, once a `TestBench` exists the pipeline is the same.
11. Did canonical campaigns use LLM:
   - no; `run_paper_campaign.py` sets `use_llm=False`.
12. Quantitative LLM results existing:
   - not confirmed from canonical campaign outputs inspected here.
13. Paper claims that are only architectural/future:
   - any claim implying canonical campaign dependence on LLM generation would be unsupported by the inspected `run_paper_campaign.py`.

## Architectural reading

Fact observed:
- LLM support exists as an optional adapter path.

Interpretation:
- in the current implementation, LLM is peripheral to the canonical scientific pipeline, not central to the published benchmark campaign.
