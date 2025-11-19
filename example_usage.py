"""
Example Usage of Refactored HVAC System

This script demonstrates how to use the refactored HVAC system with:
1. Simplified CoolingSystem (integrated chiller + cooling tower)
2. Clear separation of downstream interface vs internal diagnostics
3. Easy integration with heat exchanger / building

Author: HVAC Team
Date: 2025-11-19
"""

from hvac_integrated import IntegratedHVACSystem
from cooling_system import CoolingSystem
import json


def example_1_cooling_system_standalone():
    """
    Example 1: Using CoolingSystem standalone

    This shows how to use the integrated chiller + cooling tower
    without the full HVAC system.
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 1: CoolingSystem Standalone Usage")
    print("=" * 80)

    # Create cooling system
    cooling_sys = CoolingSystem(
        chiller_capacity_MW=100.0,  # 100 MW
        chiller_cop=6.0,
        t_chw_supply_C=7.0,
        tower_approach_C=4.0,
        tower_coc=4.0,
    )

    # Solve for given conditions
    result = cooling_sys.solve(
        q_cooling_load_W=100e6,  # 100 MW load
        m_dot_chw_kg_s=4777,     # CHW flow rate
        t_chw_return_C=12.0,     # CHW return temp
        t_wb_ambient_C=24.0,     # Ambient wet bulb
        t_db_ambient_C=35.0,     # Ambient dry bulb
    )

    # Access downstream interface (what heat exchanger needs)
    print("\n--- Downstream Interface (for Heat Exchanger) ---")
    ds = result["downstream_interface"]
    print(f"CHW Supply:            {ds['T_chw_supply_C']:.2f} °C")
    print(f"CHW Return:            {ds['T_chw_return_C']:.2f} °C")
    print(f"CHW Flow:              {ds['m_dot_chw_kg_s']:.0f} kg/s")
    print(f"Cooling Capacity:      {ds['Q_cooling_MW']:.1f} MW")
    print(f"System COP:            {ds['system_COP']:.2f}")
    print(f"Total Power:           {ds['total_power_MW']:.1f} MW")

    # Access internal states (for monitoring/debugging)
    print("\n--- Internal States (for Monitoring) ---")
    internal = result["internal_states"]
    print(f"Converged:             {internal['convergence']['converged']}")
    print(f"Iterations:            {internal['convergence']['iterations']}")
    print(f"Chiller COP:           {internal['chiller']['COP']:.2f}")
    print(f"Compressor Power:      {internal['chiller']['W_comp_MW']:.1f} MW")
    print(f"Tower Fan Power:       {internal['cooling_tower']['W_fan_MW']:.2f} MW")
    print(f"Water Makeup:          {internal['cooling_tower']['m_makeup_L_hr']:,.0f} L/hr")


def example_2_full_hvac_system():
    """
    Example 2: Using Full Integrated HVAC System

    This shows how to use the complete system including air loop,
    building heat exchanger, and cooling system.
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 2: Full Integrated HVAC System")
    print("=" * 80)

    # Create integrated system
    hvac = IntegratedHVACSystem(
        pump_power_W=250_000.0,
        air_delta_p_Pa=900.0,
        air_eta=0.65,
        t_air_in_C=20.0,
        q_air_load_W=100e6,
        t_air_max_C=25.0,
        t_chw_supply_C=7.0,
        deltaT_chw_design_C=5.0,
        hx_effectiveness=0.80,
        t_wb_C=24.0,
        t_db_C=35.0,
        chiller_cop=6.0,
    )

    # Solve system
    results = hvac.solve()

    # For downstream (Building / Heat Exchanger):
    # Use this interface to connect to your building model
    print("\n--- For Heat Exchanger (Downstream Interface) ---")
    hx_interface = results["for_heat_exchanger"]
    print(f"Component:             {hx_interface['component']}")
    print(f"CHW Supply:            {hx_interface['T_chw_supply_C']:.2f} °C")
    print(f"CHW Return:            {hx_interface['T_chw_return_C']:.2f} °C")
    print(f"CHW Flow:              {hx_interface['m_dot_chw_kg_s']:.0f} kg/s")
    print(f"CHW Delta-T:           {hx_interface['deltaT_chw_C']:.2f} °C")
    print(f"Cooling Capacity:      {hx_interface['Q_cooling_MW']:.1f} MW")
    print(f"System COP:            {hx_interface['system_COP']:.2f}")
    print(f"Total Power:           {hx_interface['total_power_MW']:.1f} MW")

    # For monitoring/debugging:
    # Use internal diagnostics for detailed analysis
    print("\n--- Internal Diagnostics (Summary) ---")
    diag = results["internal_diagnostics"]

    print("\nAir Loop:")
    print(f"  Air Flow:            {diag['air_loop']['air_pump']['m_dot_air_kg_s']:.0f} kg/s")
    print(f"  Heat Absorbed:       {diag['air_loop']['air_cooled_equipment']['Q_absorbed_W']/1e6:.1f} MW")

    print("\nBuilding Heat Exchanger:")
    print(f"  Heat Transferred:    {diag['building_heat_exchanger']['Q_transferred_MW']:.1f} MW")
    print(f"  Effectiveness:       {diag['building_heat_exchanger']['effectiveness']:.2f}")

    print("\nCooling System:")
    print(f"  Chiller COP:         {diag['cooling_system']['chiller']['COP']:.2f}")
    print(f"  Compressor Power:    {diag['cooling_system']['chiller']['W_comp_MW']:.1f} MW")
    print(f"  Tower Approach:      {diag['cooling_system']['cooling_tower']['approach_C']:.1f} °C")
    print(f"  Water Makeup:        {diag['cooling_system']['cooling_tower']['m_makeup_L_hr']:,.0f} L/hr")


