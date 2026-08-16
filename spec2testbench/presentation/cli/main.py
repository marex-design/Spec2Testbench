"""
Command Line Interface for Spec2Testbench.
"""

from pathlib import Path
from typing import Optional
import json

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from ...application.usecases.run_verification import VerificationPipeline
from ...config.settings import settings
from ...infrastructure.llm.llm_client import LLMClient
from ...presentation.formatters.report_formatter import ReportFormatter


app = typer.Typer(
    name="spec2testbench",
    help="Specs to SPICE Testbenches",
    add_completion=False,
)
console = Console()
VALID_PROVIDERS = ["openai", "deepseek", "groq", "gemini", "anthropic"]


def _safe_console_print(message: str, style: Optional[str] = None) -> None:
    try:
        if style:
            console.print(message, style=style)
        else:
            console.print(message)
    except UnicodeEncodeError:
        sanitized = message.encode("ascii", errors="replace").decode("ascii")
        if style:
            console.print(sanitized, style=style)
        else:
            console.print(sanitized)


def _set_provider(provider: Optional[str]) -> None:
    if not provider:
        return
    if provider not in VALID_PROVIDERS:
        console.print(f"[red]Invalid provider: {provider}[/red]")
        console.print(f"   Valid providers: {', '.join(VALID_PROVIDERS)}")
        raise typer.Exit(1)
    settings.llm.default_provider = provider
    console.print(f"[dim]Using LLM provider: {provider}[/dim]")


def _build_llm_client(temperature: float = 0.5):
    api_key = settings.llm.get_api_key()
    model = settings.llm.get_model(vision=False)
    return LLMClient(
        provider=settings.llm.default_provider,
        api_key=api_key,
        model=model,
        temperature=temperature,
    )


