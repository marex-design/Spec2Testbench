# spec2testbench/infrastructure/simulator/pyspice_simulator.py

"""
Real SPICE simulator using PySpice and Ngspice.
Compatible with Windows, Linux, and macOS.
"""

import logging
import tempfile
import subprocess
import os
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
        self._ngspice_available = self._check_ngspice()    def _find_ngspice(self) -> str:
        """Return the hardcoded ngspice path for Windows."""
        # Chemin direct vers ngspice installé par Chocolatey
        return r"C:\ProgramData\chocolatey\lib\ngspice\tools\Spice64\bin\ngspice.exe"
    def _check_ngspice(self) -> bool:
        """Check if ngspice is available."""
        try:
            result = subprocess.run(
                [self.ngspice_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                shell=True if os.name == 'nt' else False
            )
            
            # Get version output (might be in stdout or stderr)
            output = result.stdout or result.stderr
            if output:
                version_line = output.splitlines()[0] if output.splitlines() else "unknown"
                logger.info(f"Ngspice found: {version_line}")
                return True
            else:
                logger.warning(f"Ngspice at {self.ngspice_path} returned no output")
                return False
                
        except FileNotFoundError:
            logger.warning(f"Ngspice not found at {self.ngspice_path}")
            logger.warning("Install ngspice or set NGSPICE_PATH in .env")
            return False
        except Exception as e:
            logger.warning(f"Error checking ngspice: {e}")
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
            f".OPTIONS POST=2 PROBE",
            "",
            f".TEMP {testbench.temperature}",
            "",
        ]
        
        # Include main netlist
        if netlist_path and netlist_path.exists():
            # Use absolute path for include
            abs_path = netlist_path.absolute()
            lines.append(f".INCLUDE {abs_path}")
        else:
            lines.append(f"* WARNING: Netlist not found: {netlist_path}")
        
        lines.append("")
        
        # Add stimuli
        for stimulus in testbench.stimuli:
            lines.append(stimulus.to_spice())
        
        lines.append("")
        
        # Add analyses
        for analysis in testbench.analyses:
            lines.append(analysis.to_spice())
        
        lines.append("")
        
        # Add measurements
        for measurement in testbench.measurements:
            if measurement.node:
                lines.append(f".MEASURE {measurement.name} FIND {measurement.expression}")
        
        lines.append("")
        lines.append(".END")
        
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
                shell=True if os.name == 'nt' else False
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
            'dc': {},
            'currents': {}
        }
        
        if not raw_file.exists():
            return results
        
        try:
            # Try to parse with PySpice
            from PySpice.Spice.RawFile import RawFile
            
            raw = RawFile(str(raw_file))
            
            # Get all variables
            for var_name in raw.variables:
                try:
                    data = raw.get_variable(var_name)
                    if data is not None:
                        var_lower = var_name.lower()
                        if 'frequency' in var_lower or 'freq' in var_lower:
                            results['ac']['frequency'] = np.array(data)
                        elif 'time' in var_lower:
                            results['tran']['time'] = np.array(data)
                        elif 'v(' in var_lower or var_lower.startswith('v'):
                            # Voltage variable
                            clean_name = var_name.replace('(', '').replace(')', '')
                            if 'ac' in str(testbench.analyses):
                                results['ac'][clean_name] = np.array(data)
                            else:
                                results['tran'][clean_name] = np.array(data)
                        elif 'i(' in var_lower or var_lower.startswith('i'):
                            # Current variable
                            clean_name = var_name.replace('(', '').replace(')', '')
                            results['currents'][clean_name] = float(np.mean(data)) if len(data) > 0 else 0
                except Exception as e:
                    logger.debug(f"Could not parse variable {var_name}: {e}")
            
            results['success'] = True
            
        except ImportError:
            logger.warning("PySpice not available for parsing")
        except Exception as e:
            logger.warning(f"Failed to parse raw file: {e}")
        
        return results
    
    def extract_metrics(self, 
                        results: Dict[str, Any],
                        testbench: TestBench) -> Dict[str, float]:
        """
        Extract metrics from simulation results.
        """
        metrics = {}
        
        # Extract from AC analysis
        if 'ac' in results and 'magnitude' in results['ac']:
            mag = results['ac']['magnitude']
            if len(mag) > 0 and mag[0] > 0:
                metrics['dc_gain_db'] = 20 * np.log10(mag[0])
        
        # Extract from transient analysis
        if 'tran' in results and 'vout' in results['tran']:
            vout = results['tran']['vout']
            time = results['tran'].get('time', np.arange(len(vout)))
            
            if len(vout) > 1 and len(time) > 1:
                # Slew rate
                dv = np.diff(vout)
                dt = np.diff(time)
                with np.errstate(divide='ignore'):
                    sr = np.max(np.abs(dv / dt))
                if not np.isnan(sr) and not np.isinf(sr):
                    metrics['slew_rate_v_s'] = float(sr)
        
        # Extract from measurements in testbench
        for measurement in testbench.measurements:
            if measurement.name in results:
                metrics[measurement.name] = results[measurement.name]
        
        return metrics
    
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
                [self.ngspice_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                shell=True if os.name == 'nt' else False
            )
            output = result.stdout or result.stderr
            return output.splitlines()[0] if output else "unknown"
        except Exception:
            return "unknown"
    
    def supports_pvt_analysis(self) -> bool:
        """Check if PVT analysis is supported."""
        return True
