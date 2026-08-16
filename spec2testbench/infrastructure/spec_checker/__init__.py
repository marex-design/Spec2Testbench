# spec2testbench/infrastructure/spec_checker/__init__.py

"""
Module SpecChecker - Vérification automatique des spécifications.
"""

from .spec_checker import SpecChecker
from .metric_extractor import MetricExtractor

__all__ = [
    'SpecChecker',
    'MetricExtractor',
]