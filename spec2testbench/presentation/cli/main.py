
"""
Command Line Interface for Spec2TestBench.
This module defines the CLI commands for the Spec2TestBench tool, allowing users to:
- Verify circuits against specifications- Generate testbenches from specifications
- Diagnose failures from waveform images
- Draw schematics from SPICE netlists
- Display version and configuration information
- List available LLM providers and their status

Developed by Exauce K. Maruba 
Co-authors: Christian Marie Moanda
"""

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from ...application.usecases.run_verification import VerificationPipeline
from ...presentation.formatters.report_formatter import ReportFormatter
from ...config.settings import settings
from ...infrastructure.llm.llm_client import LLMClient, LLMProvider
from ...application.services.acp_benchmark_runner import run_acp_benchmark, run_single_case
from ...domain.entities.specification import Specification
import json

# Initialize Typer app and console
app = typer.Typer(
    name="spec2testbench",
    help="Specs to SPICE Testbenches",
    add_completion=False,
)
console = Console()


@app.command()
def verify(
    specs: Path = typer.Option(..., "--specs", "-s", help="Path to specifications YAML file"),
    netlist: Optional[Path] = typer.Option(None, "--netlist", "-n", help="Path to SPICE netlist"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output directory"),
    format: str = typer.Option("markdown", "--format", "-f", help="Output format: markdown, json, console"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="LLM provider: openai, deepseek, gemini, anthropic"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Disable LLM (use templates only)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """
    Verify a circuit against specifications.
    
    This command:
    1. Reads specifications from YAML file
    2. Generates testbench (using LLM or templates)
    3. Runs simulation (if netlist provided)
    4. Verifies results against specifications
    5. Analyzes waveforms for failures
    6. Generates comprehensive report
    
    LLM Providers:
    - openai: GPT-4, GPT-4V (API key: OPENAI_API_KEY)
    - deepseek: DeepSeek-V3, DeepSeek-VL (API key: DEEPSEEK_API_KEY) - Plus économique
    - gemini: Google Gemini 1.5 Pro (API key: GOOGLE_API_KEY)
    - anthropic: Claude 3 (API key: ANTHROPIC_API_KEY)
    """
    console.print("\n[bold cyan] Spec2TestBench - Verification[/bold cyan]\n")
    
    # Check if specs file exists
    if not specs.exists():
        console.print(f"[red] Specifications file not found: {specs}[/red]")
        raise typer.Exit(1)
    
    # Check if netlist exists (if provided)
    if netlist and not netlist.exists():
        console.print(f"[yellow]⚠️ Netlist file not found: {netlist}[/yellow]")
        console.print("   Simulation will use mock results")
    
    # Strict schema-v2 path: deterministic scientific verification.
    specification_probe = Specification.from_yaml(specs)
    if specification_probe.is_v2:
        if netlist is None or not netlist.exists():
            console.print("[red]A real DUT netlist is required for strict schema v2 verification.[/red]")
            raise typer.Exit(2)
        out_dir = output or Path("results") / f"verify_{specification_probe.case_id or specs.stem}"
        report = run_single_case(specs, netlist, out_dir, allow_mock=False)
        if format.lower() == "json":
            console.print(json.dumps(report, indent=2, default=str))
        else:
            console.print(f"Execution: {report['execution_status']}")
            console.print(f"Compliance: {report['compliance_status']}")
            for row in report['criteria']:
                console.print(f"{row['criterion_status']:15} {row['metric']}: {row['message']}")
            console.print(f"Report: {out_dir / 'verification_report.json'}")
        code = 0 if report['compliance_status'] == 'COMPLIANT' else 1
        raise typer.Exit(code)

    # Set output directory
    if output:
        settings.output.output_dir = output
        settings.output.waveform_dir = output / "waveforms"
        settings.output.report_dir = output / "reports"
    
    # Override provider if specified via command line
    if provider:
        if provider not in ["openai", "deepseek", "gemini", "anthropic"]:
            console.print(f"[red]❌ Invalid provider: {provider}[/red]")
            console.print("   Valid providers: openai, deepseek, gemini, anthropic")
            raise typer.Exit(1)
        settings.llm.default_provider = provider
        console.print(f"[dim]📡 Using LLM provider: {provider}[/dim]")
    
    # Configure LLM usage
    use_llm = not no_llm and settings.llm.is_configured
    
    if not no_llm and not settings.llm.is_configured:
        console.print("[yellow]⚠️ No LLM API keys configured. Using template-based generation.[/yellow]")
        console.print("   To enable LLM, set the appropriate API key in .env file:")
        console.print("   - OpenAI:   OPENAI_API_KEY")
        console.print("   - DeepSeek: DEEPSEEK_API_KEY")
        console.print("   - Gemini:   GOOGLE_API_KEY")
        console.print("   - Anthropic: ANTHROPIC_API_KEY")
        console.print("")
    
    # Create LLM client if needed
    llm_client = None
    if use_llm:
        try:
            api_key = settings.llm.get_api_key()
            model = settings.llm.get_model(vision=False)
            llm_client = LLMClient(
                provider=settings.llm.default_provider,
                api_key=api_key,
                model=model,
                temperature=0.5
            )
            console.print(f"[green] LLM client initialized: {settings.llm.default_provider}[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠️ Failed to initialize LLM client: {e}[/yellow]")
            console.print("   Falling back to template-based generation\n")
            use_llm = False
            llm_client = None
    
    # Run verification
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Running verification...", total=None)
        
        pipeline = VerificationPipeline(use_llm=use_llm, llm_client=llm_client)
        report = pipeline.verify_from_yaml(specs, netlist)
        
        progress.remove_task(task)
    
    # Generate report
    formatter = ReportFormatter(output_dir=settings.output.report_dir)
    
    if format == "markdown":
        formatter.to_markdown(report, save=True)
        console.print(f"\n[green] Markdown report generated[/green]")
    elif format == "json":
        formatter.to_json(report, save=True)
        console.print(f"\n[green] JSON report generated[/green]")
    else:
        content = formatter.to_console(report)
        console.print(content)
    
    # Exit with appropriate code
    if report.overall_verdict.value in {"FAIL", "RUN"}:
        raise typer.Exit(1)
    raise typer.Exit(0)


@app.command()
def generate(
    specs: Path = typer.Option(..., "--specs", "-s", help="Path to specifications YAML file"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output testbench path"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="LLM provider: openai, deepseek, gemini, anthropic"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Disable LLM (use templates only)"),
):
    """
    Generate testbench from specifications.
    
    This command only generates the testbench without running simulation.
    """
    console.print("\n[bold cyan] Spec2TestBench - TestBench Generation[/bold cyan]\n")
    
    if not specs.exists():
        console.print(f"[red]❌ Specifications file not found: {specs}[/red]")
        raise typer.Exit(1)
    
    # Override provider if specified via command line
    if provider:
        if provider not in ["openai", "deepseek", "gemini", "anthropic"]:
            console.print(f"[red]❌ Invalid provider: {provider}[/red]")
            console.print("   Valid providers: openai, deepseek, gemini, anthropic")
            raise typer.Exit(1)
        settings.llm.default_provider = provider
        console.print(f"[dim]📡 Using LLM provider: {provider}[/dim]")
    
    use_llm = not no_llm and settings.llm.is_configured
    
    if not no_llm and not settings.llm.is_configured:
        console.print("[yellow]⚠️ No LLM API keys configured. Using template-based generation.[/yellow]")
        console.print("   To enable LLM, set the appropriate API key in .env file\n")
    
    # Create LLM client if needed
    llm_client = None
    if use_llm:
        try:
            api_key = settings.llm.get_api_key()
            model = settings.llm.get_model(vision=False)
            llm_client = LLMClient(
                provider=settings.llm.default_provider,
                api_key=api_key,
                model=model,
                temperature=0.5
            )
        except Exception as e:
            console.print(f"[yellow]⚠️ Failed to initialize LLM client: {e}[/yellow]")
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
    
    # Save testbench
    if output:
        pyspice_code = testbench.generate_pyspice_code()
        output.write_text(pyspice_code, encoding="utf-8")
        console.print(f"\n[green]✅ Testbench saved to {output}[/green]")
    else:
        console.print("\n[green]✅ Testbench generated:[/green]")
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
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="LLM provider: openai, deepseek, gemini, anthropic"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output report path"),
):
    """
    Diagnose a circuit failure from waveform image.
    
    This command uses multimodal LLM to analyze waveform images
    and provide structured diagnostics.
    """
    console.print("\n[bold cyan]🔬 Spec2TestBench - Waveform Diagnosis[/bold cyan]\n")
    
    if not waveform.exists():
        console.print(f"[red]❌ Waveform file not found: {waveform}[/red]")
        raise typer.Exit(1)
    
    # Override provider if specified
    if provider:
        if provider not in ["openai", "deepseek", "gemini", "anthropic"]:
            console.print(f"[red]❌ Invalid provider: {provider}[/red]")
            console.print("   Valid providers: openai, deepseek, gemini, anthropic")
            raise typer.Exit(1)
        settings.llm.default_provider = provider
        console.print(f"[dim]📡 Using LLM provider: {provider}[/dim]")
    
    # Check LLM configuration for multimodal
    use_llm = settings.llm.is_configured
    if not use_llm:
        console.print("[red]❌ No LLM API keys configured for multimodal analysis[/red]")
        console.print("   Please set the appropriate API key in .env file:")
        console.print("   - DeepSeek: DEEPSEEK_API_KEY (recommended, economical)")
        console.print("   - OpenAI:   OPENAI_API_KEY")
        console.print("   - Gemini:   GOOGLE_API_KEY")
        raise typer.Exit(1)
    
    # Load specification if provided
    specification = None
    if specs and specs.exists():
        from ...domain.entities.specification import Specification
        specification = Specification.from_yaml(specs)
        console.print(f"[green]✅ Specifications loaded from {specs}[/green]")
    
    # Create LLM client for multimodal
    try:
        api_key = settings.llm.get_api_key()
        model = settings.llm.get_model(vision=True)
        llm_client = LLMClient(
            provider=settings.llm.default_provider,
            api_key=api_key,
            model=model,
            temperature=0.5
        )
        console.print(f"[green]✅ Multimodal LLM client initialized: {settings.llm.default_provider}[/green]")
    except Exception as e:
        console.print(f"[red]❌ Failed to initialize LLM client: {e}[/red]")
        raise typer.Exit(1)
    
    # Run diagnosis
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Analyzing waveform...", total=None)
        
        from ...infrastructure.waveform_checker import WaveformChecker
        checker = WaveformChecker(llm_client=llm_client, use_llm=True)
        
        if specification:
            # Get failed metrics from spec (or use empty list)
            failed_metrics = list(specification.performance_targets.keys())
            result = checker.diagnose_failure(waveform, specification, failed_metrics)
        else:
            result = checker.check_specification(
                waveform, 
                metric_name="unknown",
                expected_min=0,
                expected_max=float('inf'),
                unit=""
            )
        
        progress.remove_task(task)
    
    # Display results
    console.print("\n[bold cyan] Diagnosis Results[/bold cyan]\n")
    console.print(f"  Verdict: {result.verdict.colorized_with_emoji}")
    console.print(f"  Confidence: {result.confidence:.1%}")
    console.print(f"  Waveform Type: {result.waveform_type.value}")
    console.print("")
    
    if result.anomalies:
        console.print("[yellow] Anomalies detected:[/yellow]")
        for anomaly in result.anomalies:
            console.print(f"    • {anomaly}")
        console.print("")
    
    console.print("[bold]Diagnosis:[/bold]")
    console.print(f"  {result.diagnosis}")
    console.print("")
    
    if result.recommendations:
        console.print("[bold green]🔧 Recommendations:[/bold green]")
        for rec in result.recommendations:
            console.print(f"  • {rec}")
    
    # Save report if output specified
    if output:
        report_content = result.to_markdown()
        output.write_text(report_content, encoding="utf-8")
        console.print(f"\n[green] Diagnosis report saved to {output}[/green]")


@app.command()
def draw(
    netlist: Path = typer.Option(..., "--netlist", "-n", help="Path to SPICE netlist file"),
    output: Path = typer.Option(Path("schematic.png"), "--output", "-o", help="Output PNG path"),
):
    """Draw a schematic figure from a SPICE netlist.

    This command parses the netlist and renders a schematic that reflects
    the actual components, nets, and connections it contains. Different
    netlists produce different figures.
    """
    from ...infrastructure.schematic import netlist_to_schematic

    console.print("\n[bold cyan] Spec2TestBench - Schematic Drawing[/bold cyan]\n")

    if not netlist.exists():
        console.print(f"[red]❌ Netlist file not found: {netlist}[/red]")
        raise typer.Exit(code=1)

    try:
        netlist_text = netlist.read_text()
    except Exception as e:
        console.print(f"[red]❌ Cannot read netlist: {e}[/red]")
        raise typer.Exit(code=1)

    try:
        result = netlist_to_schematic(netlist_text, str(output))
    except ValueError as e:
        console.print(f"[red]❌ {e}[/red]")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]❌ Drawing failed: {e}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[green]✅ Schematic saved to {result}[/green]")


@app.command("acp-benchmark")
def acp_benchmark(
    manifest: Path = typer.Option(Path("benchmark/analogcoder_pro/acp28_manifest.yaml"), "--manifest", help="ACP-28 manifest"),
    output: Path = typer.Option(Path("results/acp28"), "--output", "-o", help="Evidence output directory"),
    ngspice_path: Optional[str] = typer.Option(None, "--ngspice-path", help="Explicit ngspice executable"),
    timeout: float = typer.Option(300.0, "--timeout", help="Per-analysis timeout in seconds"),
):
    """Run the deterministic ACP-28 adapted benchmark with real ngspice evidence."""
    if not manifest.exists():
        console.print(f"[red]Manifest not found: {manifest}[/red]")
        raise typer.Exit(2)
    result = run_acp_benchmark(manifest, output, ngspice_path=ngspice_path, allow_mock=False, timeout_seconds=timeout)
    s=result['summary']
    table=Table(title="ACP-28 deterministic summary")
    table.add_column("Measure"); table.add_column("Value",justify="right")
    rows=[('Circuits',s['circuits']),('Simulation SUCCESS',s['simulation_success']),('COMPLIANT',s['COMPLIANT']),('NONCOMPLIANT',s['NONCOMPLIANT']),('NOT_EVALUATED',s['NOT_EVALUATED']),
          ('Evaluation rate',f"{100*s['evaluation_rate']:.2f}%"),('Compliance/evaluated',f"{100*s['compliance_evaluated']:.2f}%"),('Verified Compliance Yield',f"{100*s['verified_compliance_yield']:.2f}%"),
          ('Cov_circuits',f"{100*s['Cov_circuits']:.2f}%"),('Cov_metrics',f"{100*s['Cov_metrics']:.2f}%"),('Cov_analyses',f"{100*s['Cov_analyses']:.2f}%")]
    for k,v in rows: table.add_row(str(k),str(v))
    console.print(table); console.print(f"Evidence: {output}")



@app.command()
def version():
    """Display version information."""
    console.print("[bold cyan]Spec2TestBench v0.5.0[/bold cyan]")
    console.print("From Specs to SPICE Testbenches: LLM-Assisted Analog Verification")
    console.print("\n[dim]License: MIT[/dim]")
    console.print("\n[dim]Supported LLM Providers: OpenAI, DeepSeek, Gemini, Anthropic[/dim]")


@app.command()
def config():
    """Display current configuration."""
    console.print("\n[bold cyan]Configuration[/bold cyan]\n")
    
    table = Table(show_header=True, header_style="bold")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="white")
    
    table.add_row("LLM Enabled", "✓" if settings.use_llm else "✗")
    table.add_row("LLM Provider", settings.llm.default_provider)
    table.add_row("")
    table.add_row("[bold]API Keys:[/bold]", "")
    table.add_row("  OpenAI", "✓" if settings.llm.openai_api_key else "✗")
    table.add_row("  DeepSeek", "✓" if settings.llm.deepseek_api_key else "✗")
    table.add_row("  Gemini", "✓" if settings.llm.google_api_key else "✗")
    table.add_row("  Anthropic", "✓" if settings.llm.anthropic_api_key else "✗")
    table.add_row("")
    table.add_row("Simulator", settings.simulator.simulator_type)
    table.add_row("Warning Margin", f"{settings.warning_margin*100:.0f}%")
    table.add_row("Output Directory", str(settings.output.output_dir))
    
    console.print(table)
    
    # Show provider recommendation
    console.print("\n[dim]💡 Recommendation: Use DeepSeek for cost-effective testing[/dim]")
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
        ("deepseek", "✓" if settings.llm.deepseek_api_key else "✗", "deepseek-chat", "deepseek-vl", ""),
        ("openai", "✓" if settings.llm.openai_api_key else "✗", "gpt-4-turbo", "gpt-4-turbo", ""),
        ("gemini", "✓" if settings.llm.google_api_key else "✗", "gemini-1.5-pro", "gemini-1.5-pro", ""),
        ("anthropic", "✓" if settings.llm.anthropic_api_key else "✗", "claude-3-sonnet", "claude-3-sonnet", ""),
    ]
    
    for name, status, text_model, vision_model, cost in provider_info:
        status_icon = "✅" if "✓" in status else "❌"
        providers_table.add_row(name, f"{status_icon} {status}", text_model, vision_model, cost)
    
    console.print(providers_table)
    console.print("\n[dim]To use a provider, set LLM_PROVIDER=name and the corresponding API key[/dim]")


def run():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    run()
