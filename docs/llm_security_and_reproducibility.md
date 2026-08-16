# LLM Security And Reproducibility

Security rules:

- Never write the DeepSeek API key to logs, artifacts, or reports.
- Keep `.env` and `*.env.local` out of Git.
- Persist request payloads, prompts, raw responses, and provenance only after secret-safe serialization.

Reproducibility rules:

- Cache keys include case id, mode, trial id, provider, model, prompt hash, specification hash, netlist hash, capability-registry hash, temperature, and max tokens.
- Every LLM artifact directory records request payloads, prompt hashes, parsed plans, validation output, compiled decks, ngspice outputs, metrics, and provenance.
- Deterministic D0 remains untouched and is used as the fair comparison baseline.

Current reproducibility note on 2026-07-21: live DeepSeek bit-for-bit reproducibility is not claimed because the provider is not configured locally and provider-side seed guarantees have not been verified in this workspace.
