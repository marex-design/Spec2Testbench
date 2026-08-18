"""
Module Simulator - Interface avec ngspice via WSL.
"""

from .wsl_simulator import WSLSimulator, NgspiceSimulator

# Alias pour compatibilité avec le code existant
PySpiceSimulator = WSLSimulator

__all__ = [
    'WSLSimulator',
    'NgspiceSimulator', 
    'PySpiceSimulator'
]
