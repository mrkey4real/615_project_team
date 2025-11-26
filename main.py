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

    Project Requirements:
    - Total IT Load: 1 GW (1000 MW)
    - 90% from liquid-cooled GPUs: 900 MW
    - 10% from air-cooled equipment: 100 MW
    - Chip cooling water: max 40°C
    - Air cooling: max 25°C
    """
    # ===== Total System Load =====
    Q_TOTAL_MW = 1000.0  # Total datacenter cooling load 总冷负荷

    # ===== Chip / GPU Parameters (90% of total) =====
    # Liquid-cooled GPUs: 900 MW
    N_GPUS = 2250  # Number of GPUs GPU数量 (2250 × 400kW = 900MW)
    P_GPU_W = 400000.0  # Power per GPU (W) 单个GPU功率 (400 kW each for high-power AI GPUs)
    Q_CHIP_MW = 900.0  # Total chip cooling load 芯片总冷负荷

    # Chip cooling loop temperatures 芯片冷却回路温度
    T_CHIP_IN_C = 30.0  # Chip inlet temp (from HX) 芯片入口温度
    T_CHIP_OUT_C = 40.0  # Chip outlet temp (to pump) 芯片出口温度 (max limit)

    # ===== Building Parameters (10% of total) =====
    # Air-cooled equipment: 100 MW
    Q_BUILDING_MW = 100.0  # Building/Air-cooled load 建筑/风冷负荷
    Q_BUILDING_W = 100e6  # Same in Watts 瓦特单位

    # Building heat exchanger 建筑热交换器
    HX_EFFECTIVENESS = 0.75  # Heat exchanger effectiveness 热交换器效能
    T_AIR_COOLED_MAX_C = 25.0  # Max air temperature for workers 最高空气温度
    T_AIR_AMBIENT_C = 22.0  # Ambient indoor air temp 室内环境温度

    # ===== Cooling System Parameters =====
    # Chiller 冷水机组
    T_CHW_SUPPLY_C = 7.0  # Chilled water supply temp 冷冻水供水温度
    DELTA_T_CHW_DESIGN_C = 5.0  # Design delta-T for CHW 冷冻水设计温差
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
    Run complete integrated system simulation following the project architecture:

    TWO INDEPENDENT WATER LOOPS 两个独立的水循环:

    1. CHILLED WATER LOOP (冷冻水循环):
       Chiller Evaporator → Building HXer → Compute HXer → Chiller Evaporator
           (7°C)               ↓(100MW)       ↓(900MW)         (12°C)
                          Air-Cooled      Liquid-Cooled
                          Equipment       GPU Chips

    2. CONDENSER WATER LOOP (冷却水循环):
       Chiller Condenser → Cooling Tower → Chiller Condenser
           (热)              (蒸发散热)         (冷)

    The Cooling Tower serves the chiller's condenser, NOT the chilled water loop.
    冷却塔为冷水机组的冷凝器服务，不直接与冷冻水循环交互。

    运行完整的集成系统仿真，按照项目架构流程
    """
    print("\n" + "=" * 100)
    print("1 GW AI数据中心冷却系统仿真 - 1 GW AI DATACENTER COOLING SYSTEM SIMULATION")
    print("Project: Modern Datacenter Building Cooling System Design")
    print("CHW Loop: Chiller Evap → Building HX → Compute HX → Chiller Evap")
    print("CW Loop:  Chiller Cond → Cooling Tower → Chiller Cond")
    print("=" * 100)

    params = SystemParameters()

    print(f"\n【系统设计参数 System Design Parameters】")
    print(f"  总IT负荷 Total IT Load:        {params.Q_TOTAL_MW:.0f} MW")
    print(f"  液冷芯片 Liquid-cooled GPUs:   {params.Q_CHIP_MW:.0f} MW (90%)")
    print(f"  风冷设备 Air-cooled Equipment: {params.Q_BUILDING_MW:.0f} MW (10%)")
    print(f"  GPU数量 Number of GPUs:        {params.N_GPUS:,} × {params.P_GPU_W/1000:.0f}kW")

    # ========================================================================
    # STEP 0: Calculate system-wide parameters
    # ========================================================================

    # Total cooling load
    Q_total_cooling_W = params.Q_CHIP_MW * 1e6 + params.Q_BUILDING_W

    # Chilled water flow rate based on total load and design delta-T
    # Q = m_dot × Cp × ΔT
    Cp_water = 4186.0  # J/(kg·K)
    m_dot_chw_kg_s = Q_total_cooling_W / (Cp_water * params.DELTA_T_CHW_DESIGN_C)
    t_chw_return_C = params.T_CHW_SUPPLY_C + params.DELTA_T_CHW_DESIGN_C

    print(f"\n【冷冻水系统参数 Chilled Water System】")
    print(f"  总冷负荷 Total Cooling Load:   {Q_total_cooling_W/1e6:.1f} MW")
    print(f"  流量 Flow Rate:                {m_dot_chw_kg_s:.0f} kg/s")
    print(f"  供水温度 Supply Temp:          {params.T_CHW_SUPPLY_C:.1f} °C")
    print(f"  回水温度 Return Temp:          {t_chw_return_C:.1f} °C")
    print(f"  温差 Delta-T:                  {params.DELTA_T_CHW_DESIGN_C:.1f} °C")

    # ========================================================================
    # STEP 1: Chiller - 冷水机组
    # ========================================================================
    print("\n" + "-" * 100)
    print("步骤 1: 冷水机组 - STEP 1: CHILLER (produces chilled water at 7°C)")
    print("-" * 100)

    # Initialize cooling system (Chiller + Tower + Pump)
    cooling_system = CoolingSystem(
        chiller_capacity_MW=Q_total_cooling_W / 1e6,
        chiller_cop=params.CHILLER_COP,
        t_chw_supply_C=params.T_CHW_SUPPLY_C,
        tower_approach_C=params.TOWER_APPROACH_C,
        tower_coc=params.TOWER_COC,
    )

    print(f"  冷水机容量 Chiller Capacity:   {Q_total_cooling_W/1e6:.1f} MW")
    print(f"  设计COP Design COP:            {params.CHILLER_COP:.1f}")

    # ========================================================================
    # STEP 2: Building Heat Exchanger - 建筑热交换器 (Air-Cooled Equipment)
    # ========================================================================
    print("\n" + "-" * 100)
    print("步骤 2: 建筑热交换器 - STEP 2: BUILDING HXer (Air-Cooled Equipment)")
    print("Water receives heat from air-cooled servers (100 MW)")
    print("-" * 100)

    # Building air-side parameters
    # Air-cooled equipment generates 100 MW of heat
    # Air circulates: absorbs heat from equipment → goes to HX → cools down → returns
    Cp_air = 1005.0  # J/(kg·K)
    T_air_cold_C = params.T_AIR_AMBIENT_C  # 22°C (air leaving HX, entering building)
    T_air_hot_C = params.T_AIR_COOLED_MAX_C  # 25°C (air leaving equipment, entering HX)

    # Air flow needed to absorb 100 MW with 3°C rise
    deltaT_air_C = T_air_hot_C - T_air_cold_C  # 3°C
    m_dot_air_kg_s = params.Q_BUILDING_W / (Cp_air * deltaT_air_C)

    # Building heat exchanger: hot air (25°C) exchanges heat with cold water (7°C)
    # Direct calculation: 100 MW from air to water
    T_water_after_building_C = params.T_CHW_SUPPLY_C + params.Q_BUILDING_W / (m_dot_chw_kg_s * Cp_water)
    Q_building_actual_W = params.Q_BUILDING_W  # By design: exactly 100 MW

    # Air outlet temperature from HX (cooled down)
    T_air_out_HX_C = T_air_hot_C - params.Q_BUILDING_W / (m_dot_air_kg_s * Cp_air)

    print(f"\n  建筑侧（空气）Building Side (Air):")
    print(f"    流量 Flow Rate:              {m_dot_air_kg_s:.1f} kg/s")
    print(f"    设备出口 Equipment Outlet:   {T_air_hot_C:.1f} °C (hot air from equipment)")
    print(f"    HX出口 HX Outlet:            {T_air_out_HX_C:.1f} °C (cooled air)")
    print(f"    温差 Delta-T:                {T_air_hot_C - T_air_out_HX_C:.1f} °C")

    print(f"\n  水侧 Water Side:")
    print(f"    流量 Flow Rate:              {m_dot_chw_kg_s:.0f} kg/s")
    print(f"    入口温度 Inlet Temp:         {params.T_CHW_SUPPLY_C:.1f} °C (from chiller)")
    print(f"    出口温度 Outlet Temp:        {T_water_after_building_C:.2f} °C")
    print(f"    温升 Temp Rise:              {T_water_after_building_C - params.T_CHW_SUPPLY_C:.2f} °C")

    print(f"\n  热交换 Heat Transfer:")
    print(f"    传热量 Heat Transfer:        {Q_building_actual_W/1e6:.1f} MW")
    print(f"    设计负荷 Design Load:        {params.Q_BUILDING_MW:.1f} MW")

    # ========================================================================
    # STEP 3: Compute Heat Exchanger - 计算热交换器 (Liquid-Cooled Chips)
    # ========================================================================
    print("\n" + "-" * 100)
    print("步骤 3: 计算热交换器 - STEP 3: COMPUTE HXer (Liquid-Cooled GPU Chips)")
    print("Water receives heat from chip cooling loop (900 MW)")
    print("-" * 100)

    # Chip cooling system receives water from Building HX outlet
    # T_bin is now the water temperature after Building HX
    chip_result = compute_selected_with_branches_and_hx(
        N=params.N_GPUS,
        P_gpu=params.P_GPU_W,                # Power per GPU in W
        m_b=m_dot_chw_kg_s,                  # Building (water) loop flow
        T_bin=T_water_after_building_C,      # Water inlet from Building HX
        T1=params.T_CHIP_IN_C,               # Chip loop inlet: 30°C
        T2=params.T_CHIP_OUT_C,              # Chip loop outlet: 40°C (max)
        rho=997.0,
        gpus_per_branch=225,                 # 2250 GPUs / 225 per branch = 10 branches
        epsilon=0.90,                         # Chip HX effectiveness
        # Larger pipe diameters for lower pressure drop (optimized for 900 MW system)
        D1=0.20,  # Rack pipe: 200mm
        D2=1.00,  # Branch pipe: 1000mm (1m)
        D3=3.00,  # Header pipe: 3000mm (3m)
    )

    T_water_after_compute_C = chip_result['T_to_tower_C']
    Q_chip_actual_W = chip_result['Q_through_HX_W']

    print(f"\n  芯片侧（液冷回路）Chip Side (Liquid Loop):")
    print(f"    GPU数量 Number of GPUs:      {params.N_GPUS:,}")
    print(f"    芯片总功率 Total Power:      {chip_result['Q_chip_W']/1e6:.1f} MW")
    print(f"    芯片流量 Flow Rate:          {chip_result['m_chip_kg_s']:.0f} kg/s")
    print(f"    入口温度 Inlet Temp:         {params.T_CHIP_IN_C:.1f} °C")
    print(f"    出口温度 Outlet Temp:        {params.T_CHIP_OUT_C:.1f} °C (max limit)")
    print(f"    泵功率 Pump Power:           {chip_result['W_pump_W']/1e6:.3f} MW")

    print(f"\n  水侧（建筑回路）Water Side (Building Loop):")
    print(f"    流量 Flow Rate:              {m_dot_chw_kg_s:.0f} kg/s")
    print(f"    入口温度 Inlet Temp:         {T_water_after_building_C:.2f} °C (from Building HX)")
    print(f"    出口温度 Outlet Temp:        {T_water_after_compute_C:.2f} °C")
    print(f"    温升 Temp Rise:              {T_water_after_compute_C - T_water_after_building_C:.2f} °C")

    print(f"\n  热交换 Heat Transfer:")
    print(f"    通过HX的热量 Heat via HX:    {Q_chip_actual_W/1e6:.1f} MW")
    print(f"    设计负荷 Design Load:        {params.Q_CHIP_MW:.1f} MW")
    print(f"    HX效率 HX Effectiveness:     {0.90:.0%}")

    # ========================================================================
    # STEP 4: Complete Cooling System Solve - 完整冷却系统求解
    # ========================================================================
    print("\n" + "-" * 100)
    print("步骤 4: 完整冷却系统 - STEP 4: COMPLETE COOLING SYSTEM")
    print("Solve Chiller (evaporator + condenser) + Cooling Tower system")
    print("-" * 100)

    # Actual return temperature from the complete cascade
    t_chw_return_actual_C = T_water_after_compute_C

    print(f"\n  冷冻水循环 Chilled Water Loop:")
    print(f"    供水温度 Supply Temp:        {params.T_CHW_SUPPLY_C:.1f} °C (from evaporator)")
    print(f"    回水温度 Return Temp:        {t_chw_return_actual_C:.2f} °C (to evaporator)")
    print(f"    温升 Total Rise:             {t_chw_return_actual_C - params.T_CHW_SUPPLY_C:.2f} °C")

    # Solve complete cooling system
    # This includes:
    # - Chiller evaporator (produces 7°C CHW)
    # - Chiller condenser (rejects heat to condenser water)
    # - Cooling tower (cools condenser water via evaporation)
    print(f"\n  求解完整系统 Solving Complete System (Chiller + Cooling Tower)...")
    cooling_result = cooling_system.solve(
        q_cooling_load_W=Q_total_cooling_W,
        m_dot_chw_kg_s=m_dot_chw_kg_s,
        t_chw_return_C=t_chw_return_actual_C,
        t_wb_ambient_C=params.T_WB_AMBIENT_C,
        t_db_ambient_C=params.T_DB_AMBIENT_C,
    )

    # ========================================================================
    # STEP 5: Results Summary - 结果汇总
    # ========================================================================
    print("\n" + "=" * 100)
    print("系统结果汇总 - SYSTEM RESULTS SUMMARY")
    print("=" * 100)

    # Extract results
    ds = cooling_result["downstream_interface"]
    internal = cooling_result["internal_states"]
    ch = internal["chiller"]
    ct = internal["cooling_tower"]

    print(f"\n【水温度级联 Water Temperature Cascade】")
    print(f"  ① Chiller出口 Chiller Outlet:  {params.T_CHW_SUPPLY_C:.1f} °C")
    print(f"  ② Building HX出 Building Out:  {T_water_after_building_C:.2f} °C  (温升 +{T_water_after_building_C - params.T_CHW_SUPPLY_C:.2f}°C)")
    print(f"  ③ Compute HX出 Compute Out:    {T_water_after_compute_C:.2f} °C  (温升 +{T_water_after_compute_C - T_water_after_building_C:.2f}°C)")
    print(f"  ④ 总温升 Total Rise:            {T_water_after_compute_C - params.T_CHW_SUPPLY_C:.2f} °C")
    print(f"  ⑤ 回到Chiller Return to Chill: {T_water_after_compute_C:.2f} °C")

    print(f"\n【能量平衡 Energy Balance】")
    total_heat_absorbed_MW = (Q_building_actual_W + Q_chip_actual_W) / 1e6
    print(f"  建筑HX吸热 Building HX:        {Q_building_actual_W/1e6:.1f} MW")
    print(f"  芯片HX吸热 Compute HX:         {Q_chip_actual_W/1e6:.1f} MW")
    print(f"  总吸热 Total Heat Absorbed:    {total_heat_absorbed_MW:.1f} MW")
    print(f"  设计冷负荷 Design Load:        {Q_total_cooling_W/1e6:.1f} MW")
    print(f"  能量平衡误差 Balance Error:    {abs(total_heat_absorbed_MW - Q_total_cooling_W/1e6):.2f} MW")

    print(f"\n【冷却系统性能 Cooling System Performance】")
    print(f"  冷量 Cooling Capacity:         {ds['Q_cooling_MW']:.1f} MW")
    print(f"  系统COP System COP:            {ds['system_COP']:.2f}")
    print(f"  冷却系统总功率 Total Power:    {ds['total_power_MW']:.1f} MW")

    print(f"\n【冷水机组 Chiller】")
    print(f"  蒸发器冷量 Q_evap:             {ch['Q_evap_MW']:.1f} MW")
    print(f"  压缩机功率 W_comp:             {ch['W_comp_MW']:.1f} MW")
    print(f"  冷凝器热量 Q_cond:             {ch['Q_cond_MW']:.1f} MW")
    print(f"  COP:                           {ch['COP']:.2f}")
    print(f"  制冷剂 Refrigerant:            {ch['refrigerant']}")

    print(f"\n【冷却塔 Cooling Tower】")
    print(f"  热量排放 Heat Rejected:        {ct['Q_rejected_MW']:.1f} MW")
    print(f"  风机功率 Fan Power:            {ct['W_fan_MW']:.1f} MW")
    print(f"  蒸发损失 Evaporation Loss:     {ct['m_evap_kg_s']:.2f} kg/s")
    print(f"  补水量 Water Makeup:           {ct['m_makeup_L_hr']:,.0f} L/hr  ({ct['m_makeup_kg_s']:.2f} kg/s)")
    print(f"  浓缩倍数 COC:                  {ct['COC']:.1f}")

    print(f"\n【建筑冷却 Building Cooling (Air-Cooled Equipment)】")
    print(f"  冷负荷 Cooling Load:           {Q_building_actual_W/1e6:.1f} MW")
    print(f"  空气流量 Air Flow:             {m_dot_air_kg_s:.1f} kg/s")
    print(f"  空气温度 Air Temp:             {T_air_cold_C:.1f} → {T_air_hot_C:.1f} °C (equipment heating)")

    print(f"\n【芯片冷却 Chip Cooling (Liquid-Cooled GPUs)】")
    print(f"  GPU数量 Number of GPUs:        {params.N_GPUS:,}")
    print(f"  芯片总功率 Total Power:        {chip_result['Q_chip_W']/1e6:.1f} MW")
    print(f"  芯片泵功率 Pump Power:         {chip_result['W_pump_W']/1e6:.3f} MW")
    print(f"  芯片流量 Chip Flow:            {chip_result['m_chip_kg_s']:.0f} kg/s")
    print(f"  芯片温度 Chip Temp:            {params.T_CHIP_IN_C:.1f} → {params.T_CHIP_OUT_C:.1f} °C")

    # Overall System Metrics
    total_IT_power_MW = params.Q_TOTAL_MW  # 1000 MW total IT load
    total_cooling_power_MW = ds['total_power_MW'] + chip_result['W_pump_W']/1e6
    pue = (total_IT_power_MW + total_cooling_power_MW) / total_IT_power_MW

    print(f"\n" + "=" * 100)
    print("【关键性能指标 KEY PERFORMANCE INDICATORS】")
    print("=" * 100)

    print(f"\n  IT功率 IT Power:               {total_IT_power_MW:.1f} MW")
    print(f"    - 液冷GPU Liquid-cooled:     {params.Q_CHIP_MW:.1f} MW (90%)")
    print(f"    - 风冷设备 Air-cooled:       {params.Q_BUILDING_MW:.1f} MW (10%)")

    print(f"\n  冷却功率 Cooling Power:        {total_cooling_power_MW:.1f} MW")
    print(f"    - 冷水机组 Chiller:          {ch['W_comp_MW']:.1f} MW")
    print(f"    - 冷却塔 Cooling Tower:      {ct['W_fan_MW']:.1f} MW")
    print(f"    - 冷冻水泵 CHW Pumps:        {internal['pump']['P_pump_W']/1e6:.2f} MW")
    print(f"    - 芯片泵 Chip Pumps:         {chip_result['W_pump_W']/1e6:.3f} MW")

    print(f"\n  ★ PUE (Power Usage Effectiveness):")
    print(f"    PUE = (IT + Cooling) / IT")
    print(f"        = ({total_IT_power_MW:.1f} + {total_cooling_power_MW:.1f}) / {total_IT_power_MW:.1f}")
    print(f"        = {pue:.3f}")
    print(f"    行业标准 Industry Standard: 1.2-1.5 (good), <1.2 (excellent)")

    # Water usage
    annual_water_m3 = ct['m_makeup_kg_s'] * 3600 * 8760 / 1000  # kg/s → m³/year
    annual_it_kwh = total_IT_power_MW * 1000 * 8760  # MW → kWh/year
    wue = annual_water_m3 * 1000 / annual_it_kwh  # L/kWh

    print(f"\n  ★ WUE (Water Usage Effectiveness):")
    print(f"    年补水量 Annual Makeup:      {annual_water_m3:,.0f} m³/year")
    print(f"    年IT能耗 Annual IT Energy:   {annual_it_kwh/1e6:,.1f} million kWh")
    print(f"    WUE = {annual_water_m3:,.0f} m³ × 1000 / {annual_it_kwh/1e6:,.1f}M kWh")
    print(f"        = {wue:.3f} L/kWh")
    print(f"    行业标准 Industry Standard: <1.8 L/kWh (good), <1.0 L/kWh (excellent)")

    print(f"\n  社会影响 Societal Impact:")
    print(f"    水消耗 Water Consumption:    {annual_water_m3:,.0f} m³/year")
    print(f"      等同于 Equivalent to:      {annual_water_m3/365:,.0f} m³/day")
    print(f"      约 Approximately:          {annual_water_m3*264.172/1e6:.1f} million gallons/year")
    print(f"    能耗 Energy Consumption:     {total_cooling_power_MW/total_IT_power_MW*100:.1f}% overhead")

    print("\n" + "=" * 100)
    print("仿真完成 - SIMULATION COMPLETE")
    print("=" * 100 + "\n")

    return {
        "cooling_system": cooling_result,
        "chip_cooling": chip_result,
        "building_cooling": {
            "Q_absorbed_W": Q_building_actual_W,
            "T_water_out_C": T_water_after_building_C,
        },
        "water_cascade": {
            "T_chiller_out_C": params.T_CHW_SUPPLY_C,
            "T_after_building_C": T_water_after_building_C,
            "T_after_compute_C": T_water_after_compute_C,
        },
        "pue": pue,
        "wue": wue,
        "total_it_power_MW": total_IT_power_MW,
        "total_cooling_power_MW": total_cooling_power_MW,
        "annual_water_m3": annual_water_m3,
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
