"""
Integrated Cooling System Module (Chiller + Cooling Tower)

This module integrates chiller and cooling tower into a single system
for easier use and simplified interfaces.

Key Features:
- Combined chiller and cooling tower operation
- Iterative solution for condenser water loop
- Simplified interface for downstream components
- Separated internal states from downstream outputs

Author: HVAC Team
Date: 2025-11-19
"""

from typing import Dict, Optional
from chiller import Chiller
from cooling_tower import CoolingTower
from pump import PumpSystem


class CoolingSystem:
    """
    Integrated cooling system combining chiller and cooling tower.

    This class manages the condenser water loop between chiller and cooling tower,
    solving for steady-state operation with iterative convergence.

    Components:
        - Chiller: Provides cooling using vapor compression cycle
        - Cooling Tower: Rejects heat to ambient air
        - Condenser Water Pump: Circulates water between chiller and tower

    Interface Design:
        The system exposes two types of outputs:
        1. downstream_interface: Values needed by connected components (heat exchanger)
        2. internal_states: Detailed internal states for monitoring/debugging
    """

    def __init__(
        self,
        # Chiller parameters
        chiller_capacity_MW: float = 1000.0,
        chiller_cop: float = 6.0,
        t_chw_supply_C: float = 7.0,
        refrigerant: str = "R134a",

        # Cooling tower parameters
        tower_approach_C: float = 4.0,
        tower_coc: float = 4.0,
        tower_drift_rate: float = 1e-5,

        # Pump parameters
        pump_static_head_m: float = 10.0,
        pump_efficiency: float = 0.85,

        # Convergence parameters
        max_iter: int = 50,
        tol_C: float = 0.05,
    ):
        """
        Initialize integrated cooling system.

        Args:
            chiller_capacity_MW: Rated chiller capacity (MW)
            chiller_cop: Chiller coefficient of performance
            t_chw_supply_C: Chilled water supply temperature (°C)
            refrigerant: Refrigerant type (default R134a)
            tower_approach_C: Cooling tower approach temperature (°C)
            tower_coc: Cycles of concentration
            tower_drift_rate: Drift rate fraction
            pump_static_head_m: Pump static head (m)
            pump_efficiency: Pump efficiency (0-1)
            max_iter: Maximum iterations for convergence
            tol_C: Temperature convergence tolerance (°C)
        """
        # Create components
        self.chiller = Chiller(
            rated_capacity_mw=chiller_capacity_MW,
            rated_cop=chiller_cop,
            t_chw_supply=t_chw_supply_C,
            refrigerant=refrigerant,
            eta_is_comp=0.80,
        )

        self.cooling_tower = CoolingTower(
            approach_temp=tower_approach_C,
            coc=tower_coc,
            drift_rate=tower_drift_rate,
            air_to_water_ratio=1.2,
        )

        self.pump_system = PumpSystem(
            cw_static_head=pump_static_head_m,
            cw_efficiency=pump_efficiency,
        )

        # Store parameters
        self.t_chw_supply = t_chw_supply_C
        self.max_iter = max_iter
        self.tol_C = tol_C
        self.cp_water = 4186.0  # J/(kg·K)

    def solve(
        self,
        q_cooling_load_W: float,
        m_dot_chw_kg_s: float,
        t_chw_return_C: float,
        t_wb_ambient_C: float,
        t_db_ambient_C: Optional[float] = None,
    ) -> Dict:
        """
        Solve complete cooling system for given cooling load.

        This method iterates to find steady-state operation where:
        - Chiller provides required cooling
        - Cooling tower rejects condenser heat
        - Condenser water temperatures are consistent

        Args:
            q_cooling_load_W: Required cooling capacity (W)
            m_dot_chw_kg_s: Chilled water mass flow rate (kg/s)
            t_chw_return_C: Chilled water return temperature (°C)
            t_wb_ambient_C: Ambient wet bulb temperature (°C)
            t_db_ambient_C: Ambient dry bulb temperature (°C), optional

        Returns:
            dict with two main sections:
                - downstream_interface: Values for heat exchanger
                - internal_states: Detailed component states

        Raises:
            ValueError: If solution doesn't converge or parameters invalid
        """
        if q_cooling_load_W <= 0:
            raise ValueError(f"Cooling load must be positive: {q_cooling_load_W}")
        if m_dot_chw_kg_s <= 0:
            raise ValueError(f"CHW flow rate must be positive: {m_dot_chw_kg_s}")
        if t_chw_return_C <= self.t_chw_supply:
            raise ValueError(
                f"CHW return temp ({t_chw_return_C}°C) must be > supply temp ({self.t_chw_supply}°C)"
            )

        # Estimate condenser water flow rate
        # Typical: similar to CHW flow or slightly higher
        deltaT_cw_design = 5.5  # °C, typical cooling tower range
        q_cond_est = q_cooling_load_W * 1.15  # Estimate condenser heat
        m_dot_cw = q_cond_est / (self.cp_water * deltaT_cw_design)

        # Initial guess for condenser water inlet temperature (from tower)
        t_cw_in = t_wb_ambient_C + self.cooling_tower.approach + 0.5

        # Iterative solution
        converged = False
        for iteration in range(self.max_iter):
            # Step 1: Solve chiller
            chiller_result = self.chiller.solve_energy_balance(
                q_evap=q_cooling_load_W,
                m_dot_chw=m_dot_chw_kg_s,
                m_dot_cw=m_dot_cw,
                t_cw_in=t_cw_in,
                t_chw_return=t_chw_return_C,
            )

            # Step 2: Solve cooling tower
            tower_result = self.cooling_tower.solve(
                q_cond=chiller_result["Q_cond_MW"] * 1e6,  # Convert to W
                m_dot_cw=m_dot_cw,
                t_in=chiller_result["T_cw_out_C"],
                t_wb=t_wb_ambient_C,
                t_db=t_db_ambient_C,
            )

            # Step 3: Check convergence
            t_cw_in_new = tower_result["T_water_out_C"]

            if abs(t_cw_in_new - t_cw_in) < self.tol_C:
                converged = True
                t_cw_in = t_cw_in_new
                break

            # Update for next iteration
            t_cw_in = t_cw_in_new

        if not converged:
            raise ValueError(
                f"Cooling system did not converge after {self.max_iter} iterations. "
                f"Last ΔT = {abs(t_cw_in_new - t_cw_in):.3f}°C"
            )

        # Step 4: Calculate pump power
        pump_result = self.pump_system.solve(m_dot_cw=m_dot_cw)

        # Step 5: Package results
        return {
            # ===== DOWNSTREAM INTERFACE =====
            # These are the values that heat exchanger / building need
            "downstream_interface": {
                "component": "CoolingSystem",
                "T_chw_supply_C": self.t_chw_supply,
                "T_chw_return_C": t_chw_return_C,
                "m_dot_chw_kg_s": m_dot_chw_kg_s,
                "Q_cooling_W": q_cooling_load_W,
                "Q_cooling_MW": q_cooling_load_W / 1e6,
                "deltaT_chw_C": t_chw_return_C - self.t_chw_supply,
                "system_COP": chiller_result["COP"],
                "total_power_W": chiller_result["W_comp_MW"] * 1e6 + pump_result["P_pump_W"] + tower_result["W_fan_MW"] * 1e6,
                "total_power_MW": chiller_result["W_comp_MW"] + pump_result["P_pump_W"] / 1e6 + tower_result["W_fan_MW"],
            },

            # ===== INTERNAL STATES =====
            # Detailed states for monitoring, debugging, and validation
            "internal_states": {
                "convergence": {
                    "converged": converged,
                    "iterations": iteration + 1,
                    "final_temp_diff_C": abs(t_cw_in_new - t_cw_in) if not converged else 0.0,
                },

                "chiller": {
                    "Q_evap_MW": chiller_result["Q_evap_MW"],
                    "Q_cond_MW": chiller_result["Q_cond_MW"],
                    "W_comp_MW": chiller_result["W_comp_MW"],
                    "COP": chiller_result["COP"],
                    "PLR": chiller_result["PLR"],
                    "T_evap_sat_C": chiller_result["T_evap_sat_C"],
                    "T_cond_sat_C": chiller_result["T_cond_sat_C"],
                    "P_evap_kPa": chiller_result["P_evap_kPa"],
                    "P_cond_kPa": chiller_result["P_cond_kPa"],
                    "compression_ratio": chiller_result["compression_ratio"],
                    "m_dot_ref_kg_s": chiller_result["m_dot_ref_kg_s"],
                    "refrigerant": chiller_result["refrigerant"],
                },

                "condenser_water_loop": {
                    "m_dot_cw_kg_s": m_dot_cw,
                    "T_cw_from_tower_C": t_cw_in,
                    "T_cw_to_tower_C": chiller_result["T_cw_out_C"],
                    "deltaT_cw_C": chiller_result["T_cw_out_C"] - t_cw_in,
                    "Q_rejected_MW": chiller_result["Q_cond_MW"],
                },

                "cooling_tower": {
                    "Q_rejected_MW": tower_result["Q_cond_MW"],
                    "T_water_in_C": tower_result["T_water_in_C"],
                    "T_water_out_C": tower_result["T_water_out_C"],
                    "T_wb_ambient_C": t_wb_ambient_C,
                    "T_db_ambient_C": tower_result["T_db_in_C"],
                    "approach_C": tower_result["Approach_C"],
                    "range_C": tower_result["Range_C"],
                    "m_dot_air_kg_s": tower_result["m_dot_da_kg_s"],
                    "W_fan_MW": tower_result["W_fan_MW"],
                    "m_evap_kg_s": tower_result["m_evap_kg_s"],
                    "m_makeup_kg_s": tower_result["m_makeup_kg_s"],
                    "m_makeup_L_hr": tower_result["m_makeup_L_hr"],
                    "COC": tower_result["COC"],
                    "RH_in_pct": tower_result["RH_in"] * 100,
                    "RH_out_pct": tower_result["RH_out"] * 100,
                },

                "pump": {
                    "P_pump_W": pump_result["P_pump_W"],
                    "P_pump_kW": pump_result["P_pump_W"] / 1000,
                    "static_head_m": pump_result.get("static_head_m", 0),
                    "efficiency": pump_result.get("efficiency", 0),
                },

                "energy_balance": {
                    "Q_evap_MW": chiller_result["Q_evap_MW"],
                    "W_comp_MW": chiller_result["W_comp_MW"],
                    "Q_cond_MW": chiller_result["Q_cond_MW"],
                    "error_pct": abs(
                        chiller_result["Q_cond_MW"] -
                        (chiller_result["Q_evap_MW"] + chiller_result["W_comp_MW"])
                    ) / chiller_result["Q_cond_MW"] * 100,
                },
            },
        }


