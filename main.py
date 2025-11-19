"""
Main Program - 完整系统集成
Complete System Integration

This is the main entry point that integrates all three major components:
这是集成所有三大组件的主程序入口：

1. Cooling System (cooling_system.py) - 冷却系统
   - Chiller 冷水机组
   - Cooling Tower 冷却塔
   - Pump 泵

2. Building (Building and HeatEX.py) - 建筑系统
   - Building Heat Exchanger 建筑热交换器
   - Air-Cooled Equipment 风冷设备

3. Chip Cooling (CHIPCOOLING.py) - 芯片冷却系统
   - GPU Chip Cooling 显卡芯片冷却
   - Heat Exchanger 热交换器

System Flow 系统流程:
Cooling System → Building HX → Chip HX → GPU Heat Generation
冷却系统 → 建筑热交换器 → 芯片热交换器 → GPU发热

Author: HVAC Team
Date: 2025-11-19
"""

# ============================================================================
# Imports - 导入模块
# ============================================================================

# Cooling System 冷却系统
from cooling_system import CoolingSystem

# Building System 建筑系统
import importlib.util
import sys

# Load Building module (handle space in filename)
spec = importlib.util.spec_from_file_location("building_module", "Building and HeatEX.py")
building_module = importlib.util.module_from_spec(spec)
sys.modules["building_module"] = building_module
spec.loader.exec_module(building_module)

BuildingHeatExchanger = building_module.BuildingHeatExchanger
AirCooledComponent = building_module.AirCooledComponent
Pump = building_module.Pump

# Chip Cooling System 芯片冷却系统
from CHIPCOOLING import compute_selected_with_branches_and_hx, print_results


# ============================================================================
# System Parameters - 系统参数
# ============================================================================

class SystemParameters:
    """
    Complete system parameters.
    完整系统参数
    """
    # ===== Chip / GPU Parameters =====
    N_GPUS = 8000  # Number of GPUs GPU数量
    P_GPU_W = 400.0  # Power per GPU (W) 单个GPU功率

    # Chip cooling loop temperatures 芯片冷却回路温度
    T_CHIP_IN_C = 30.0  # Chip inlet temp (from HX) 芯片入口温度
    T_CHIP_OUT_C = 40.0  # Chip outlet temp (to pump) 芯片出口温度

    # ===== Building Parameters =====
    # Building cooling load (additional to chips) 建筑冷负荷(除芯片外)
    Q_BUILDING_W = 100e6  # 100 MW building load 建筑负荷

    # Building heat exchanger 建筑热交换器
    HX_EFFECTIVENESS = 0.75  # Heat exchanger effectiveness 热交换器效能

    # ===== Cooling System Parameters =====
    # Chiller 冷水机组
    T_CHW_SUPPLY_C = 7.0  # Chilled water supply temp 冷冻水供水温度
    CHILLER_COP = 6.0  # Chiller COP 冷水机组能效比

    # Cooling tower 冷却塔
    TOWER_APPROACH_C = 4.0  # Approach temperature 接近温度
    TOWER_COC = 4.0  # Cycles of concentration 浓缩倍数

    # ===== Ambient Conditions =====
    T_WB_AMBIENT_C = 24.0  # Wet bulb temperature 湿球温度
    T_DB_AMBIENT_C = 35.0  # Dry bulb temperature 干球温度


# ============================================================================
# Main System Simulation - 主系统仿真
# ============================================================================