def example_3_connecting_to_building():
    """
    Example 3: How to connect HVAC output to a building model

    This shows the recommended pattern for integrating with building simulation.
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 3: Connecting to Building Model")
    print("=" * 80)

    # Step 1: Create and solve HVAC system
    hvac = IntegratedHVACSystem(
        t_chw_supply_C=7.0,
        chiller_cop=6.0,
        t_wb_C=24.0,
        t_db_C=35.0,
    )

    hvac_results = hvac.solve()

    # Step 2: Extract interface for building
    # The building only needs these values:
    hvac_to_building = hvac_results["for_heat_exchanger"]

    print("\n--- Interface Values for Building ---")
    print(f"T_chw_supply_C:        {hvac_to_building['T_chw_supply_C']:.2f} °C")
    print(f"T_chw_return_C:        {hvac_to_building['T_chw_return_C']:.2f} °C")
    print(f"m_dot_chw_kg_s:        {hvac_to_building['m_dot_chw_kg_s']:.0f} kg/s")
    print(f"Q_cooling_W:           {hvac_to_building['Q_cooling_W']:.0f} W")
    print(f"Q_cooling_MW:          {hvac_to_building['Q_cooling_MW']:.1f} MW")

    print("\n--- Building Model Pseudo-code ---")
    print("""
    # In your building model, you would use:

    def update_building_hvac(hvac_interface):
        # Extract HVAC outputs
        T_supply = hvac_interface['T_chw_supply_C']
        T_return = hvac_interface['T_chw_return_C']
        m_dot = hvac_interface['m_dot_chw_kg_s']
        Q_cooling = hvac_interface['Q_cooling_W']

        # Apply to building thermal model
        building.apply_cooling(
            supply_temp=T_supply,
            return_temp=T_return,
            flow_rate=m_dot,
            cooling_capacity=Q_cooling
        )

        return building.state

    # Usage:
    building_state = update_building_hvac(hvac_to_building)
    """)

    # Step 3: Show what's NOT needed for building
    # (but available for monitoring)
    print("\n--- Values NOT Needed for Building ---")
    print("(But available in internal_diagnostics for monitoring)")
    print("  - Refrigerant states")
    print("  - Compressor pressures")
    print("  - Cooling tower psychrometrics")
    print("  - Pump details")
    print("  - Energy balance checks")
    print("  - Convergence info")


def example_4_data_structure():
    """
    Example 4: Understanding the data structure

    Shows the complete structure of outputs.
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 4: Data Structure Overview")
    print("=" * 80)

    cooling_sys = CoolingSystem(
        chiller_capacity_MW=100.0,
        chiller_cop=6.0,
        t_chw_supply_C=7.0,
    )

    result = cooling_sys.solve(
        q_cooling_load_W=100e6,
        m_dot_chw_kg_s=4777,
        t_chw_return_C=12.0,
        t_wb_ambient_C=24.0,
        t_db_ambient_C=35.0,
    )

    print("\n--- Output Structure ---")
    print("""
    result = {
        'downstream_interface': {
            # VALUES FOR HEAT EXCHANGER / BUILDING
            'T_chw_supply_C': float,      # CHW supply temperature
            'T_chw_return_C': float,      # CHW return temperature
            'm_dot_chw_kg_s': float,      # CHW mass flow rate
            'Q_cooling_W': float,         # Cooling capacity (W)
            'Q_cooling_MW': float,        # Cooling capacity (MW)
            'deltaT_chw_C': float,        # CHW temperature difference
            'system_COP': float,          # Overall system COP
            'total_power_W': float,       # Total power consumption
        },
        'internal_states': {
            # DETAILED INTERNAL STATES
            'convergence': {...},         # Convergence info
            'chiller': {...},             # Chiller details
            'condenser_water_loop': {...},# CW loop states
            'cooling_tower': {...},       # Tower details
            'pump': {...},                # Pump details
            'energy_balance': {...},      # Validation
        }
    }
    """)

    print("\n--- Key Design Principles ---")
    print("1. downstream_interface: Clean interface for connected components")
    print("2. internal_states: Detailed diagnostics for monitoring/debugging")
    print("3. Separation of concerns: Building doesn't see refrigerant details")
    print("4. Easy to use: Just access result['downstream_interface']")
    print("5. Complete data: Everything available if needed")


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("HVAC SYSTEM USAGE EXAMPLES")
    print("Demonstrating Refactored Architecture")
    print("=" * 80)

    # Run examples
    example_1_cooling_system_standalone()
    example_2_full_hvac_system()
    example_3_connecting_to_building()
    example_4_data_structure()

    print("\n" + "=" * 80)
    print("All examples completed successfully!")
    print("=" * 80 + "\n")
