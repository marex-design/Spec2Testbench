# LLM Current Limitations

The LLM path is an exploratory extension, not primary evidence for the paper.

Supported providers in the code are OpenAI, DeepSeek, Groq, Gemini, and
Anthropic through `spec2testbench/infrastructure/llm/llm_client.py`.

Prompts used for testbench generation are built by
`spec2testbench/infrastructure/testbench/prompts/testbench_prompts.py` and
consumed by `TestBenchGenerator._generate_with_llm`.

Observed limitations from archived pre-consolidation artifacts include:

- multiple LLM rows marked `SKIPPED`;
- failures such as `No testbench generated for ...`;
- no stable paper-eligible LLM campaign;
- no token, cost, or retry accounting suitable for publication;
- limited validation beyond JSON parsing and normalization;
- no deterministic fallback that proves LLM output correctness.

Before defending an LLM claim, the project needs a separate protocol covering
model selection, prompts, retries, parsing failures, cost, token counts,
deterministic validation, and comparison against the non-LLM baseline.