if __name__ == "__main__":
    """
    Test cooling system with typical datacenter conditions.
    """
    print("\n" + "=" * 80)
    print("INTEGRATED COOLING SYSTEM TEST - Datacenter Conditions")
    print("=" * 80)

    # Create cooling system
    cooling_system = CoolingSystem(
        chiller_capacity_MW=1000.0,
        chiller_cop=6.0,
        t_chw_supply_C=7.0,
        tower_approach_C=4.0,
        tower_coc=4.0,
    )

    # Operating conditions
    q_cooling = 1000e6  # 1000 MW
    m_dot_chw = 47770  # kg/s (for 5°C ΔT)
    t_chw_return = 12.0  # °C
    t_wb = 24.0  # °C
    t_db = 35.0  # °C

    print(f"\nOperating Conditions:")
    print(f"  Cooling Load:        {q_cooling/1e6:.1f} MW")
    print(f"  CHW Flow:            {m_dot_chw:.0f} kg/s")
    print(f"  CHW Supply:          {cooling_system.t_chw_supply:.1f} °C")
    print(f"  CHW Return:          {t_chw_return:.1f} °C")
    print(f"  Ambient Wet Bulb:    {t_wb:.1f} °C")
    print(f"  Ambient Dry Bulb:    {t_db:.1f} °C")

    # Solve system
    result = cooling_system.solve(
        q_cooling_load_W=q_cooling,
        m_dot_chw_kg_s=m_dot_chw,
        t_chw_return_C=t_chw_return,
        t_wb_ambient_C=t_wb,
        t_db_ambient_C=t_db,
    )

    # Print results - DOWNSTREAM INTERFACE (what heat exchanger sees)
    print("\n" + "=" * 80)
    print("DOWNSTREAM INTERFACE (for Heat Exchanger / Building)")
    print("=" * 80)
    ds = result["downstream_interface"]
    print(f"Component:             {ds['component']}")
    print(f"CHW Supply Temp:       {ds['T_chw_supply_C']:.2f} °C")
    print(f"CHW Return Temp:       {ds['T_chw_return_C']:.2f} °C")
    print(f"CHW Flow Rate:         {ds['m_dot_chw_kg_s']:.0f} kg/s")
    print(f"CHW Delta-T:           {ds['deltaT_chw_C']:.2f} °C")
    print(f"Cooling Capacity:      {ds['Q_cooling_MW']:.1f} MW")
    print(f"System COP:            {ds['system_COP']:.2f}")
    print(f"Total Power:           {ds['total_power_MW']:.1f} MW")

    # Print results - INTERNAL STATES (for debugging/monitoring)
    print("\n" + "=" * 80)
    print("INTERNAL STATES (for Monitoring & Debugging)")
    print("=" * 80)

    internal = result["internal_states"]

    print(f"\n--- Convergence ---")
    print(f"Converged:             {internal['convergence']['converged']}")
    print(f"Iterations:            {internal['convergence']['iterations']}")

    print(f"\n--- Chiller ---")
    ch = internal["chiller"]
    print(f"Q_evap:                {ch['Q_evap_MW']:.1f} MW")
    print(f"Q_cond:                {ch['Q_cond_MW']:.1f} MW")
    print(f"W_comp:                {ch['W_comp_MW']:.1f} MW")
    print(f"COP:                   {ch['COP']:.2f}")
    print(f"T_evap_sat:            {ch['T_evap_sat_C']:.1f} °C")
    print(f"T_cond_sat:            {ch['T_cond_sat_C']:.1f} °C")
    print(f"Compression Ratio:     {ch['compression_ratio']:.2f}")

    print(f"\n--- Condenser Water Loop ---")
    cw = internal["condenser_water_loop"]
    print(f"Flow Rate:             {cw['m_dot_cw_kg_s']:.0f} kg/s")
    print(f"From Tower:            {cw['T_cw_from_tower_C']:.2f} °C")
    print(f"To Tower:              {cw['T_cw_to_tower_C']:.2f} °C")
    print(f"Delta-T:               {cw['deltaT_cw_C']:.2f} °C")

    print(f"\n--- Cooling Tower ---")
    ct = internal["cooling_tower"]
    print(f"Heat Rejected:         {ct['Q_rejected_MW']:.1f} MW")
    print(f"Water In:              {ct['T_water_in_C']:.2f} °C")
    print(f"Water Out:             {ct['T_water_out_C']:.2f} °C")
    print(f"Range:                 {ct['range_C']:.2f} °C")
    print(f"Approach:              {ct['approach_C']:.2f} °C")
    print(f"Fan Power:             {ct['W_fan_MW']:.1f} MW")
    print(f"Water Makeup:          {ct['m_makeup_L_hr']:,.0f} L/hr")

    print(f"\n--- Energy Balance ---")
    eb = internal["energy_balance"]
    print(f"Q_evap:                {eb['Q_evap_MW']:.1f} MW")
    print(f"W_comp:                {eb['W_comp_MW']:.1f} MW")
    print(f"Q_cond:                {eb['Q_cond_MW']:.1f} MW")
    print(f"Balance Error:         {eb['error_pct']:.4f} %")

    print("=" * 80 + "\n")
