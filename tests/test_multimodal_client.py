#!/usr/bin/env python3
"""
Test script for LLMMultimodalClient multimodal waveform analysis.

This script demonstrates:
1. Creating a LLMMultimodalClient with different providers
2. Analyzing a waveform image
3. Extracting metrics
4. Detecting anomalies
5. Diagnosing failures
"""

import os
import sys
from pathlib import Path
from typing import Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from spec2testbench.infrastructure.waveform_checker.llm_multimodal_client import (
    LLMMultimodalClient, DiagnosticLevel
)
from spec2testbench.infrastructure.waveform_checker.waveform_checker import WaveformChecker
from spec2testbench.infrastructure.waveform_checker.waveform_plotter import WaveformPlotter

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_llm_multimodal_client(provider: str = "openai",
                               api_key: Optional[str] = None,
                               image_path: Optional[Path] = None) -> None:
    """
    Test LLMMultimodalClient with a waveform image.
    
    Args:
        provider: LLM provider ('openai', 'deepseek', 'gemini', 'anthropic')
        api_key: API key for the provider
        image_path: Path to waveform image (if not provided, will generate a test image)
    """
    print("\n" + "="*80)
    print("LLM Multimodal Waveform Analysis Test")
    print("="*80)
    
    # Initialize LLMMultimodalClient
    print(f"\n[1] Initializing LLMMultimodalClient with provider: {provider}")
    try:
        client = LLMMultimodalClient(
            provider=provider,
            api_key=api_key,
            temperature=0.3
        )
        print(f"✓ LLMMultimodalClient initialized successfully")
        print(f"  Model: {client.model}")
        print(f"  Provider: {client.provider}")
    except Exception as e:
        print(f"✗ Failed to initialize LLMMultimodalClient: {e}")
        return
    
    # Check if image exists, otherwise create a test image
    if image_path is None or not image_path.exists():
        print("\n[2] Generating test waveform image...")
        try:
            plotter = WaveformPlotter(output_dir=Path("./waveforms_test"))
            
            import numpy as np
            
            # Generate test signal: damped oscillation
            t = np.linspace(0, 1e-6, 1000)
            # Damped sine wave (simulating oscillator startup)
            signal = 2.5 * (1 - np.exp(-t / 0.3e-6)) * np.sin(2 * np.pi * 1e6 * t)
            
            signals = {"Output": signal}
            image_path = plotter.plot_transient(
                time=t,
                signals=signals,
                title="Test Waveform: Damped Oscillation",
                xlabel="Time (µs)",
                ylabel="Voltage (V)",
                save=True
            )
            print(f"✓ Test waveform image generated: {image_path}")
            print(f"  Waveform type: Damped oscillation")
            print(f"  Expected anomalies: Ringing, damped oscillation")
        except Exception as e:
            print(f"✗ Failed to generate test image: {e}")
            return
    else:
        print(f"\n[2] Using provided image: {image_path}")
    
    # Test 1: Basic waveform analysis
    print("\n[3] Testing waveform analysis (STANDARD diagnostic level)...")
    try:
        result = client.analyze_waveform(
            image_path=image_path,
            circuit_type="oscillator",
            expected_behavior="1 MHz sine wave with 2.5V amplitude",
            diagnostic_level=DiagnosticLevel.STANDARD
        )
        print(f"✓ Waveform analysis completed")
        print(f"  Waveform type: {result.waveform_type}")
        print(f"  Confidence: {result.confidence:.2f}")
        print(f"  Anomalies: {result.anomalies}")
        print(f"  Extracted metrics:")
        for metric, value in result.extracted_metrics.items():
            print(f"    - {metric}: {value}")
        print(f"  Recommendations: {result.recommendations[:2]}")
    except Exception as e:
        print(f"✗ Waveform analysis failed: {e}")
        return
    
    # Test 2: Metric extraction
    print("\n[4] Testing metric extraction...")
    try:
        metrics = client.extract_metrics(
            image_path=image_path,
            metrics_to_extract=["amplitude", "frequency", "rise_time"],
            circuit_type="oscillator"
        )
        print(f"✓ Metric extraction completed")
        print(f"  Extracted metrics: {metrics}")
    except Exception as e:
        print(f"✗ Metric extraction failed: {e}")
    
    # Test 3: Anomaly detection
    print("\n[5] Testing anomaly detection...")
    try:
        thresholds = {
            "amplitude": {"min": 2.0, "max": 3.0},
            "frequency": {"min": 0.9e6, "max": 1.1e6}
        }
        anomalies_result = client.detect_anomalies(
            image_path=image_path,
            circuit_type="oscillator",
            thresholds=thresholds
        )
        print(f"✓ Anomaly detection completed")
        print(f"  Detected anomalies: {anomalies_result['anomalies']}")
        print(f"  Severity: {anomalies_result['severity']}")
        print(f"  Recommendations: {anomalies_result['recommendations'][:2]}")
    except Exception as e:
        print(f"✗ Anomaly detection failed: {e}")
    
    # Test 4: Failure diagnosis
    print("\n[6] Testing failure diagnosis...")
    try:
        failed_spec = {
            "amplitude": 0.5,  # Below minimum
            "frequency": 1e6
        }
        diagnosis = client.diagnose_failure(
            image_path=image_path,
            failed_specification=failed_spec,
            circuit_type="oscillator"
        )
        print(f"✓ Failure diagnosis completed")
        print(f"  Root cause: {diagnosis['root_cause']}")
        print(f"  Recommendations: {diagnosis['recommendations'][:2]}")
        print(f"  Confidence: {diagnosis['confidence']:.2f}")
    except Exception as e:
        print(f"✗ Failure diagnosis failed: {e}")
    
    # Test 5: Image optimization for vision LLM
    print("\n[7] Testing image optimization for vision LLM...")
    try:
        plotter = WaveformPlotter()
        optimized_path = plotter.optimize_for_vision_llm(
            image_path=image_path,
            test_name="Oscillator Frequency Test",
            circuit_type="Ring Oscillator",
            specification={"frequency": {"min": 0.9e6, "max": 1.1e6}},
            anomalies=["ringing", "damped_oscillation"]
        )
        print(f"✓ Image optimization completed")
        print(f"  Optimized image: {optimized_path}")
        print(f"  Original size: {image_path.stat().st_size / 1024:.1f} KB")
        print(f"  Optimized size: {optimized_path.stat().st_size / 1024:.1f} KB")
    except Exception as e:
        print(f"✗ Image optimization failed: {e}")
    
    # Test 6: Integration with WaveformChecker
    print("\n[8] Testing integration with WaveformChecker...")
    try:
        checker = WaveformChecker(
            provider=provider,
            api_key=api_key
        )
        
        # Verify multimodal client is available
        if checker.multimodal_client:
            print(f"✓ WaveformChecker has LLMMultimodalClient")
            
            # Test multimodal analysis
            analysis_dict = checker.analyze_with_multimodal(
                image_path=image_path,
                circuit_type="oscillator"
            )
            print(f"✓ WaveformChecker multimodal analysis completed")
            print(f"  Waveform type: {analysis_dict['waveform_type']}")
        else:
            print(f"✗ WaveformChecker doesn't have multimodal client")
    except Exception as e:
        print(f"✗ WaveformChecker integration failed: {e}")
    
    print("\n" + "="*80)
    print("Test completed successfully!")
    print("="*80 + "\n")


