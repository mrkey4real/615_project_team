"""
Usage:
    python run_hvac.py

Inputs (from building-side heat exchangers):
    - Total cooling load (Q_evap) from building and compute loads
    - Chilled water return temperature (T_chw_return)
    - Ambient conditions (T_wb, T_db)

Outputs:
    - Chilled water supply temperature and flow rate
    - Power consumption (chiller, pumps, fans)
    - All node parameters (temperatures, flows, air properties)
    - Water consumption data
"""

from chiller import Chiller
from cooling_tower import CoolingTower
from pump import PumpSystem


class HVACSystem:
    """
    Integrates chiller, cooling tower, and pump systems.

    System Flow:
        Building/Compute Loads → Heat Exchangers → Chilled Water Return
        → Chiller Evaporator → Chiller Compressor → Chiller Condenser
        → Cooling Tower → Atmosphere

    Loops:
        1. Chilled Water Loop: Chiller → Building HX → Compute HX → Chiller
        2. Condenser Water Loop: Cooling Tower → Chiller Condenser → Cooling Tower
        3. GPU Coolant Loop: Compute HX → GPU Cold Plates → Compute HX
    """

    def __init__(
        self,
        chiller_capacity_mw=1000,
        chiller_cop=6.1,
        t_chw_supply=10.0,
        cooling_tower_approach=4.0,
        coc=5.0,
    ):
        """
        Initialize HVAC system with all components.

        Args:
            chiller_capacity_mw: Chiller rated capacity (MW)
            chiller_cop: Chiller rated COP (-)
            t_chw_supply: Chilled water supply temperature (°C)
            cooling_tower_approach: Cooling tower approach temperature (°C)
            coc: Cycles of concentration for cooling tower (-)
        """
        # Initialize components
        self.chiller = Chiller(
            rated_capacity_mw=chiller_capacity_mw,
            rated_cop=chiller_cop,
            t_chw_supply=t_chw_supply,
            refrigerant="R134a",
            eta_is_comp=0.80,
        )

        self.cooling_tower = CoolingTower(
            approach_temp=cooling_tower_approach,
            coc=coc,
            drift_rate=0.00001,
            air_to_water_ratio=1.2,
        )

        self.pump_system = PumpSystem(
            cw_static_head=10.0,
        )

        # Store configuration
        self.t_chw_supply = t_chw_supply
        self.cp_water = 4186  # J/(kg·K)

    def calculate_flow_rates(self, q_evap, t_chw_return, q_gpu):
        """
        Calculate design flow rates for all loops.

        Args:
            q_evap: Total evaporator load (W)
            t_chw_return: Chilled water return temperature (°C)
            q_gpu: GPU load (W)

        Returns:
            dict: Flow rates for all loops (kg/s)
        """
        # Chilled water flow rate
        delta_t_chw = t_chw_return - self.t_chw_supply
        if delta_t_chw <= 0:
            raise ValueError(
                f"Invalid temperature difference: T_return ({t_chw_return}°C) "
                f"must be > T_supply ({self.t_chw_supply}°C)"
            )
        m_dot_chw = q_evap / (self.cp_water * delta_t_chw)

        # Condenser water flow rate (estimate based on typical range)
        # Q_cond ≈ Q_evap × 1.15 (COP ~ 6)
        # Typical range: 5-6°C
        q_cond_estimate = q_evap * 1.15
        delta_t_cw = 5.5  # °C
        m_dot_cw = q_cond_estimate / (self.cp_water * delta_t_cw)

        # GPU coolant flow rate
        # Typical GPU delta-T: 20-25°C
        delta_t_gpu = 23.0  # °C
        m_dot_gpu = q_gpu / (self.cp_water * delta_t_gpu)

        return {
            "m_dot_chw_kg_s": m_dot_chw,
            "m_dot_cw_kg_s": m_dot_cw,
            "m_dot_gpu_kg_s": m_dot_gpu,
            "delta_T_chw_C": delta_t_chw,
            "delta_T_cw_C": delta_t_cw,
            "delta_T_gpu_C": delta_t_gpu,
        }

    def solve(
        self,
        q_evap,
        t_chw_return,
        q_gpu,
        t_wb,
        t_db=None,
        max_iter=50,
        tolerance=0.1,
    ):
        """
        Solve complete HVAC system performance.

        Solution Procedure:
        1. Calculate flow rates based on loads and temperatures
        2. Iterate to find consistent chiller and cooling tower operation:
           a. Solve chiller for given CW inlet temperature
           b. Solve cooling tower for chiller's CW outlet temperature
           c. Update CW inlet temperature
           d. Check convergence
        3. Solve pump system for all loops
        4. Compile complete results

        Args:
            q_evap: Total cooling load (W) from building-side
            t_chw_return: Chilled water return temperature (°C) from building-side
            q_gpu: GPU cooling load (W)
            t_wb: Ambient wet bulb temperature (°C)
            t_db: Ambient dry bulb temperature (°C), optional
            max_iter: Maximum iterations for convergence
            tolerance: Convergence tolerance (°C)

        Returns:
            dict: Complete HVAC system performance data

        Raises:
            ValueError: If solution doesn't converge or inputs invalid
        """
        if q_evap <= 0:
            raise ValueError(f"Invalid q_evap: {q_evap}, must be > 0")
        if q_gpu < 0 or q_gpu > q_evap:
            raise ValueError(f"Invalid q_gpu: {q_gpu}, must be between 0 and q_evap")

        # Calculate flow rates
        flows = self.calculate_flow_rates(q_evap, t_chw_return, q_gpu)
        m_dot_chw = flows["m_dot_chw_kg_s"]
        m_dot_cw = flows["m_dot_cw_kg_s"]
        m_dot_gpu = flows["m_dot_gpu_kg_s"]

        # Initial guess for condenser water temperature from cooling tower
        t_cw_in = t_wb + self.cooling_tower.approach + 0.5  # Initial guess

        # Iterative solution for chiller-tower coupling
        for iteration in range(max_iter):
            t_cw_in_old = t_cw_in

            # Step 1: Solve chiller
            chiller_result = self.chiller.solve_energy_balance(
                q_evap=q_evap,
                m_dot_chw=m_dot_chw,
                m_dot_cw=m_dot_cw,
                t_cw_in=t_cw_in,
                t_chw_return=t_chw_return,
            )

            # Extract chiller outputs
            q_cond = chiller_result["Q_cond_MW"] * 1e6  # W
            t_cw_out = chiller_result["T_cw_out_C"]
            w_comp = chiller_result["W_comp_MW"] * 1e6  # W

            # Step 2: Solve cooling tower
            tower_result = self.cooling_tower.solve(
                q_cond=q_cond, m_dot_cw=m_dot_cw, t_in=t_cw_out, t_wb=t_wb, t_db=t_db
            )

            # Extract cooling tower outputs
            t_cw_from_tower = tower_result["T_water_out_C"]

            # Step 3: Update condenser water inlet temperature
            t_cw_in = t_cw_from_tower

            # Step 4: Check convergence
            delta_t_cw = abs(t_cw_in - t_cw_in_old)

            if delta_t_cw < tolerance:
                # Converged
                break
        else:
            raise ValueError(
                f"HVAC system did not converge after {max_iter} iterations. "
                f"Last change: ΔT_cw={delta_t_cw:.3f}°C"
            )

        # Step 5: Solve pump system (CW pump only, HVAC-side)
        pump_result = self.pump_system.solve(m_dot_cw=m_dot_cw)

        # Step 6: Calculate total power consumption
        w_pumps = pump_result["P_pump_W"]
        w_fans = tower_result["W_fan_MW"] * 1e6
        w_total_cooling = w_comp + w_pumps + w_fans

        # Step 7: Compile complete results
        results = {
            "system": "HVAC System (Chiller + Cooling Tower + Pumps)",
            "converged": True,
            "iterations": iteration + 1,
            # Inputs
            "inputs": {
                "Q_evap_MW": q_evap / 1e6,
                "Q_gpu_MW": q_gpu / 1e6,
                "T_chw_return_C": t_chw_return,
                "T_wb_ambient_C": t_wb,
                "T_db_ambient_C": t_db if t_db else tower_result["T_db_in_C"],
            },
            # Flow rates
            "flow_rates": {
                "m_dot_chw_kg_s": m_dot_chw,
                "m_dot_chw_L_s": m_dot_chw,
                "m_dot_cw_kg_s": m_dot_cw,
                "m_dot_cw_L_s": m_dot_cw,
                "m_dot_gpu_kg_s": m_dot_gpu,
                "m_dot_gpu_L_s": m_dot_gpu,
            },
            # Power consumption
            "power": {
                "W_comp_MW": w_comp / 1e6,
                "W_pump_CW_MW": w_pumps / 1e6,
                "W_fans_MW": w_fans / 1e6,
                "W_total_cooling_MW": w_total_cooling / 1e6,
                "pump_details": pump_result["CW_pump"],
            },
            # Chiller performance
            "chiller": {
                "Q_evap_MW": chiller_result["Q_evap_MW"],
                "Q_cond_MW": chiller_result["Q_cond_MW"],
                "COP": chiller_result["COP"],
                "PLR": chiller_result["PLR"],
                "T_chw_supply_C": chiller_result["T_chw_supply_C"],
                "T_chw_return_C": chiller_result["T_chw_return_C"],
                "T_cw_in_C": chiller_result["T_cw_in_C"],
                "T_cw_out_C": chiller_result["T_cw_out_C"],
                "refrigerant": chiller_result["refrigerant"],
                "T_evap_sat_C": chiller_result["T_evap_sat_C"],
                "T_cond_sat_C": chiller_result["T_cond_sat_C"],
                "m_dot_ref_kg_s": chiller_result["m_dot_ref_kg_s"],
            },
            # Cooling tower performance
            "cooling_tower": {
                "Q_cond_MW": tower_result["Q_cond_MW"],
                "T_water_in_C": tower_result["T_water_in_C"],
                "T_water_out_C": tower_result["T_water_out_C"],
                "Range_C": tower_result["Range_C"],
                "Approach_C": tower_result["Approach_C"],
                "air_inlet": {
                    "T_db_C": tower_result["T_db_in_C"],
                    "T_wb_C": tower_result["T_wb_in_C"],
                    "RH": tower_result["RH_in"],
                    "w_kg_kg": tower_result["w_in_kg_kg"],
                    "h_J_kg": tower_result["h_in_J_kg"],
                },
                "air_outlet": {
                    "T_db_C": tower_result["T_db_out_C"],
                    "RH": tower_result["RH_out"],
                    "w_kg_kg": tower_result["w_out_kg_kg"],
                    "h_J_kg": tower_result["h_out_J_kg"],
                },
                "m_dot_air_kg_s": tower_result["m_dot_da_kg_s"],
            },
            # Water consumption
            "water_consumption": {
                "m_evap_kg_s": tower_result["m_evap_kg_s"],
                "m_evap_L_hr": tower_result["m_evap_kg_s"] * 3600,
                "m_drift_kg_s": tower_result["m_drift_kg_s"],
                "m_blowdown_kg_s": tower_result["m_blowdown_kg_s"],
                "m_makeup_kg_s": tower_result["m_makeup_kg_s"],
                "m_makeup_L_s": tower_result["m_makeup_L_s"],
                "m_makeup_L_hr": tower_result["m_makeup_L_hr"],
                "COC": tower_result["COC"],
            },
            # Energy balance validation
            "validation": {
                "chiller_energy_balance_error_pct": chiller_result[
                    "energy_balance_error_pct"
                ],
                "tower_energy_balance_error_pct": tower_result["energy_balance_error_pct"],
                "system_energy_balance_pct": abs(q_cond - (q_evap + w_comp))
                / q_cond
                * 100,
            },
        }

        return results

    def print_summary(self, results):
        """
        Print formatted summary of HVAC system performance.

        Args:
            results: Results dictionary from solve()
        """
        print("\n" + "=" * 90)
        print("HVAC SYSTEM PERFORMANCE SUMMARY")
        print("=" * 90)

        # System status
        print(f"\nSystem Status:")
        print(
            f"  Converged:              {results['converged']} (in {results['iterations']} iterations)"
        )

        # Inputs
        inp = results["inputs"]
        print(f"\n--- INPUTS (from Building-Side) ---")
        print(f"  Total Cooling Load:     {inp['Q_evap_MW']:>10.1f} MW")
        print(f"  GPU Load:               {inp['Q_gpu_MW']:>10.1f} MW")
        print(f"  CHW Return Temp:        {inp['T_chw_return_C']:>10.1f} °C")
        print(f"  Ambient Wet Bulb:       {inp['T_wb_ambient_C']:>10.1f} °C")
        print(f"  Ambient Dry Bulb:       {inp['T_db_ambient_C']:>10.1f} °C")

        # Flow rates
        flow = results["flow_rates"]
        print(f"\n--- FLOW RATES ---")
        print(
            f"  Chilled Water:          {flow['m_dot_chw_kg_s']:>10.0f} kg/s  ({flow['m_dot_chw_L_s']:>10.0f} L/s)"
        )
        print(
            f"  Condenser Water:        {flow['m_dot_cw_kg_s']:>10.0f} kg/s  ({flow['m_dot_cw_L_s']:>10.0f} L/s)"
        )
        print(
            f"  GPU Coolant:            {flow['m_dot_gpu_kg_s']:>10.0f} kg/s  ({flow['m_dot_gpu_L_s']:>10.0f} L/s)"
        )

        # Power consumption
        pwr = results["power"]
        print(f"\n--- POWER CONSUMPTION (HVAC-Side Only) ---")
        print(f"  Chiller Compressor:     {pwr['W_comp_MW']:>10.2f} MW")
        print(f"  CW Pump (HVAC):         {pwr['W_pump_CW_MW']:>10.2f} MW")
        print(f"  Cooling Tower Fans:     {pwr['W_fans_MW']:>10.2f} MW")
        print(f"  TOTAL HVAC POWER:       {pwr['W_total_cooling_MW']:>10.2f} MW")
        print(f"\n  Note: CHW pump and GPU pump are managed by building/compute systems")

        # Chiller
        ch = results["chiller"]
        print(f"\n--- CHILLER PERFORMANCE ---")
        print(f"  Refrigerant:            {ch['refrigerant']:>10s}")
        print(f"  COP:                    {ch['COP']:>10.2f}")
        print(f"  Part Load Ratio:        {ch['PLR']*100:>10.1f} %")
        print(f"  CHW Supply/Return:      {ch['T_chw_supply_C']:>10.1f} / {ch['T_chw_return_C']:.1f} °C")
        print(f"  CW Inlet/Outlet:        {ch['T_cw_in_C']:>10.1f} / {ch['T_cw_out_C']:.1f} °C")
        print(f"  Evap Sat Temp:          {ch['T_evap_sat_C']:>10.1f} °C")
        print(f"  Cond Sat Temp:          {ch['T_cond_sat_C']:>10.1f} °C")
        print(f"  Refrigerant Flow:       {ch['m_dot_ref_kg_s']:>10.2f} kg/s")

        # Cooling tower
        ct = results["cooling_tower"]
        print(f"\n--- COOLING TOWER PERFORMANCE ---")
        print(f"  Water In/Out:           {ct['T_water_in_C']:>10.1f} / {ct['T_water_out_C']:.1f} °C")
        print(f"  Range:                  {ct['Range_C']:>10.1f} °C")
        print(f"  Approach:               {ct['Approach_C']:>10.1f} °C")
        print(f"  Air Inlet:              {ct['air_inlet']['T_db_C']:.1f}°C DB, {ct['air_inlet']['T_wb_C']:.1f}°C WB, RH={ct['air_inlet']['RH']*100:.1f}%")
        print(
            f"  Air Outlet:             {ct['air_outlet']['T_db_C']:.1f}°C, RH={ct['air_outlet']['RH']*100:.1f}%"
        )
        print(f"  Humidity Ratio In/Out:  {ct['air_inlet']['w_kg_kg']:.6f} / {ct['air_outlet']['w_kg_kg']:.6f} kg/kg")
        print(f"  Air Flow:               {ct['m_dot_air_kg_s']:>10.0f} kg_da/s")

        # Water consumption
        water = results["water_consumption"]
        print(f"\n--- WATER CONSUMPTION ---")
        print(
            f"  Evaporation:            {water['m_evap_kg_s']:>10.1f} kg/s  ({water['m_evap_L_hr']:>12,.0f} L/hr)"
        )
        print(f"  Drift:                  {water['m_drift_kg_s']:>10.3f} kg/s")
        print(f"  Blowdown:               {water['m_blowdown_kg_s']:>10.1f} kg/s")
        print(
            f"  Total Makeup:           {water['m_makeup_kg_s']:>10.1f} kg/s  ({water['m_makeup_L_hr']:>12,.0f} L/hr)"
        )
        print(f"  COC:                    {water['COC']:>10.1f}")
        print(
            f"  Annual Water Usage:     {water['m_makeup_kg_s']*3600*8760/1e6:>10.1f} million L/year"
        )

        # Validation
        val = results["validation"]
        print(f"\n--- ENERGY BALANCE VALIDATION ---")
        print(f"  Chiller Error:          {val['chiller_energy_balance_error_pct']:>10.4f} %")
        print(f"  Tower Error:            {val['tower_energy_balance_error_pct']:>10.4f} %")
        print(f"  System Error:           {val['system_energy_balance_pct']:>10.4f} %")

        print("=" * 90 + "\n")


