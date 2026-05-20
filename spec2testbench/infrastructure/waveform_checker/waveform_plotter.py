# spec2testbench/infrastructure/waveform_checker/waveform_plotter.py

"""
WaveformPlotter - Génère des images PNG à partir de données de simulation.
"""

import math
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union, Any

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# Configuration matplotlib pour un rendu propre
plt.rcParams['figure.figsize'] = (12, 6)
plt.rcParams['figure.dpi'] = 100
plt.rcParams['savefig.dpi'] = 150
plt.rcParams['font.size'] = 10
plt.rcParams['lines.linewidth'] = 1.5


class WaveformPlotter:
    """
    Generate PNG waveform images from simulation data.
    
    Supports:
    - Transient waveforms (time vs voltage)
    - AC frequency response (Bode plots)
    - FFT spectra
    - Eye diagrams
    """
    
    def __init__(self, output_dir: Path = Path("./waveforms")):
        """
        Initialize the waveform plotter.
        
        Args:
            output_dir: Directory to save generated images
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def plot_transient(self,
                       time: np.ndarray,
                       signals: Dict[str, np.ndarray],
                       title: str = "Transient Response",
                       xlabel: str = "Time (s)",
                       ylabel: str = "Voltage (V)",
                       markers: Optional[Dict[str, str]] = None,
                       save: bool = True) -> Path:
        """
        Plot transient waveforms.
        
        Args:
            time: Time array (seconds)
            signals: Dictionary {signal_name: voltage_array}
            title: Plot title
            xlabel: X-axis label
            ylabel: Y-axis label
            markers: Optional markers for specific points
            save: If True, save to file
            
        Returns:
            Path to saved image
        """
        fig, ax = plt.subplots(figsize=(12, 6))
        
        # Plot signals
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
        for i, (name, data) in enumerate(signals.items()):
            color = colors[i % len(colors)]
            ax.plot(time, data, label=name, color=color, linewidth=1.5)
        
        # Add markers if provided
        if markers:
            for name, (t, v) in markers.items():
                ax.plot(t, v, 'ro', markersize=8)
                ax.annotate(name, (t, v), xytext=(5, 5), textcoords='offset points')
        
        # Labels and formatting
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.legend(loc='best')
        
        # Use scientific notation for time if needed
        if len(time) > 0 and time[-1] < 1e-3:
            ax.xaxis.set_major_formatter(plt.FuncFormatter(
                lambda x, p: f'{x*1e6:.1f}µ' if x < 0.001 else f'{x*1e3:.1f}m'
            ))
        
        plt.tight_layout()
        
        if save:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"transient_{timestamp}.png"
            filepath = self.output_dir / filename
            plt.savefig(filepath, dpi=150, bbox_inches="tight")
            plt.close()
            return filepath
        
        plt.show()
        return None
    
    def plot_ac_response(self,
                         frequency: np.ndarray,
                         magnitude: np.ndarray,
                         phase: Optional[np.ndarray] = None,
                         title: str = "AC Frequency Response",
                         save: bool = True) -> Path:
        """
        Plot AC frequency response (Bode plot).
        
        Args:
            frequency: Frequency array (Hz)
            magnitude: Magnitude array (linear, will be converted to dB)
            phase: Phase array (radians, optional)
            title: Plot title
            save: If True, save to file
            
        Returns:
            Path to saved image
        """
        if phase is not None:
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
        else:
            fig, ax1 = plt.subplots(figsize=(12, 6))
        
        # Convert magnitude to dB
        mag_db = 20 * np.log10(np.maximum(magnitude, 1e-30))
        
        # Magnitude plot
        ax1.semilogx(frequency, mag_db, 'b-', linewidth=1.5)
        ax1.set_ylabel("Magnitude (dB)")
        ax1.set_title(title)
        ax1.grid(True, alpha=0.3, linestyle='--')
        
        # Add -3dB line
        if len(mag_db) > 0:
            dc_gain = mag_db[0]
            ax1.axhline(y=dc_gain - 3, color='r', linestyle='--', alpha=0.5, label='-3dB')
        
        # Phase plot
        if phase is not None:
            phase_deg = phase * 180 / np.pi
            ax2.semilogx(frequency, phase_deg, 'r-', linewidth=1.5)
            ax2.set_xlabel("Frequency (Hz)")
            ax2.set_ylabel("Phase (degrees)")
            ax2.grid(True, alpha=0.3, linestyle='--')
            ax2.axhline(y=-180, color='k', linestyle='--', alpha=0.3)
            ax2.axhline(y=0, color='k', linestyle='--', alpha=0.3)
        
        ax1.legend(loc='best')
        plt.tight_layout()
        
        if save:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"ac_response_{timestamp}.png"
            filepath = self.output_dir / filename
            plt.savefig(filepath, dpi=150, bbox_inches="tight")
            plt.close()
            return filepath
        
        plt.show()
        return None
    
    def plot_fft(self,
                 frequency: np.ndarray,
                 spectrum: np.ndarray,
                 title: str = "FFT Spectrum",
                 fundamental_freq: Optional[float] = None,
                 save: bool = True) -> Path:
        """
        Plot FFT spectrum.
        
        Args:
            frequency: Frequency array (Hz)
            spectrum: Magnitude spectrum (linear)
            title: Plot title
            fundamental_freq: Fundamental frequency to highlight
            save: If True, save to file
            
        Returns:
            Path to saved image
        """
        fig, ax = plt.subplots(figsize=(12, 6))
        
        # Convert to dB
        spec_db = 20 * np.log10(np.maximum(spectrum, 1e-30))
        
        # Plot spectrum
        ax.semilogx(frequency, spec_db, 'b-', linewidth=1)
        ax.set_xlabel("Frequency (Hz)")
        ax.set_ylabel("Magnitude (dB)")
        ax.set_title(title)
        ax.grid(True, alpha=0.3, linestyle='--')
        
        # Highlight fundamental
        if fundamental_freq:
            ax.axvline(x=fundamental_freq, color='r', linestyle='--', alpha=0.5, label=f'Fundamental ({fundamental_freq/1e6:.1f} MHz)')
        
        # Highlight harmonics
        if fundamental_freq:
            for n in range(2, 6):
                harmonic = n * fundamental_freq
                ax.axvline(x=harmonic, color='g', linestyle=':', alpha=0.3)
        
        ax.legend(loc='best')
        plt.tight_layout()
        
        if save:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"fft_{timestamp}.png"
            filepath = self.output_dir / filename
            plt.savefig(filepath, dpi=150, bbox_inches="tight")
            plt.close()
            return filepath
        
        plt.show()
        return None
    
    def plot_eye_diagram(self,
                         signal: np.ndarray,
                         period: float,
                         samples_per_period: int,
                         title: str = "Eye Diagram",
                         save: bool = True) -> Path:
        """
        Plot eye diagram for high-speed signals.
        
        Args:
            signal: Signal array
            period: Period of the signal (seconds)
            samples_per_period: Number of samples per period
            title: Plot title
            save: If True, save to file
            
        Returns:
            Path to saved image
        """
        fig, ax = plt.subplots(figsize=(12, 6))
        
        # Calculate number of periods
        num_periods = len(signal) // samples_per_period
        
        # Plot each period overlaid
        for i in range(num_periods - 1):
            start = i * samples_per_period
            end = start + samples_per_period
            time = np.linspace(0, period, samples_per_period)
            ax.plot(time, signal[start:end], 'b-', alpha=0.3, linewidth=0.8)
        
        ax.set_xlabel(f"Time within period (s) - Period = {period*1e9:.1f} ns")
        ax.set_ylabel("Voltage (V)")
        ax.set_title(title)
        ax.grid(True, alpha=0.3, linestyle='--')
        
        plt.tight_layout()
        
        if save:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"eye_diagram_{timestamp}.png"
            filepath = self.output_dir / filename
            plt.savefig(filepath, dpi=150, bbox_inches="tight")
            plt.close()
            return filepath
        
        plt.show()
        return None
    
    def plot_comparison(self,
                        waveforms: Dict[str, np.ndarray],
                        time: np.ndarray,
                        title: str = "Waveform Comparison",
                        save: bool = True) -> Path:
        """
        Plot multiple waveforms for comparison.
        
        Args:
            waveforms: Dictionary {name: waveform_data}
            time: Time array
            title: Plot title
            save: If True, save to file
            
        Returns:
            Path to saved image
        """
        fig, ax = plt.subplots(figsize=(12, 6))
        
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
        
        for i, (name, data) in enumerate(waveforms.items()):
            color = colors[i % len(colors)]
            ax.plot(time, data, label=name, color=color, linewidth=1.5)
        
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Voltage (V)")
        ax.set_title(title)
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.legend(loc='best')
        
        plt.tight_layout()
        
        if save:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"comparison_{timestamp}.png"
            filepath = self.output_dir / filename
            plt.savefig(filepath, dpi=150, bbox_inches="tight")
            plt.close()
            return filepath
        
        plt.show()
        return None
    
    def add_annotations(self,
                        image_path: Path,
                        annotations: List[Dict],
                        output_path: Optional[Path] = None) -> Path:
        """
        Add annotations to an existing image.
        
        Args:
            image_path: Path to existing image
            annotations: List of annotations with 'x', 'y', 'text', 'color'
            output_path: Output path (default: overwrite or create new)
            
        Returns:
            Path to annotated image
        """
        import matplotlib.image as mpimg
        
        fig, ax = plt.subplots(figsize=(12, 6))
        
        # Load image
        img = mpimg.imread(image_path)
        ax.imshow(img)
        
        # Add annotations
        for ann in annotations:
            ax.annotate(
                ann['text'],
                xy=(ann['x'], ann['y']),
                xytext=(ann.get('text_x', ann['x'] + 10), 
                        ann.get('text_y', ann['y'] + 10)),
                color=ann.get('color', 'red'),
                fontsize=ann.get('fontsize', 10),
                arrowprops=dict(arrowstyle='->', color=ann.get('color', 'red'))
            )
        
        ax.axis('off')
        plt.tight_layout()
        
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = self.output_dir / f"annotated_{timestamp}.png"
        
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()
        
        return output_path
    
    def optimize_for_vision_llm(self,
                               image_path: Path,
                               test_name: Optional[str] = None,
                               circuit_type: Optional[str] = None,
                               specification: Optional[Dict[str, Any]] = None,
                               anomalies: Optional[List[str]] = None) -> Path:
        """
        Optimize waveform image for vision LLM analysis.
        
        Enhances image with:
        - Larger text annotations
        - Specification threshold overlays
        - Anomaly highlighting (red zones)
        - Test metadata in image
        - Increased contrast for vision model
        
        Args:
            image_path: Path to original waveform image
            test_name: Name of the test (for display)
            circuit_type: Circuit type (for display)
            specification: Dict with thresholds {metric: {min, max}}
            anomalies: List of detected anomalies to highlight
            
        Returns:
            Path to optimized image
        """
        from PIL import Image, ImageDraw, ImageFont
        import os
        
        logger.info(f"Optimizing image for vision LLM: {image_path}")
        
        try:
            # Open original image
            img = Image.open(image_path)
            
            # Ensure image is in RGB mode
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Get image dimensions
            width, height = img.size
            
            # Calculate new size (ensure optimal for vision models)
            # Vision models typically work well with 1024x768 or 1280x720
            max_width = 1280
            max_height = 720
            if width > max_width or height > max_height:
                ratio = min(max_width / width, max_height / height)
                new_size = (int(width * ratio), int(height * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                width, height = new_size
            
            # Increase contrast for better vision model interpretation
            from PIL import ImageEnhance
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.2)  # 20% contrast boost
            
            # Create copy for annotation
            img_annotated = img.copy()
            draw = ImageDraw.Draw(img_annotated)
            
            # Try to use a larger font, fall back if not available
            try:
                font_large = ImageFont.truetype("arial.ttf", int(height * 0.04))  # 4% of height
                font_small = ImageFont.truetype("arial.ttf", int(height * 0.025))  # 2.5% of height
            except:
                font_large = ImageFont.load_default()
                font_small = ImageFont.load_default()
            
            # Add metadata header
            margin = int(height * 0.02)
            y_offset = margin
            
            metadata_lines = []
            if test_name:
                metadata_lines.append(f"TEST: {test_name}")
            if circuit_type:
                metadata_lines.append(f"CIRCUIT: {circuit_type}")
            metadata_lines.append(f"TIMESTAMP: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Draw metadata header with semi-transparent background
            header_bg_height = len(metadata_lines) * int(height * 0.04) + 2 * margin
            draw.rectangle(
                [(0, 0), (width, header_bg_height)],
                fill=(240, 240, 240),  # Light gray background
                outline=(100, 100, 100)
            )
            
            # Draw metadata text
            for line in metadata_lines:
                draw.text((margin * 2, y_offset), line, fill=(0, 0, 0), font=font_small)
                y_offset += int(height * 0.04)
            
            # Add specification thresholds if provided
            if specification:
                spec_text = "SPEC: "
                for metric, bounds in specification.items():
                    if "min" in bounds and "max" in bounds:
                        spec_text += f"{metric}: [{bounds['min']}-{bounds['max']}]  "
                
                # Add specification box at bottom
                text_bbox = draw.textbbox((0, 0), spec_text, font=font_small)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
                
                y_spec = height - text_height - margin
                draw.rectangle(
                    [(margin, y_spec - margin), (width - margin, height - margin)],
                    fill=(255, 255, 220),  # Light yellow background
                    outline=(200, 200, 0)
                )
                draw.text((margin * 2, y_spec), spec_text, fill=(0, 0, 0), font=font_small)
            
            # Add anomaly indicators
            if anomalies:
                anomaly_text = "ANOMALIES: " + ", ".join(anomalies[:3])  # Show first 3
                if len(anomalies) > 3:
                    anomaly_text += f" +{len(anomalies)-3} more"
                
                text_bbox = draw.textbbox((0, 0), anomaly_text, font=font_small)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
                
                y_anom = height - (text_height * 3) - (margin * 4)
                draw.rectangle(
                    [(margin, y_anom - margin), (width - margin, y_anom + text_height + margin)],
                    fill=(255, 200, 200),  # Light red background
                    outline=(200, 0, 0)
                )
                draw.text((margin * 2, y_anom), anomaly_text, fill=(200, 0, 0), font=font_small)
            
            # Save optimized image
            optimized_path = image_path.parent / f"{image_path.stem}_optimized.png"
            img_annotated.save(optimized_path, quality=95, dpi=(150, 150))
            
            logger.info(f"Optimized image saved: {optimized_path} ({img_annotated.size})")
            return optimized_path
            
        except Exception as e:
            logger.warning(f"Failed to optimize image for vision LLM: {e}")
            logger.warning("Returning original image path")
            return image_path