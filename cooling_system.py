"""
HVAC集成冷却系统

这个模块作为统一入口，提供所有HVAC组件的访问。

包含的组件：
- Psychrometrics: 湿空气热力学计算
- Refrigerant Cycle: 制冷循环建模
- Chiller: 冷水机
- Cooling Tower: 冷却塔
- Pump: 泵系统
- IntegratedHVACSystem: 完整HVAC系统

使用方法：
    from cooling_system import IntegratedHVACSystem

    system = IntegratedHVACSystem(...)
    results = system.solve()

作者：HVAC Team
日期：2025-11-19
版本：v1.2 - 简化模块结构
"""

# 导入所有核心组件
from psychrometrics import MoistAir, PsychrometricState
from refrigerant_cycle import (
    COOLPROP_AVAILABLE,
    RefrigerantState,
    VaporCompressionCycle,
    HeatExchanger,
)
from chiller import Chiller
from cooling_tower import CoolingTower
from pump import Pump, PumpSystem
from hvac_integrated import IntegratedHVACSystem, to_jsonable

__all__ = [
    # Psychrometrics
    'MoistAir',
    'PsychrometricState',
    # Refrigerant Cycle
    'COOLPROP_AVAILABLE',
    'RefrigerantState',
    'VaporCompressionCycle',
    'HeatExchanger',
    # Chiller
    'Chiller',
    # Cooling Tower
    'CoolingTower',
    # Pump
    'Pump',
    'PumpSystem',
    # Integrated HVAC
    'IntegratedHVACSystem',
    'to_jsonable',
]

__version__ = '1.2'
__author__ = 'HVAC Team'


def get_system_info():
    """获取系统信息"""
    return {
        'version': __version__,
        'author': __author__,
        'coolprop_available': COOLPROP_AVAILABLE,
        'components': {
            'psychrometrics': '湿空气热力学',
            'refrigerant_cycle': '制冷循环',
            'chiller': '冷水机',
            'cooling_tower': '冷却塔',
            'pump': '泵系统',
            'hvac_integrated': '完整HVAC系统',
        }
    }


if __name__ == "__main__":
    print("=" * 80)
    print("HVAC集成冷却系统")
    print("=" * 80)

    info = get_system_info()
    print(f"\n版本: {info['version']}")
    print(f"作者: {info['author']}")
    print(f"CoolProp 可用: {info['coolprop_available']}")

    print("\n包含的组件：")
    for key, value in info['components'].items():
        print(f"  - {key}: {value}")

    print("\n使用方法：")
    print("  from cooling_system import IntegratedHVACSystem")
    print("  system = IntegratedHVACSystem(...)")
    print("  results = system.solve()")

    print("\n或运行示例：")
    print("  python main.py")
    print("=" * 80)
