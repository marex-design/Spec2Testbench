"""
Command Line Interface for Spec2TestBench.
"""

from pathlib import Path
from typing import Optional

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
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Verify a circuit against specifications."""
    _safe_console_print("\nSpec2TestBench - Verification\n", style="bold cyan")

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
            pipeline = VerificationPipeline(use_llm=use_llm, llm_client=llm_client)
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


@app.command()
def generate(
    specs: Path = typer.Option(..., "--specs", "-s", help="Path to specifications YAML file"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output testbench path"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="LLM provider"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Disable LLM (use templates only)"),
):
    """Generate testbench from specifications."""
    console.print("\n[bold cyan]Spec2TestBench - TestBench Generation[/bold cyan]\n")

    if not specs.exists():
        console.print(f"[red]Specifications file not found: {specs}[/red]")
        raise typer.Exit(1)

    _set_provider(provider)
    use_llm = not no_llm and settings.llm.is_configured

    if not no_llm and not settings.llm.is_configured:
        console.print("[yellow]No LLM API keys configured. Using template-based generation.[/yellow]")
        console.print("   To enable LLM, set the appropriate API key in .env file\n")

    llm_client = None
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
        pipeline = VerificationPipeline(use_llm=use_llm, llm_client=llm_client)
        testbench = pipeline.testbench_gen.generate(specification)
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
def diagnose(
    waveform: Path = typer.Option(..., "--waveform", "-w", help="Path to waveform image (PNG)"),
    specs: Optional[Path] = typer.Option(None, "--specs", "-s", help="Path to specifications YAML file"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="LLM provider"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output report path"),
):
    """Diagnose a circuit failure from waveform image."""
    console.print("\n[bold cyan]Spec2TestBench - Waveform Diagnosis[/bold cyan]\n")

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
    output: Path = typer.Option(Path("schematic.png"), "--output", "-o", help="Output PNG path"),
):
    """Draw a schematic figure from a SPICE netlist."""
    from ...infrastructure.schematic import netlist_to_schematic

    console.print("\n[bold cyan]Spec2TestBench - Schematic Drawing[/bold cyan]\n")

    if not netlist.exists():
        console.print(f"[red]Netlist file not found: {netlist}[/red]")
        raise typer.Exit(code=1)

    try:
        netlist_text = netlist.read_text()
    except Exception as exc:
        console.print(f"[red]Cannot read netlist: {exc}[/red]")
        raise typer.Exit(code=1)

    try:
        result = netlist_to_schematic(netlist_text, str(output))
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[red]Drawing failed: {exc}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[green]Schematic saved to {result}[/green]")


@app.command()
def version():
    """Display version information."""
    console.print("[bold cyan]Spec2TestBench v0.1.0[/bold cyan]")
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
