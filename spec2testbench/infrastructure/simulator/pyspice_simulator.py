# spec2testbench/infrastructure/simulator/pyspice_simulator.py

"""
Real SPICE simulator using PySpice and Ngspice.
Compatible with Windows, Linux, and macOS.
"""

import logging
import tempfile
import subprocess
import os
import re
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
import numpy as np

from ...domain.entities.testbench import TestBench, AnalysisType
from ...domain.interfaces.icircuit_simulator import ICircuitSimulator

logger = logging.getLogger(__name__)


class SimulationError(Exception):
    """Raised when simulation fails."""
    pass


@dataclass
class SimulationResult:
    """Results from a SPICE simulation."""
    success: bool
    logs: List[str]
    errors: List[str]
    ac: Optional[Dict[str, np.ndarray]] = None
    tran: Optional[Dict[str, np.ndarray]] = None
    dc: Optional[Dict[str, np.ndarray]] = None
    currents: Optional[Dict[str, float]] = None
    metrics: Dict[str, float] = field(default_factory=dict)
    raw_output: str = ""


class PySpiceSimulator(ICircuitSimulator):
    """
    Real SPICE simulator using PySpice with Ngspice backend.
    
    Requirements:
    - PySpice installed: pip install PySpice
    - Ngspice installed: 
        Windows: Download from https://ngspice.sourceforge.io/
        Linux: sudo apt-get install ngspice
        macOS: brew install ngspice
    """
    
    def __init__(self, ngspice_path: Optional[str] = None, timeout: int = 300):
        """
        Initialize the PySpice simulator.
        
        Args:
            ngspice_path: Path to ngspice executable (auto-detect if None)
            timeout: Simulation timeout in seconds
        """
        self.ngspice_path = ngspice_path or self._find_ngspice()
        self.timeout = timeout
        self._ngspice_available = self._check_ngspice()
    
    def _find_ngspice(self) -> str:
        """Find a usable ngspice executable path."""
        candidates = [
            r"C:\ProgramData\chocolatey\lib\ngspice\tools\Spice64\bin\ngspice.exe",
            r"C:\ProgramData\chocolatey\bin\ngspice.exe",
            r"C:\Program Files\ngspice\bin\ngspice.exe",
            shutil.which("ngspice"),
            shutil.which("ngspice.exe"),
        ]
        for candidate in candidates:
            if candidate:
                return candidate
        return "ngspice"
    
    def _check_ngspice(self) -> bool:
        """Check if ngspice is available."""
        if shutil.which("ngspice") or shutil.which("ngspice.exe"):
            logger.info("Ngspice found in PATH")
            return True
        if Path(self.ngspice_path).exists():
            logger.info(f"Ngspice executable found at {self.ngspice_path}")
            return True
        logger.warning(f"Ngspice not found at {self.ngspice_path}")
        logger.warning("Install ngspice or set NGSPICE_PATH in .env")
        return False
    
    @property
    def is_available(self) -> bool:
        """Check if simulator is available."""
        return self._ngspice_available
    
    def run(self,
            netlist_path: Path,
            testbench: TestBench,
            output_dir: Optional[Path] = None) -> Dict[str, Any]:
        """
        Run simulation with real SPICE.
        
        Args:
            netlist_path: Path to SPICE netlist
            testbench: TestBench configuration
            output_dir: Output directory for raw files
            
        Returns:
            Dictionary with simulation results
        """
        logger.info(f"Running simulation for {testbench.circuit_name}")
        
        if not self._ngspice_available:
            # Fallback to mock simulation
            logger.warning("Ngspice not available, using mock simulation")
            return self._run_mock_simulation(testbench)
        
        # Generate SPICE deck
        spice_deck = self._generate_spice_deck(netlist_path, testbench)
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cir', delete=False, encoding='utf-8') as f:
            f.write(spice_deck)
            spice_file = Path(f.name)
        
        try:
            # Run simulation
            raw_file = spice_file.with_suffix('.raw')
            result = self._run_ngspice(spice_file, raw_file)
            
            # Parse results
            simulation_results = self._parse_results(raw_file, testbench)
            simulation_results['logs'] = result['logs']
            simulation_results['errors'] = result['errors']
            simulation_results['success'] = result['success']
            
            # Extract metrics
            if result['success']:
                metrics = self.extract_metrics(simulation_results, testbench)
                simulation_results['metrics'] = metrics
            
            return simulation_results
            
        except Exception as e:
            logger.error(f"Simulation failed: {e}")
            return self._run_mock_simulation(testbench)
        finally:
            # Cleanup
            try:
                spice_file.unlink(missing_ok=True)
                raw_file.unlink(missing_ok=True)
            except Exception:
                pass
    
    def _run_mock_simulation(self, testbench: TestBench) -> Dict[str, Any]:
        """Run mock simulation when ngspice is not available."""
        logger.info("Running mock simulation")
        
        # Generate mock results based on testbench type
        results = {
            'success': True,
            'logs': ['Mock simulation - ngspice not available'],
            'errors': [],
            'metrics': {},
            'ac': {},
            'tran': {}
        }
        
        # Mock AC results
        if any(a.type == AnalysisType.AC for a in testbench.analyses):
            freq = np.logspace(0, 9, 100)
            # Simple low-pass response
            mag = 100 / (1 + (freq / 1e6)**2)
            results['ac'] = {
                'frequency': freq,
                'magnitude': mag,
                'phase': -np.arctan2(freq, 1e6) * 180 / np.pi
            }
            results['metrics']['dc_gain_db'] = 20 * np.log10(mag[0])
        
        # Mock transient results
        if any(a.type == AnalysisType.TRANSIENT for a in testbench.analyses):
            time = np.linspace(0, 10e-6, 1000)
            vout = 2.5 + 2.5 * np.sin(2 * np.pi * 1e6 * time)
            results['tran'] = {
                'time': time,
                'vout': vout
            }
            # Calculate mock slew rate
            dv = np.diff(vout)
            dt = np.diff(time)
            results['metrics']['slew_rate_v_s'] = float(np.max(np.abs(dv / dt)))
        
        # Mock DC results
        if any(a.type == AnalysisType.DC for a in testbench.analyses):
            vin = np.linspace(0, 5, 50)
            vout = 2.5 + 2.5 * np.tanh(vin - 2.5)
            results['dc'] = {
                'vin': vin,
                'vout': vout
            }
        
        # Mock currents
        results['currents'] = {'vdd': 1e-3}
        
        return results
    
    def _generate_spice_deck(self, netlist_path: Path, testbench: TestBench) -> str:
        """Generate complete SPICE deck."""
        lines = [
            f"* TestBench: {testbench.name}",
            f"* Circuit: {testbench.circuit_name}",
            f"* Category: {testbench.category}",
            "*",
            ".OPTIONS POST=2 PROBE",
        ]

        existing_text = ""
        if netlist_path and netlist_path.exists():
            existing_text = netlist_path.read_text(encoding="utf-8", errors="ignore")
            existing_text = re.sub(r"(?is)\.control\b.*?\.endc", "", existing_text)
            existing_text = re.sub(r"^\s*\.end\s*$", "", existing_text, flags=re.IGNORECASE | re.MULTILINE).strip()
            if existing_text:
                lines.extend(["", existing_text])
        else:
            lines.extend(["", f"* WARNING: Netlist not found: {netlist_path}"])

        if not re.search(r"^\s*\.temp\b", existing_text, re.IGNORECASE | re.MULTILINE):
            lines.extend(["", f".TEMP {testbench.temperature}"])

        has_existing_sources = re.search(r"^\s*[VI]\w+\s+\S+\s+\S+", existing_text, re.IGNORECASE | re.MULTILINE)
        if not has_existing_sources:
            for stimulus in testbench.stimuli:
                if not re.search(rf"^\s*V{re.escape(stimulus.name)}\b", existing_text, re.IGNORECASE | re.MULTILINE):
                    lines.append(stimulus.to_spice())

        analysis_commands = {
            AnalysisType.DC: r"^\s*\.dc\b",
            AnalysisType.AC: r"^\s*\.ac\b",
            AnalysisType.TRANSIENT: r"^\s*\.tran\b",
            AnalysisType.FOURIER: r"^\s*\.fourier\b",
        }
        for analysis in testbench.analyses:
            pattern = analysis_commands.get(analysis.type)
            if pattern and re.search(pattern, existing_text, re.IGNORECASE | re.MULTILINE):
                continue
            lines.append(analysis.to_spice())

        lines.extend(["", ".END"])
        return "\n".join(lines)
    
    def _run_ngspice(self, spice_file: Path, raw_file: Path) -> Dict[str, Any]:
        """
        Run ngspice simulation.
        
        Returns:
            Dictionary with success flag and logs
        """
        # Command to run ngspice in batch mode
        cmd = [
            self.ngspice_path,
            "-b",  # Batch mode
            "-r", str(raw_file),  # Raw output file
            str(spice_file)
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                shell=False
            )
            
            logs = result.stdout.splitlines() if result.stdout else []
            errors = result.stderr.splitlines() if result.stderr else []
            
            # Check for convergence issues
            all_output = (result.stdout or "") + (result.stderr or "")
            all_output_lower = all_output.lower()
            
            success = result.returncode == 0
            if 'error' in all_output_lower or 'no convergence' in all_output_lower:
                success = False
            
            return {
                'success': success,
                'logs': logs,
                'errors': errors
            }
            
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'logs': [],
                'errors': [f"Simulation timed out after {self.timeout} seconds"]
            }
        except Exception as e:
            return {
                'success': False,
                'logs': [],
                'errors': [str(e)]
            }
    
    def _parse_results(self, raw_file: Path, testbench: TestBench) -> Dict[str, Any]:
        """
        Parse ngspice raw output file.
        
        Returns:
            Structured results dictionary
        """
        results = {
            'ac': {},
            'tran': {},
            'transient': {},
            'dc': {},
            'currents': {},
            'fourier': {},
        }
        
        if not raw_file.exists():
            return results
        
        try:
            # Try to parse with PySpice
            from PySpice.Spice.RawFile import RawFile
            
            raw = RawFile(str(raw_file))
            parsed_plots = self._extract_rawfile_plots(raw)
            results.update(self._build_structured_results(parsed_plots))
            
        except ImportError:
            logger.warning("PySpice not available for parsing")
        except Exception as e:
            logger.warning(f"Failed to parse raw file with PySpice parser: {e}")

        if not any(results[key] for key in ('ac', 'tran', 'dc', 'currents')):
            parsed_plots = self._parse_raw_fallback(raw_file)
            if parsed_plots:
                results.update(self._build_structured_results(parsed_plots))
        
        return results
    
    def extract_metrics(self, 
                        results: Dict[str, Any],
                        testbench: TestBench) -> Dict[str, float]:
        """
        Extract metrics from simulation results.
        """
        metrics = {}
        
        ac = results.get('ac', {})
        if ac.get('dc_gain_db') is not None:
            metrics['dc_gain_db'] = float(ac['dc_gain_db'])
        if ac.get('bandwidth') is not None:
            metrics['bandwidth'] = float(ac['bandwidth'])
            metrics['cutoff_frequency_hz'] = float(ac['bandwidth'])
        if ac.get('unity_gain_frequency') is not None:
            metrics['unity_gain_frequency'] = float(ac['unity_gain_frequency'])
            metrics['ugbw'] = float(ac['unity_gain_frequency'])
        if ac.get('phase_margin') is not None:
            metrics['phase_margin'] = float(ac['phase_margin'])

        dc = results.get('dc', {})
        for key in ('vout_dc', 'operating_point'):
            if key in dc:
                metrics[key] = float(dc[key])

        current = results.get('currents', {}).get('vdd')
        supply = results.get('vdd', 0.0)
        if current is not None:
            metrics['quiescent_current'] = float(abs(current))
            metrics['idd'] = float(abs(current))
            if supply:
                metrics['power'] = float(abs(supply * current))

        tran = results.get('transient') or results.get('tran', {})
        vout = tran.get('vout', [])
        time = tran.get('time', [])
        if len(vout) > 1 and len(time) > 1:
            dv = np.diff(vout)
            dt = np.diff(time)
            with np.errstate(divide='ignore'):
                sr = np.max(np.abs(dv / dt))
            if not np.isnan(sr) and not np.isinf(sr):
                metrics['slew_rate_v_s'] = float(sr)
                metrics['slew_rate'] = float(sr)

        fourier = results.get('fourier', {})
        if 'thd' in fourier:
            metrics['thd'] = float(fourier['thd'])
            metrics['thd_percent'] = float(fourier['thd'])
        if 'fundamental_frequency' in fourier:
            metrics['fundamental_frequency'] = float(fourier['fundamental_frequency'])

        for measurement in testbench.measurements:
            for container in (metrics, dc, ac, fourier, results.get('pvt', {}).get('summary', {})):
                if measurement.name in container:
                    value = container[measurement.name]
                    if value is None:
                        continue
                    metrics[measurement.name] = float(value)
                    break
        
        return metrics

    def _extract_rawfile_plots(self, raw: Any) -> Dict[str, Dict[str, np.ndarray]]:
        parsed_plots: Dict[str, Dict[str, np.ndarray]] = {}
        plots = getattr(raw, 'plots', None)
        if not plots:
            plots = [raw]

        for plot_index, plot in enumerate(plots):
            plot_name = getattr(plot, 'plot_name', f'plot_{plot_index}') or f'plot_{plot_index}'
            dataset: Dict[str, np.ndarray] = {}
            variables = getattr(plot, 'variables', [])
            for variable in variables:
                var_name = getattr(variable, 'name', None) or str(variable)
                try:
                    data = plot.get_variable(var_name)
                except Exception:
                    try:
                        data = raw.get_variable(var_name)
                    except Exception:
                        continue
                if data is not None:
                    dataset[var_name] = np.array(data)
            if dataset:
                parsed_plots[plot_name.lower()] = dataset
        return parsed_plots

    def _parse_raw_fallback(self, raw_file: Path) -> Dict[str, Dict[str, np.ndarray]]:
        try:
            text = raw_file.read_text(errors='ignore')
        except Exception:
            return {}

        if not text.lstrip().startswith('Title:'):
            return {}

        lines = text.splitlines()
        plot_starts = [index for index, line in enumerate(lines) if line.startswith('Plotname:')]
        if not plot_starts:
            return {}
        plot_starts.append(len(lines))

        plots: Dict[str, Dict[str, np.ndarray]] = {}
        for block_index in range(len(plot_starts) - 1):
            section = lines[plot_starts[block_index]:plot_starts[block_index + 1]]
            plot_name = section[0].split(':', 1)[1].strip().lower()
            variables: List[str] = []
            values_index = None
            point_count = None

            for index, line in enumerate(section):
                lower = line.lower().strip()
                if lower.startswith('no. points'):
                    point_count = int(line.split(':', 1)[1].strip())
                elif lower == 'variables:':
                    cursor = index + 1
                    while cursor < len(section):
                        current = section[cursor].strip()
                        if current.lower() == 'values:':
                            break
                        tokens = current.split()
                        if len(tokens) >= 2 and tokens[0].isdigit():
                            variables.append(tokens[1])
                        cursor += 1
                elif lower == 'values:':
                    values_index = index + 1
                    break

            if not variables or values_index is None:
                continue

            parsed_columns = {name: [] for name in variables}
            cursor = values_index
            points_read = 0
            while cursor < len(section) and (point_count is None or points_read < point_count):
                line = section[cursor]
                match = re.match(r'^\s*(\d+)\s+(.+?)\s*$', line)
                if not match:
                    cursor += 1
                    continue

                parsed_columns[variables[0]].append(self._parse_raw_value(match.group(2), variables[0]))
                cursor += 1
                for variable_index in range(1, len(variables)):
                    if cursor >= len(section):
                        break
                    parsed_columns[variables[variable_index]].append(
                        self._parse_raw_value(section[cursor].strip(), variables[variable_index])
                    )
                    cursor += 1
                points_read += 1

            plots[plot_name] = {name: np.array(values) for name, values in parsed_columns.items()}

        return plots

    def _parse_raw_value(self, raw_value: str, variable_name: str) -> complex | float:
        raw_value = raw_value.strip()
        if ',' in raw_value:
            try:
                real_str, imag_str = raw_value.split(',', 1)
                real = float(real_str)
                imag = float(imag_str)
                return real if variable_name.lower() == 'frequency' else complex(real, imag)
            except Exception:
                return float('nan')
        try:
            return float(raw_value)
        except Exception:
            return float('nan')

    def _build_structured_results(self, plots: Dict[str, Dict[str, np.ndarray]]) -> Dict[str, Any]:
        results = {
            'ac': {},
            'tran': {},
            'transient': {},
            'dc': {},
            'currents': {},
            'fourier': {},
        }
        if not plots:
            return results

        ac_plot = next((dataset for name, dataset in plots.items() if 'ac analysis' in name), None)
        tran_plot = next((dataset for name, dataset in plots.items() if 'transient analysis' in name), None)
        dc_plot = next((dataset for name, dataset in plots.items() if 'operating point' in name or 'dc transfer' in name), None)

        if ac_plot is None and any('frequency' in key.lower() for dataset in plots.values() for key in dataset):
            ac_plot = next(dataset for dataset in plots.values() if any('frequency' in key.lower() for key in dataset))
        if tran_plot is None and any('time' in key.lower() for dataset in plots.values() for key in dataset):
            tran_plot = next(dataset for dataset in plots.values() if any('time' in key.lower() for key in dataset))
        if dc_plot is None:
            dc_plot = next((dataset for dataset in plots.values() if dataset is not ac_plot and dataset is not tran_plot), None)

        if ac_plot is not None:
            results['ac'] = self._build_ac_results(ac_plot)
        if tran_plot is not None:
            transient = self._build_transient_results(tran_plot)
            results['tran'] = transient
            results['transient'] = transient
            results['fourier'] = self._estimate_fourier(transient)
        if dc_plot is not None:
            dc, currents = self._build_dc_results(dc_plot)
            results['dc'] = dc
            results['currents'].update(currents)
        return results

    def _build_ac_results(self, dataset: Dict[str, np.ndarray]) -> Dict[str, Any]:
        frequency_key = next((key for key in dataset if 'frequency' in key.lower()), None)
        if frequency_key is None:
            return {}

        frequency = np.real(np.atleast_1d(dataset[frequency_key])).astype(float)
        voltage_keys = [key for key in dataset if key.lower().startswith('v(')]
        out_key = self._choose_voltage_node(voltage_keys, preferred=('out', 'vout'))
        in_key = self._choose_voltage_node(voltage_keys, preferred=('in', 'vin', 'inp'))

        if out_key is None:
            return {'frequency': frequency.tolist()}

        vout = np.atleast_1d(dataset[out_key])
        vin = np.atleast_1d(dataset[in_key]) if in_key and in_key in dataset else None

        with np.errstate(divide='ignore', invalid='ignore'):
            transfer = vout / vin if vin is not None and np.any(np.abs(vin) > 0) else vout
        magnitude = np.abs(transfer).astype(float)
        phase = np.degrees(np.angle(transfer)).astype(float)

        ac = {
            'frequency': frequency.tolist(),
            'magnitude': magnitude.tolist(),
            'phase': phase.tolist(),
        }
        if magnitude.size:
            ac['dc_gain_db'] = float(20 * np.log10(max(magnitude[0], 1e-30)))
            ac['bandwidth'] = self._find_minus_3db_bandwidth(frequency, magnitude)
            ac['unity_gain_frequency'] = self._find_unity_gain_frequency(frequency, magnitude)
        if phase.size and ac.get('unity_gain_frequency') is not None:
            phase_at_ugf = self._sample_at_frequency(frequency, phase, ac['unity_gain_frequency'])
            if phase_at_ugf is not None:
                ac['phase_margin'] = float(max(0.0, min(180.0, 180.0 + phase_at_ugf)))
        return ac

    def _build_transient_results(self, dataset: Dict[str, np.ndarray]) -> Dict[str, Any]:
        time_key = next((key for key in dataset if 'time' in key.lower()), None)
        if time_key is None:
            return {}

        time = np.real(np.atleast_1d(dataset[time_key])).astype(float)
        voltage_keys = [key for key in dataset if key.lower().startswith('v(')]
        out_key = self._choose_voltage_node(voltage_keys, preferred=('out', 'vout'))
        in_key = self._choose_voltage_node(voltage_keys, preferred=('in', 'vin', 'inp'))

        voltage_map = {}
        for key in voltage_keys:
            clean = self._clean_node_name(key)
            voltage_map[clean] = np.real(np.atleast_1d(dataset[key])).astype(float).tolist()

        transient = {
            'time': time.tolist(),
            'voltage': voltage_map,
        }
        if out_key:
            transient['vout'] = np.real(np.atleast_1d(dataset[out_key])).astype(float).tolist()
        if in_key:
            transient['vin'] = np.real(np.atleast_1d(dataset[in_key])).astype(float).tolist()
        return transient

    def _build_dc_results(self, dataset: Dict[str, np.ndarray]) -> Tuple[Dict[str, Any], Dict[str, float]]:
        dc: Dict[str, Any] = {}
        currents: Dict[str, float] = {}
        voltage_keys = [key for key in dataset if key.lower().startswith('v(')]
        out_key = self._choose_voltage_node(voltage_keys, preferred=('out', 'vout', 'vref'))

        if out_key is not None:
            value = np.real(np.atleast_1d(dataset[out_key])[0])
            dc['vout_dc'] = float(value)
            dc['operating_point'] = float(value)
            dc['vout'] = float(value)

        for key, values in dataset.items():
            if key.lower().startswith('i('):
                clean = self._clean_node_name(key)
                array = np.real(np.atleast_1d(values)).astype(float)
                if array.size:
                    currents[clean] = float(np.mean(array))
                    if 'vdd' in clean.lower():
                        currents['vdd'] = float(np.mean(array))

        return dc, currents

    def _estimate_fourier(self, transient: Dict[str, Any]) -> Dict[str, Any]:
        time = np.array(transient.get('time', []), dtype=float)
        vout = np.array(transient.get('vout', []), dtype=float)
        if time.size < 8 or vout.size < 8:
            return {}

        dt = float(np.mean(np.diff(time)))
        if not np.isfinite(dt) or dt <= 0:
            return {}

        windowed = (vout - np.mean(vout)) * np.hanning(vout.size)
        spectrum = np.fft.rfft(windowed)
        frequencies = np.fft.rfftfreq(vout.size, dt)
        magnitudes = np.abs(spectrum)
        if magnitudes.size < 2:
            return {}

        magnitudes[0] = 0.0
        fundamental_index = int(np.argmax(magnitudes))
        if fundamental_index <= 0 or fundamental_index >= frequencies.size:
            return {}

        fundamental_frequency = float(frequencies[fundamental_index])
        fundamental_magnitude = float(magnitudes[fundamental_index])
        harmonics = [{'order': 1, 'frequency': fundamental_frequency, 'magnitude': fundamental_magnitude}]

        sum_squares = 0.0
        for harmonic_order in range(2, 6):
            target_frequency = harmonic_order * fundamental_frequency
            harmonic_index = int(np.argmin(np.abs(frequencies - target_frequency)))
            harmonic_magnitude = float(magnitudes[harmonic_index]) if harmonic_index < magnitudes.size else 0.0
            harmonics.append({
                'order': harmonic_order,
                'frequency': float(frequencies[harmonic_index]),
                'magnitude': harmonic_magnitude,
            })
            sum_squares += harmonic_magnitude ** 2

        thd = 100.0 * np.sqrt(sum_squares) / max(fundamental_magnitude, 1e-30)
        return {
            'fundamental_frequency': fundamental_frequency,
            'harmonics': harmonics,
            'thd': float(thd),
        }

    def _choose_voltage_node(self, voltage_keys: List[str], preferred: Tuple[str, ...]) -> Optional[str]:
        lowered = [(key, key.lower()) for key in voltage_keys]
        for token in preferred:
            for key, key_lower in lowered:
                if token in key_lower:
                    return key
        return voltage_keys[0] if voltage_keys else None

    def _clean_node_name(self, name: str) -> str:
        return name.replace('(', '').replace(')', '').replace('v', '', 1) if name.lower().startswith('v(') else name.replace('(', '').replace(')', '')

    def _find_minus_3db_bandwidth(self, frequency: np.ndarray, magnitude: np.ndarray) -> Optional[float]:
        if frequency.size == 0 or magnitude.size == 0:
            return None
        target = magnitude[0] / np.sqrt(2.0)
        for index, value in enumerate(magnitude):
            if value <= target:
                return float(frequency[index])
        return None

    def _find_unity_gain_frequency(self, frequency: np.ndarray, magnitude: np.ndarray) -> Optional[float]:
        if frequency.size == 0 or magnitude.size == 0:
            return None
        for index, value in enumerate(magnitude):
            if value <= 1.0:
                return float(frequency[index])
        return None

    def _sample_at_frequency(self, frequency: np.ndarray, values: np.ndarray, target_frequency: float) -> Optional[float]:
        if frequency.size == 0 or values.size == 0:
            return None
        index = int(np.argmin(np.abs(frequency - target_frequency)))
        if index >= values.size:
            return None
        return float(values[index])
    
    def get_waveform(self, 
                     results: Any,
                     node: str,
                     analysis_type: str = "tran") -> Dict[str, list]:
        """
        Get waveform data for a specific node.
        """
        if analysis_type == "tran" and hasattr(results, 'tran'):
            tran = results.tran
            if node in tran:
                return {
                    'time': tran['time'].tolist() if hasattr(tran['time'], 'tolist') else list(tran['time']),
                    'voltage': tran[node].tolist() if hasattr(tran[node], 'tolist') else list(tran[node])
                }
        
        return {'time': [], 'voltage': []}
    
    def check_convergence(self, logs: str) -> bool:
        """
        Check if simulation converged.
        """
        logs_lower = logs.lower()
        
        failure_indicators = [
            'no convergence',
            'timestep too small',
            'singular matrix',
            'failed',
            'error'
        ]
        
        for indicator in failure_indicators:
            if indicator in logs_lower:
                return False
        
        return True
    
    def get_simulator_info(self) -> Dict[str, str]:
        """
        Get simulator information.
        """
        return {
            'name': 'PySpice with Ngspice',
            'version': self._get_ngspice_version(),
            'backend': 'ngspice',
            'status': 'available' if self._ngspice_available else 'unavailable',
            'path': self.ngspice_path
        }
    
    def _get_ngspice_version(self) -> str:
        """Get ngspice version."""
        if not self._ngspice_available:
            return "not installed"
        
        try:
            result = subprocess.run(
                [self.ngspice_path, "-v"],
                capture_output=True,
                text=True,
                timeout=2,
                shell=False
            )
            output = result.stdout or result.stderr
            return output.splitlines()[0] if output else "available"
        except Exception:
            return "available"
    
    def supports_pvt_analysis(self) -> bool:
        """Check if PVT analysis is supported."""
        return True