if __name__ == "__main__":
    """
    Example usage of HVAC system.
    """
    print("\n" + "=" * 90)
    print("HVAC SYSTEM MAIN PROGRAM")
    print("=" * 90)

    # Create HVAC system
    hvac = HVACSystem(
        chiller_capacity_mw=1000,  # 1 GW capacity
        chiller_cop=6.1,
        t_chw_supply=10.0,  # °C
        cooling_tower_approach=4.0,  # °C
        coc=5.0,  # Cycles of concentration
    )

    # Input conditions (from building-side heat exchangers)
    # Typical datacenter: 1 GW total, 900 MW GPU, 100 MW building
    q_evap = 1000e6  # W (1000 MW total cooling load)
    q_gpu = 900e6  # W (900 MW GPU load)
    t_chw_return = 15.0  # °C (from building-side HX)
    t_wb = 25.5  # °C (ambient wet bulb)
    t_db = 35.5  # °C (ambient dry bulb)

    print("\n--- RUNNING HVAC SYSTEM ANALYSIS ---")
    print(f"\nInput Conditions:")
    print(f"  Total Cooling Load:     {q_evap/1e6:.1f} MW")
    print(f"  GPU Load:               {q_gpu/1e6:.1f} MW")
    print(f"  CHW Return Temp:        {t_chw_return:.1f} °C")
    print(f"  Ambient Conditions:     {t_db:.1f}°C DB, {t_wb:.1f}°C WB")

    # Solve HVAC system
    results = hvac.solve(
        q_evap=q_evap,
        t_chw_return=t_chw_return,
        q_gpu=q_gpu,
        t_wb=t_wb,
        t_db=t_db,
    )

    # Print results
    hvac.print_summary(results)

    # Additional analysis
    print("\n--- PERFORMANCE METRICS ---")
    p_it = q_evap / 1e6  # MW
    p_cooling = results["power"]["W_total_cooling_MW"]
    pue = (p_it + p_cooling) / p_it
    print(f"  IT Power:               {p_it:.1f} MW")
    print(f"  Cooling Power:          {p_cooling:.2f} MW")
    print(f"  PUE:                    {pue:.3f}")

    # Water usage effectiveness
    annual_water_m3 = results["water_consumption"]["m_makeup_kg_s"] * 3600 * 8760 / 1000
    annual_it_kwh = p_it * 1000 * 8760
    wue = annual_water_m3 * 1000 / annual_it_kwh  # L/kWh
    print(f"  WUE:                    {wue:.3f} L/kWh")

    print("\n" + "=" * 90)
    print("HVAC SYSTEM ANALYSIS COMPLETE")
    print("=" * 90 + "\n")