def test_waveform_plotter() -> None:
    """Test WaveformPlotter with various waveforms."""
    print("\n" + "="*80)
    print("WaveformPlotter Test")
    print("="*80)
    
    plotter = WaveformPlotter(output_dir=Path("./waveforms_test"))
    
    import numpy as np
    
    # Create test waveforms
    t = np.linspace(0, 1e-6, 1000)
    
    # 1. Transient response
    print("\n[1] Generating transient response...")
    signal = 2.5 * (1 - np.exp(-t / 0.2e-6)) * np.sin(2 * np.pi * 1e6 * t)
    signals = {"Output": signal}
    path1 = plotter.plot_transient(
        time=t,
        signals=signals,
        title="Transient Response with Damping",
        save=True
    )
    print(f"✓ Saved: {path1}")
    
    # 2. Frequency response
    print("\n[2] Generating frequency response...")
    freq = np.logspace(3, 9, 100)
    magnitude = 100 / np.sqrt(1 + (freq / 1e6)**2)
    phase = np.arctan(freq / 1e6)
    path2 = plotter.plot_ac_response(
        frequency=freq,
        magnitude=magnitude,
        phase=phase,
        title="AC Frequency Response",
        save=True
    )
    print(f"✓ Saved: {path2}")
    
    # 3. FFT spectrum
    print("\n[3] Generating FFT spectrum...")
    sig = np.sin(2 * np.pi * 1e6 * t) + 0.1 * np.sin(2 * np.pi * 3e6 * t)
    fft_result = np.abs(np.fft.fft(sig))
    fft_freq = np.fft.fftfreq(len(t), t[1] - t[0])
    path3 = plotter.plot_fft(
        frequency=fft_freq[:len(fft_freq)//2],
        spectrum=fft_result[:len(fft_result)//2],
        fundamental_freq=1e6,
        title="FFT Spectrum with Harmonics",
        save=True
    )
    print(f"✓ Saved: {path3}")
    
    print("\n" + "="*80)
    print("WaveformPlotter test completed!")
    print("="*80 + "\n")


def main():
    """Main test entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Test LLMMultimodalClient multimodal waveform analysis"
    )
    parser.add_argument(
        "--provider",
        default="openai",
        choices=["openai", "deepseek", "gemini", "anthropic"],
        help="LLM provider to use"
    )
    parser.add_argument(
        "--api-key",
        help="API key for the provider (if not set via environment)"
    )
    parser.add_argument(
        "--image",
        help="Path to waveform image (if not provided, will generate test image)"
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Skip LLM tests and only test image generation"
    )
    
    args = parser.parse_args()
    
    # Get API key from argument or environment
    api_key = args.api_key
    if not api_key:
        env_var = f"{args.provider.upper()}_API_KEY"
        api_key = os.getenv(env_var)
        if not api_key and not args.skip_llm:
            print(f"⚠️  Warning: {env_var} not set")
            print(f"  Set it via environment variable or --api-key argument")
    
    # Convert image path if provided
    image_path = Path(args.image) if args.image else None
    
    # Run tests
    try:
        # Test waveform plotter first (doesn't need LLM)
        test_waveform_plotter()
        
        # Test multimodal client if not skipped
        if not args.skip_llm:
            test_llm_multimodal_client(
                provider=args.provider,
                api_key=api_key,
                image_path=image_path
            )
        else:
            print("\n[INFO] Skipping LLM tests (--skip-llm flag set)")
            print("[INFO] To run LLM tests, set API key and remove --skip-llm flag")
            
    except KeyboardInterrupt:
        print("\n\n[INFO] Tests interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
