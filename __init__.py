"""
Components:
- Chiller: Full vapor compression refrigeration cycle
- CoolingTower: Psychrometric analysis with mass/energy balances
- Pump: Fluid dynamics based pump calculations
- HVACSystem: Integrated system solver

Usage:
    from hvac_components import HVACSystem

    hvac = HVACSystem()
    results = hvac.solve(q_evap=1000e6, t_chw_return=15.0, ...)

Author: Zixuan
Date: 2025-11-10
Version: 1.0
"""

from .chiller import Chiller
from .cooling_tower import CoolingTower, CoolingTowerOptimized
from .pump import Pump, PumpSystem
from .run_hvac import HVACSystem

__all__ = [
    'Chiller',
    'CoolingTower',
    'CoolingTowerOptimized',
    'Pump',
    'PumpSystem',
    'HVACSystem',
]

__version__ = '1.0.0'
__author__ = 'Zixuan'