@app.command()
def verify(
    specs: Path = typer.Option(..., "--specs", "-s", help="Path to specifications YAML file"),
    netlist: Optional[Path] = typer.Option(None, "--netlist", "-n", help="Path to SPICE netlist"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output directory"),
    format: str = typer.Option("markdown", "--format", "-f", help="Output format: markdown, json, console"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="LLM provider"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Disable LLM (use templates only)"),
    planner_llm: bool = typer.Option(False, "--planner-llm", help="Use the LLM-guided planner for netlist-aware testbench planning"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Verify a circuit against specifications."""
    _safe_console_print("\nSpec2Testbench - Verification\n", style="bold cyan")

    if not specs.exists():
        console.print(f"[red]Specifications file not found: {specs}[/red]")
        raise typer.Exit(1)

    if netlist and not netlist.exists():
        console.print(f"[yellow]Netlist file not found: {netlist}[/yellow]")
        console.print("   Simulation will use mock results")

    if output:
        settings.output.output_dir = output
        settings.output.waveform_dir = output / "waveforms"
        settings.output.report_dir = output / "reports"

    _set_provider(provider)

    use_llm = not no_llm and settings.llm.is_configured
    if not no_llm and not settings.llm.is_configured:
        console.print("[yellow]No LLM API keys configured. Using template-based generation.[/yellow]")
        console.print("   To enable LLM, set the appropriate API key in .env file:")
        console.print("   - OpenAI: OPENAI_API_KEY")
        console.print("   - DeepSeek: DEEPSEEK_API_KEY")
        console.print("   - Groq: GROQ_API_KEY")
        console.print("   - Gemini: GOOGLE_API_KEY")
        console.print("   - Anthropic: ANTHROPIC_API_KEY")
        console.print("")

    llm_client = None
    if use_llm or planner_llm:
        if not settings.llm.is_configured:
            console.print("[red]Planner LLM requested but no API key is configured.[/red]")
            console.print("   Configure one provider key first, then rerun with --planner-llm.")
            raise typer.Exit(1)
    if use_llm:
        try:
            llm_client = _build_llm_client()
            console.print(f"[green]LLM client initialized: {settings.llm.default_provider}[/green]")
        except Exception as exc:
            console.print(f"[yellow]Failed to initialize LLM client: {exc}[/yellow]")
            console.print("   Falling back to template-based generation\n")
            use_llm = False

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Running verification...", total=None)
            pipeline = VerificationPipeline(use_llm=use_llm, llm_client=llm_client, use_llm_planner=planner_llm)
            report = pipeline.verify_from_yaml(specs, netlist)
            progress.remove_task(task)
    except Exception as exc:
        _safe_console_print(f"\nVerification failed: {exc}\n", style="red")
        raise typer.Exit(1)

    formatter = ReportFormatter(output_dir=settings.output.report_dir)
    if format == "markdown":
        formatter.to_markdown(report, save=True)
        _safe_console_print("\nMarkdown report generated\n", style="green")
    elif format == "json":
        formatter.to_json(report, save=True)
        _safe_console_print("\nJSON report generated\n", style="green")
    else:
        _safe_console_print(formatter.to_console(report))

    if report.overall_verdict.value in {"FAIL", "RUN"}:
        raise typer.Exit(1)
    raise typer.Exit(0)


@app.command("hybrid-verify")
def hybrid_verify(
    specs: Path = typer.Option(..., "--specs", "-s", help="Path to specifications YAML file"),
    netlist: Path = typer.Option(..., "--netlist", "-n", help="Path to immutable DUT netlist"),
    output: Path = typer.Option(Path("output/hybrid_verify"), "--output", "-o", help="Evidence output directory"),
    provider: str = typer.Option("deepseek", "--provider", help="Modern planner provider: deepseek or stub"),
    model: Optional[str] = typer.Option(None, "--model", help="Exact model identifier"),
    temperature: float = typer.Option(0.1, "--temperature"),
    top_p: float = typer.Option(1.0, "--top-p", min=0.0, max=1.0),
    max_tokens: int = typer.Option(4096, "--max-tokens"),
    timeout: float = typer.Option(90.0, "--timeout"),
    max_retries: int = typer.Option(3, "--max-retries", min=0, max=10),
):
    """Run the controlled LLM -> validator -> SPICE -> feedback loop."""
    import os

    from ...application.services.hybrid_feedback_loop import HybridFeedbackLoop, RetryPolicy
    from ...application.services.llm_generation_service import LLMGenerationService
    from ...application.ports.llm_provider import LLMProviderError
    from ...domain.entities.specification import Specification
    from ...infrastructure.llm.deepseek_provider import DeepSeekProvider, DeepSeekProviderConfig
    from ...infrastructure.llm.stub_provider import DeterministicStubProvider

    if not specs.exists():
        console.print(f"[red]Specifications file not found: {specs}[/red]")
        raise typer.Exit(1)
    if not netlist.exists():
        console.print(f"[red]DUT netlist not found: {netlist}[/red]")
        raise typer.Exit(1)

    provider_key = provider.strip().lower()
    if provider_key == "stub":
        llm_provider = DeterministicStubProvider()
        resolved_model = model or "deepseek-stub-v1"
        provider_mode = "STUB"
        scientific_evidence = False
    elif provider_key == "deepseek":
        resolved_model = model or os.getenv("DEEPSEEK_MODEL", "").strip()
        if not resolved_model:
            console.print("[red]Set --model or DEEPSEEK_MODEL for a live DeepSeek run.[/red]")
            raise typer.Exit(1)
        config = DeepSeekProviderConfig(
            api_key=os.getenv("DEEPSEEK_API_KEY", "").strip(),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip() or "https://api.deepseek.com",
            model=resolved_model,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            timeout_seconds=timeout,
            max_retries=int(os.getenv("DEEPSEEK_MAX_RETRIES", "3")),
        )
        llm_provider = DeepSeekProvider(config)
        provider_mode = "LIVE"
        scientific_evidence = True
    else:
        console.print("[red]hybrid-verify currently supports --provider deepseek or stub.[/red]")
        raise typer.Exit(1)

    output.mkdir(parents=True, exist_ok=True)
    specification = Specification.from_yaml(specs)
    if not specification.case_id:
        specification.case_id = specs.stem

    loop = HybridFeedbackLoop(
        LLMGenerationService(llm_provider),
        retry_policy=RetryPolicy(max_retries=max_retries),
    )
    try:
        result = loop.run(
            specification=specification,
            netlist_path=netlist,
            model=resolved_model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_seconds=timeout,
            top_p=top_p,
            include_deterministic_summary=True,
            provider_mode=provider_mode,
            scientific_llm_evidence=scientific_evidence,
            spec_path=specs,
        )
    except Exception as exc:
        error_evidence = {
            "final_status": "PROVIDER_ERROR" if isinstance(exc, LLMProviderError) else "FRAMEWORK_ERROR",
            "error_type": type(exc).__name__,
            "message": str(exc),
            "configured_provider": provider_key,
            "configured_model": resolved_model,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "timeout_seconds": timeout,
            "max_retries": max_retries,
            "provider_attempts": getattr(exc, "attempts", []),
        }
        (output / "hybrid_error_evidence.json").write_text(
            json.dumps(error_evidence, indent=2), encoding="utf-8"
        )
        console.print(f"[red]Hybrid verification failed: {exc}[/red]")
        console.print(f"[yellow]Error evidence: {output / 'hybrid_error_evidence.json'}[/yellow]")
        raise typer.Exit(1)

    evidence = result.to_dict()
    evidence.update({
        "configured_provider": provider_key,
        "configured_model": resolved_model,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
        "timeout_seconds": timeout,
        "max_retries": max_retries,
        "provider_transport_max_retries": int(os.getenv("DEEPSEEK_MAX_RETRIES", "3")) if provider_key == "deepseek" else 0,
        "scientific_llm_evidence": scientific_evidence,
    })
    (output / "hybrid_evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    (output / "request_payload.json").write_text(json.dumps(result.planning_outcome.request_payload, indent=2), encoding="utf-8")
    (output / "system_prompt.txt").write_text(result.planning_outcome.system_prompt, encoding="utf-8")
    (output / "raw_response.txt").write_text(result.planning_outcome.raw_response, encoding="utf-8")
    (output / "plan_validation.json").write_text(json.dumps(result.planning_outcome.validation.to_dict(), indent=2), encoding="utf-8")
    (output / "provider_call_history.json").write_text(json.dumps(result.planning_outcome.call_history, indent=2), encoding="utf-8")

    if result.report is not None:
        ReportFormatter(output_dir=output).to_json(result.report, save=True)

    console.print(f"[bold]Final status:[/bold] {result.final_status.value}")
    console.print(f"Repairs: {result.repair_count}/{max_retries}; LLM calls: {result.llm_call_count}")
    console.print(f"Invariants: {'OK' if result.invariants_ok else 'FAILED'}")
    console.print(f"Evidence: {output / 'hybrid_evidence.json'}")
    raise typer.Exit(0 if result.final_status.value == "SUCCESS" else 1)


@app.command()
def generate(
    specs: Path = typer.Option(..., "--specs", "-s", help="Path to specifications YAML file"),
    netlist: Optional[Path] = typer.Option(None, "--netlist", "-n", help="Path to SPICE netlist for netlist-aware planning"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output testbench path"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="LLM provider"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Disable LLM (use templates only)"),
    planner_llm: bool = typer.Option(False, "--planner-llm", help="Use the LLM-guided planner for netlist-aware testbench planning"),
):
    """Generate testbench from specifications."""
    console.print("\n[bold cyan]Spec2Testbench - TestBench Generation[/bold cyan]\n")

    if not specs.exists():
        console.print(f"[red]Specifications file not found: {specs}[/red]")
        raise typer.Exit(1)

    _set_provider(provider)
    use_llm = not no_llm and settings.llm.is_configured

    if not no_llm and not settings.llm.is_configured:
        console.print("[yellow]No LLM API keys configured. Using template-based generation.[/yellow]")
        console.print("   To enable LLM, set the appropriate API key in .env file\n")

    llm_client = None
    if use_llm or planner_llm:
        if not settings.llm.is_configured:
            console.print("[red]Planner LLM requested but no API key is configured.[/red]")
            console.print("   Configure one provider key first, then rerun with --planner-llm.")
            raise typer.Exit(1)
    if use_llm:
        try:
            llm_client = _build_llm_client()
        except Exception as exc:
            console.print(f"[yellow]Failed to initialize LLM client: {exc}[/yellow]")
            console.print("   Falling back to template-based generation\n")
            use_llm = False

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Generating testbench...", total=None)
        from ...domain.entities.specification import Specification

        specification = Specification.from_yaml(specs)
        pipeline = VerificationPipeline(use_llm=use_llm, llm_client=llm_client, use_llm_planner=planner_llm)
        testbench = pipeline.testbench_gen.generate(specification, netlist_path=netlist)
        progress.remove_task(task)

    if output:
        output.write_text(testbench.generate_pyspice_code(), encoding="utf-8")
        console.print(f"\n[green]Testbench saved to {output}[/green]")
    else:
        console.print("\n[green]Testbench generated:[/green]")
        console.print(f"   Name: {testbench.name}")
        console.print(f"   Category: {testbench.category}")
        console.print(f"   Measurements: {len(testbench.measurements)}")
        console.print(f"   Analyses: {len(testbench.analyses)}")
        console.print(f"   Stimuli: {len(testbench.stimuli)}")

    console.print("\n[dim]Tip: Use 'spec2testbench verify' to run simulation and checks[/dim]")


@app.command()
def plan(
    specs: Path = typer.Option(..., "--specs", "-s", help="Path to specifications YAML file"),
    netlist: Path = typer.Option(..., "--netlist", "-n", help="Path to SPICE netlist"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output JSON plan path"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="LLM provider"),
    planner_llm: bool = typer.Option(False, "--planner-llm", help="Use the LLM-guided planner instead of deterministic planning"),
):
    """Display or export the intermediate testbench plan JSON."""
    console.print("\n[bold cyan]Spec2Testbench - Plan[/bold cyan]\n")

    if not specs.exists():
        console.print(f"[red]Specifications file not found: {specs}[/red]")
        raise typer.Exit(1)
    if not netlist.exists():
        console.print(f"[red]Netlist file not found: {netlist}[/red]")
        raise typer.Exit(1)

    _set_provider(provider)
    llm_client = None
    if planner_llm:
        if not settings.llm.is_configured:
            console.print("[red]Planner LLM requested but no API key is configured.[/red]")
            console.print("   Configure one provider key first, then rerun with --planner-llm.")
            raise typer.Exit(1)
        try:
            llm_client = _build_llm_client()
            console.print(f"[green]Planner LLM initialized: {settings.llm.default_provider}[/green]")
        except Exception as exc:
            console.print(f"[red]Failed to initialize planner LLM: {exc}[/red]")
            raise typer.Exit(1)

    from ...domain.entities.specification import Specification

    specification = Specification.from_yaml(specs)
    pipeline = VerificationPipeline(use_llm=False, llm_client=llm_client, use_llm_planner=planner_llm)
    testbench = pipeline.testbench_gen.generate(specification, netlist_path=netlist)
    plan_payload = testbench.metadata.get("llm_guided_plan", {})
    rendered = json.dumps(plan_payload, indent=2)

    if output:
        output.write_text(rendered, encoding="utf-8")
        console.print(f"[green]Plan saved to {output}[/green]")
    else:
        console.print(rendered)


@app.command()
def diagnose(
    waveform: Path = typer.Option(..., "--waveform", "-w", help="Path to waveform image (PNG)"),
    specs: Optional[Path] = typer.Option(None, "--specs", "-s", help="Path to specifications YAML file"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="LLM provider"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output report path"),
):
    """Diagnose a circuit failure from waveform image."""
    console.print("\n[bold cyan]Spec2Testbench - Waveform Diagnosis[/bold cyan]\n")

    if not waveform.exists():
        console.print(f"[red]Waveform file not found: {waveform}[/red]")
        raise typer.Exit(1)

    _set_provider(provider)

    if not settings.llm.is_configured:
        console.print("[red]No LLM API keys configured for multimodal analysis[/red]")
        console.print("   Please set the appropriate API key in .env file:")
        console.print("   - DeepSeek: DEEPSEEK_API_KEY")
        console.print("   - Groq: GROQ_API_KEY")
        console.print("   - OpenAI: OPENAI_API_KEY")
        console.print("   - Gemini: GOOGLE_API_KEY")
        raise typer.Exit(1)

    specification = None
    if specs and specs.exists():
        from ...domain.entities.specification import Specification

        specification = Specification.from_yaml(specs)
        console.print(f"[green]Specifications loaded from {specs}[/green]")

    try:
        api_key = settings.llm.get_api_key()
        model = settings.llm.get_model(vision=True)
        llm_client = LLMClient(
            provider=settings.llm.default_provider,
            api_key=api_key,
            model=model,
            temperature=0.5,
        )
        console.print(f"[green]Multimodal LLM client initialized: {settings.llm.default_provider}[/green]")
    except Exception as exc:
        console.print(f"[red]Failed to initialize LLM client: {exc}[/red]")
        raise typer.Exit(1)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Analyzing waveform...", total=None)
        from ...infrastructure.waveform_checker import WaveformChecker

        checker = WaveformChecker(llm_client=llm_client, use_llm=True)
        if specification:
            failed_metrics = list(specification.performance_targets.keys())
            result = checker.diagnose_failure(waveform, specification, failed_metrics)
        else:
            result = checker.check_specification(
                waveform,
                metric_name="unknown",
                expected_min=0,
                expected_max=float("inf"),
                unit="",
            )
        progress.remove_task(task)

    console.print("\n[bold cyan]Diagnosis Results[/bold cyan]\n")
    console.print(f"  Verdict: {result.verdict.value}")
    console.print(f"  Confidence: {result.confidence:.1%}")
    console.print(f"  Waveform Type: {result.waveform_type.value}")
    console.print("")

    if result.anomalies:
        console.print("[yellow]Anomalies detected:[/yellow]")
        for anomaly in result.anomalies:
            console.print(f"  - {anomaly}")
        console.print("")

    console.print("[bold]Diagnosis:[/bold]")
    console.print(f"  {result.diagnosis}")
    console.print("")

    if result.recommendations:
        console.print("[bold green]Recommendations:[/bold green]")
        for rec in result.recommendations:
            console.print(f"  - {rec}")

    if output:
        output.write_text(result.to_markdown(), encoding="utf-8")
        console.print(f"\n[green]Diagnosis report saved to {output}[/green]")


@app.command()
def draw(
    netlist: Path = typer.Option(..., "--netlist", "-n", help="Path to SPICE netlist file"),
    output: Path = typer.Option(Path("schematic.svg"), "--output", "-o", help="Output path stem or SVG/PDF/PNG path"),
    report: Optional[Path] = typer.Option(None, "--report", help="Connectivity evidence JSON path"),
    diagnostic: bool = typer.Option(False, "--diagnostic", help="Use the legacy annotated component view"),
    view: str = typer.Option("manuscript", "--view", help="Rendering profile: manuscript or appendix"),
):
    """Draw a connectivity-validated schematic from a SPICE netlist."""
    from ...infrastructure.schematic import PublicationSchematicGenerator, netlist_to_schematic

    console.print("\n[bold cyan]Spec2Testbench - Schematic Drawing[/bold cyan]\n")

    if not netlist.exists():
        console.print(f"[red]Netlist file not found: {netlist}[/red]")
        raise typer.Exit(code=1)

    try:
        netlist_text = netlist.read_text(encoding="utf-8")
    except Exception as exc:
        console.print(f"[red]Cannot read netlist: {exc}[/red]")
        raise typer.Exit(code=1)

    try:
        if diagnostic:
            result = netlist_to_schematic(netlist_text, str(output))
            console.print(f"[green]Diagnostic component view saved to {result}[/green]")
            return

        result = PublicationSchematicGenerator(view=view).generate_from_path(
            netlist,
            output,
            report_path=report,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[red]Drawing failed: {exc}[/red]")
        raise typer.Exit(code=1)

    verdict_color = "green" if result.validation.status == "VALID" else "red"
    console.print(f"[{verdict_color}]Structural connectivity: {result.validation.status}[/{verdict_color}]")
    console.print(f"[green]SVG saved to {result.svg_path}[/green]")
    console.print(f"[green]PDF saved to {result.pdf_path}[/green]")
    console.print(f"[green]PNG preview saved to {result.png_path}[/green]")
    console.print(f"[green]Evidence report saved to {result.report_path}[/green]")
    if result.validation.status != "VALID":
        raise typer.Exit(code=2)


@app.command("spec-lint")
def spec_lint(
    specs: Path = typer.Option(..., "--specs", "-s", help="ACP v2 YAML file or directory"),
):
    """Strictly validate uniform v2 specification YAML files."""
    from ...domain.specification_schema_v2 import load_acp_yaml_v2

    if not specs.exists():
        console.print(f"[red]Path not found: {specs}[/red]")
        raise typer.Exit(1)
    files = [specs] if specs.is_file() else sorted(specs.glob("*.yaml"))
    if not files:
        console.print("[red]No YAML files found.[/red]")
        raise typer.Exit(1)
    failures = []
    coverage = []
    for path in files:
        try:
            model = load_acp_yaml_v2(path)
            coverage.append(model.contract_implementation_coverage)
            console.print(
                f"[green]PASS[/green] {path}  contract-implementation="
                f"{model.contract_implementation_coverage:.1%}"
            )
        except Exception as exc:
            failures.append((path, str(exc)))
            console.print(f"[red]FAIL[/red] {path}: {exc}")
    console.print(
        f"\nValidated {len(files)-len(failures)}/{len(files)} YAML files; "
        f"mean mandatory-contract implementation coverage="
        f"{(sum(coverage)/len(coverage) if coverage else 0.0):.1%}."
    )
    if failures:
        raise typer.Exit(1)


@app.command("acp-benchmark")
def acp_benchmark(
    manifest: Path = typer.Option(
        Path("benchmark/analogcoder_pro/acp28_manifest.yaml"),
        "--manifest", "-m", help="ACP benchmark manifest",
    ),
    output: Path = typer.Option(Path("results/acp28_compliance"), "--output", "-o"),
    limit: Optional[int] = typer.Option(None, "--limit", min=1, help="Run only the first N cases"),
    timeout: int = typer.Option(120, "--timeout", min=1, help="ngspice timeout per DUT in seconds"),
    keep_artifacts: bool = typer.Option(True, "--keep-artifacts/--no-keep-artifacts"),
):
    """Measure deterministic compliance of preserved AnalogCoder-Pro ACP-28 DUTs."""
    from ...application.services.acp_benchmark_runner import ACPBenchmarkRunner

    root = Path.cwd()
    resolved_manifest = manifest if manifest.is_absolute() else root / manifest
    if not resolved_manifest.exists():
        console.print(f"[red]Manifest not found: {resolved_manifest}[/red]")
        raise typer.Exit(1)
    console.print("\n[bold cyan]Spec2Testbench - ACP-28 deterministic compliance[/bold cyan]\n")
    try:
        summary = ACPBenchmarkRunner(root).run(
            manifest,
            output,
            limit=limit,
            timeout_seconds=timeout,
            persist_artifacts=keep_artifacts,
            strict_contract=True,
        )
    except Exception as exc:
        console.print(f"[red]ACP benchmark failed: {exc}[/red]")
        raise typer.Exit(1)

    table = Table(show_header=True, header_style="bold")
    table.add_column("Measure")
    table.add_column("Value", justify="right")
    table.add_row("Circuits", str(summary["circuits_total"]))
    table.add_row("Simulation SUCCESS", str(summary["simulation_success"]))
    table.add_row("COMPLIANT", str(summary["compliant"]))
    table.add_row("NONCOMPLIANT", str(summary["noncompliant"]))
    table.add_row("NOT_EVALUATED", str(summary["not_evaluated"]))
    table.add_row("Evaluation rate", f"{100*summary['evaluation_rate']:.2f}%")
    table.add_row("Compliance / evaluated", f"{100*summary['compliance_rate_evaluated']:.2f}%")
    table.add_row("Verified Compliance Yield", f"{100*summary['verified_compliance_yield']:.2f}%")
    table.add_row("Cov_circuits", f"{100*summary['Cov_circuits']:.2f}%")
    table.add_row("Cov_metrics", f"{100*summary['Cov_metrics']:.2f}%")
    table.add_row("Cov_analyses", f"{100*summary['Cov_analyses']:.2f}%")
    console.print(table)
    console.print(f"\n[green]Results written to {Path(output).resolve()}[/green]")



@app.command()
def version():
    """Display version information."""
    console.print("[bold cyan]Spec2Testbench v0.5.0[/bold cyan]")
    console.print("From Specs to SPICE Testbenches: LLM-Assisted Analog Verification")
    console.print("\n[dim]License: MIT[/dim]")
    console.print("\n[dim]Supported LLM Providers: OpenAI, DeepSeek, Groq, Gemini, Anthropic[/dim]")


@app.command()
def config():
    """Display current configuration."""
    console.print("\n[bold cyan]Configuration[/bold cyan]\n")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("LLM Enabled", "yes" if settings.use_llm else "no")
    table.add_row("LLM Provider", settings.llm.default_provider)
    table.add_row("")
    table.add_row("[bold]API Keys:[/bold]", "")
    table.add_row("  OpenAI", "yes" if settings.llm.openai_api_key else "no")
    table.add_row("  DeepSeek", "yes" if settings.llm.deepseek_api_key else "no")
    table.add_row("  Groq", "yes" if settings.llm.groq_api_key else "no")
    table.add_row("  Gemini", "yes" if settings.llm.google_api_key else "no")
    table.add_row("  Anthropic", "yes" if settings.llm.anthropic_api_key else "no")
    table.add_row("")
    table.add_row("Simulator", settings.simulator.simulator_type)
    table.add_row("Warning Margin", f"{settings.warning_margin*100:.0f}%")
    table.add_row("Output Directory", str(settings.output.output_dir))

    console.print(table)
    console.print("\n[dim]Recommendation: Use DeepSeek for cost-effective testing[/dim]")
    console.print("[dim]   Set LLM_PROVIDER=deepseek and DEEPSEEK_API_KEY=your_key[/dim]")


@app.command()
def providers():
    """List available LLM providers and their status."""
    console.print("\n[bold cyan]Available LLM Providers[/bold cyan]\n")

    providers_table = Table(show_header=True, header_style="bold")
    providers_table.add_column("Provider", style="cyan")
    providers_table.add_column("Status", style="white")
    providers_table.add_column("Model (Text)", style="dim")
    providers_table.add_column("Model (Vision)", style="dim")
    providers_table.add_column("Cost", style="dim")

    provider_info = [
        ("deepseek", "yes" if settings.llm.deepseek_api_key else "no", "deepseek-chat", "deepseek-vl", ""),
        ("groq", "yes" if settings.llm.groq_api_key else "no", settings.llm.groq_model, settings.llm.groq_model, ""),
        ("openai", "yes" if settings.llm.openai_api_key else "no", "gpt-4-turbo", "gpt-4-turbo", ""),
        ("gemini", "yes" if settings.llm.google_api_key else "no", "gemini-1.5-pro", "gemini-1.5-pro", ""),
        ("anthropic", "yes" if settings.llm.anthropic_api_key else "no", "claude-3-sonnet", "claude-3-sonnet", ""),
    ]

    for name, status, text_model, vision_model, cost in provider_info:
        providers_table.add_row(name, status, text_model, vision_model, cost)

    console.print(providers_table)
    console.print("\n[dim]To use a provider, set LLM_PROVIDER=name and the corresponding API key[/dim]")


def run():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    run()