def run_complete_system():
    """
    Run complete integrated system simulation.
    运行完整的集成系统仿真
    """
    print("\n" + "=" * 100)
    print("完整系统仿真 - COMPLETE SYSTEM SIMULATION")
    print("三大组件集成：冷却系统 + 建筑 + 芯片冷却")
    print("Three Major Components: Cooling System + Building + Chip Cooling")
    print("=" * 100)

    params = SystemParameters()

    # ========================================================================
    # STEP 1: Chip Cooling System - 芯片冷却系统
    # ========================================================================
    print("\n" + "-" * 100)
    print("步骤 1: 芯片冷却系统 - STEP 1: CHIP COOLING SYSTEM")
    print("-" * 100)

    # Total GPU heat load
    Q_chip_total_W = params.N_GPUS * params.P_GPU_W
    print(f"\nGPU数量 Number of GPUs: {params.N_GPUS}")
    print(f"单GPU功率 Power per GPU: {params.P_GPU_W} W")
    print(f"芯片总热负荷 Total Chip Heat: {Q_chip_total_W/1e6:.1f} MW")

    # Building side flow rate (estimated based on total load)
    # 建筑侧流量（基于总负荷估算）
    Q_total_estimate_W = Q_chip_total_W + params.Q_BUILDING_W
    m_b_kg_s = Q_total_estimate_W / (4186.0 * 5.0)  # Assume 5°C deltaT

    print(f"\n建筑侧流量估算 Building flow estimate: {m_b_kg_s:.0f} kg/s")
    print(f"建筑侧入口温度 Building inlet temp: {params.T_CHW_SUPPLY_C:.1f} °C")

    # Solve chip cooling system
    chip_result = compute_selected_with_branches_and_hx(
        N=params.N_GPUS,
        P_gpu=params.P_GPU_W,
        m_b=m_b_kg_s,
        T_bin=params.T_CHW_SUPPLY_C,
        T1=params.T_CHIP_IN_C,
        T2=params.T_CHIP_OUT_C,
        rho=997.0,
        # Use defaults for hydraulic parameters
        gpus_per_branch=100,
        epsilon=0.90,  # Heat exchanger effectiveness
    )

    print(f"\n芯片冷却结果 Chip Cooling Results:")
    print(f"  芯片热负荷 Chip Heat:          {chip_result['Q_chip_W']/1e6:.1f} MW")
    print(f"  通过HX的热量 Heat via HX:       {chip_result['Q_through_HX_W']/1e6:.1f} MW")
    print(f"  芯片侧流量 Chip flow:          {chip_result['m_chip_kg_s']:.0f} kg/s")
    print(f"  泵功率 Pump power:             {chip_result['W_pump_W']/1e6:.3f} MW")
    print(f"  去冷却塔温度 To tower temp:     {chip_result['T_to_tower_C']:.2f} °C")

    # ========================================================================
    # STEP 2: Building Heat Exchanger - 建筑热交换器
    # ========================================================================
    print("\n" + "-" * 100)
    print("步骤 2: 建筑热交换器 - STEP 2: BUILDING HEAT EXCHANGER")
    print("-" * 100)

    # Total cooling load = Chip + Building
    Q_total_cooling_W = chip_result['Q_through_HX_W'] + params.Q_BUILDING_W

    print(f"\n总冷负荷 Total Cooling Load:")
    print(f"  芯片冷却 Chip cooling:        {chip_result['Q_through_HX_W']/1e6:.1f} MW")
    print(f"  建筑冷却 Building cooling:    {params.Q_BUILDING_W/1e6:.1f} MW")
    print(f"  总计 Total:                   {Q_total_cooling_W/1e6:.1f} MW")

    # Calculate chilled water flow rate based on total load
    # deltaT_chw = 5°C (typical)
    deltaT_chw_design_C = 5.0
    m_dot_chw_kg_s = Q_total_cooling_W / (4186.0 * deltaT_chw_design_C)
    t_chw_return_C = params.T_CHW_SUPPLY_C + deltaT_chw_design_C

    print(f"\n冷冻水参数 Chilled Water Parameters:")
    print(f"  供水温度 Supply temp:          {params.T_CHW_SUPPLY_C:.1f} °C")
    print(f"  回水温度 Return temp:          {t_chw_return_C:.1f} °C")
    print(f"  温差 Delta-T:                 {deltaT_chw_design_C:.1f} °C")
    print(f"  流量 Flow rate:               {m_dot_chw_kg_s:.0f} kg/s")

    # ========================================================================
    # STEP 3: Cooling System (Chiller + Tower + Pump) - 冷却系统
    # ========================================================================
    print("\n" + "-" * 100)
    print("步骤 3: 冷却系统 - STEP 3: COOLING SYSTEM (Chiller + Tower + Pump)")
    print("-" * 100)

    # Initialize cooling system
    cooling_system = CoolingSystem(
        chiller_capacity_MW=Q_total_cooling_W / 1e6,  # Size to load
        chiller_cop=params.CHILLER_COP,
        t_chw_supply_C=params.T_CHW_SUPPLY_C,
        tower_approach_C=params.TOWER_APPROACH_C,
        tower_coc=params.TOWER_COC,
    )

    print(f"\n冷却系统配置 Cooling System Configuration:")
    print(f"  冷水机容量 Chiller capacity:    {Q_total_cooling_W/1e6:.1f} MW")
    print(f"  设计COP Design COP:            {params.CHILLER_COP:.1f}")
    print(f"  冷却塔接近温度 Tower approach:  {params.TOWER_APPROACH_C:.1f} °C")
    print(f"  浓缩倍数 COC:                  {params.TOWER_COC:.1f}")

    # Solve cooling system
    print(f"\n求解冷却系统 Solving cooling system...")
    cooling_result = cooling_system.solve(
        q_cooling_load_W=Q_total_cooling_W,
        m_dot_chw_kg_s=m_dot_chw_kg_s,
        t_chw_return_C=t_chw_return_C,
        t_wb_ambient_C=params.T_WB_AMBIENT_C,
        t_db_ambient_C=params.T_DB_AMBIENT_C,
    )

    # ========================================================================
    # STEP 4: Results Summary - 结果汇总
    # ========================================================================
    print("\n" + "=" * 100)
    print("系统结果汇总 - SYSTEM RESULTS SUMMARY")
    print("=" * 100)

    # Cooling System Performance
    ds = cooling_result["downstream_interface"]
    internal = cooling_result["internal_states"]

    print(f"\n【冷却系统性能 Cooling System Performance】")
    print(f"  供水温度 CHW Supply:           {ds['T_chw_supply_C']:.1f} °C")
    print(f"  回水温度 CHW Return:           {ds['T_chw_return_C']:.1f} °C")
    print(f"  流量 Flow Rate:                {ds['m_dot_chw_kg_s']:.0f} kg/s")
    print(f"  冷量 Cooling Capacity:         {ds['Q_cooling_MW']:.1f} MW")
    print(f"  系统COP System COP:            {ds['system_COP']:.2f}")
    print(f"  总功率 Total Power:            {ds['total_power_MW']:.1f} MW")

    # Chiller
    ch = internal["chiller"]
    print(f"\n【冷水机组 Chiller】")
    print(f"  蒸发器冷量 Q_evap:             {ch['Q_evap_MW']:.1f} MW")
    print(f"  压缩机功率 W_comp:             {ch['W_comp_MW']:.1f} MW")
    print(f"  冷凝器热量 Q_cond:             {ch['Q_cond_MW']:.1f} MW")
    print(f"  COP:                           {ch['COP']:.2f}")
    print(f"  制冷剂 Refrigerant:            {ch['refrigerant']}")

    # Cooling Tower
    ct = internal["cooling_tower"]
    print(f"\n【冷却塔 Cooling Tower】")
    print(f"  热量排放 Heat Rejected:        {ct['Q_rejected_MW']:.1f} MW")
    print(f"  风机功率 Fan Power:            {ct['W_fan_MW']:.1f} MW")
    print(f"  补水量 Water Makeup:           {ct['m_makeup_L_hr']:,.0f} L/hr")
    print(f"  浓缩倍数 COC:                  {ct['COC']:.1f}")

    # Chip Cooling
    print(f"\n【芯片冷却 Chip Cooling】")
    print(f"  GPU数量 Number of GPUs:        {params.N_GPUS:,}")
    print(f"  芯片总热负荷 Total Heat:       {chip_result['Q_chip_W']/1e6:.1f} MW")
    print(f"  芯片泵功率 Pump Power:         {chip_result['W_pump_W']/1e6:.3f} MW")
    print(f"  芯片流量 Chip Flow:            {chip_result['m_chip_kg_s']:.0f} kg/s")

    # Overall System
    total_IT_power_MW = chip_result['Q_chip_W'] / 1e6
    total_cooling_power_MW = ds['total_power_MW'] + chip_result['W_pump_W']/1e6
    pue = (total_IT_power_MW + total_cooling_power_MW) / total_IT_power_MW

    print(f"\n【系统总计 Overall System】")
    print(f"  IT功率 IT Power:               {total_IT_power_MW:.1f} MW")
    print(f"  冷却功率 Cooling Power:        {total_cooling_power_MW:.1f} MW")
    print(f"    - 冷水机组 Chiller:          {ch['W_comp_MW']:.1f} MW")
    print(f"    - 冷却塔 Cooling Tower:      {ct['W_fan_MW']:.1f} MW")
    print(f"    - 泵 Pumps:                  {(internal['pump']['P_pump_W']/1e6 + chip_result['W_pump_W']/1e6):.2f} MW")
    print(f"  PUE:                           {pue:.3f}")

    # Water usage
    annual_water_m3 = ct['m_makeup_kg_s'] * 3600 * 8760 / 1000
    annual_it_kwh = total_IT_power_MW * 1000 * 8760
    wue = annual_water_m3 * 1000 / annual_it_kwh

    print(f"\n【用水效率 Water Usage】")
    print(f"  年补水量 Annual Makeup:        {annual_water_m3:,.0f} m³/year")
    print(f"  WUE:                           {wue:.3f} L/kWh")

    print("\n" + "=" * 100)
    print("仿真完成 - SIMULATION COMPLETE")
    print("=" * 100 + "\n")

    return {
        "cooling_system": cooling_result,
        "chip_cooling": chip_result,
        "pue": pue,
        "wue": wue,
        "total_it_power_MW": total_IT_power_MW,
        "total_cooling_power_MW": total_cooling_power_MW,
    }


# ============================================================================
# Entry Point - 程序入口
# ============================================================================

if __name__ == "__main__":
    """
    Main entry point for complete system simulation.
    完整系统仿真的主入口
    """
    try:
        results = run_complete_system()

        print("\n✓ 系统仿真成功完成 System simulation completed successfully!")
        print(f"  PUE: {results['pue']:.3f}")
        print(f"  WUE: {results['wue']:.3f} L/kWh")

    except Exception as e:
        print(f"\n✗ 错误 Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
