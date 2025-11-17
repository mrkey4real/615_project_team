"""
Cooling Tower Module - Psychrometric Analysis

This module implements an induced-draft cooling tower using advanced
psychrometric analysis with air-side mass and energy balances.

Key Features:
- Complete psychrometric state calculations for moist air
- Multi-phase energy transfer (sensible + latent heat)
- Humidity ratio calculations for mass balance
- Air-side and water-side energy balance verification
- Enthalpy-based calculations for precise energy accounting

Author: HVAC Team
Date: 2025-11-10
"""

from psychrometrics import MoistAir, PsychrometricState


class CoolingTower:
    """
    Models induced-draft cooling tower using psychrometric analysis.

    Component-Level Modeling:
        - Air side: Inlet/outlet psychrometric states (T_db, w, h, RH)
        - Water side: Inlet/outlet temperatures and mass flow
        - Mass balance: Air + makeup = Air + evap + drift + blowdown
        - Energy balance: Q_water = Q_air + evaporation enthalpy

    Thermodynamic States:
        Air inlet: T_db, T_wb (ambient conditions) → w_in, h_in
        Air outlet: Saturated at T_water_out → w_out, h_out
        Water inlet: T_in, mass flow m_cw
        Water outlet: T_out (= T_wb + Approach)

    Mass Balances:
        Dry air: m_da_in = m_da_out (constant)
        Water vapor: m_da*(w_out - w_in) = m_evap
        Liquid water: m_evap + m_drift + m_blowdown = m_makeup

    Energy Balance:
        Water side: Q = m_cw * cp_w * (T_in - T_out)
        Air side: Q = m_da * (h_out - h_in)
        Evaporation: Q_evap = m_evap * h_fg

    Variables:
        m_da: Dry air mass flow rate (kg_da/s)
        m_cw: Circulating water flow (kg/s)
        m_evap: Evaporation loss (kg/s)
        m_drift: Drift loss (kg/s)
        m_blowdown: Blowdown loss (kg/s)
        m_makeup: Total makeup water (kg/s)
    """

    def __init__(self, approach_temp, coc, drift_rate=0.00001, air_to_water_ratio=1.2):
        """
        Initialize cooling tower module with psychrometric modeling.

        Args:
            approach_temp: Approach temperature T_out - T_wb (°C)
            coc: Cycles of concentration (-)
            drift_rate: Drift as fraction of circulating water (-)
            air_to_water_ratio: Air mass flow to water mass flow ratio (L/L for ρ≈1)

        Raises:
            ValueError: If parameters are invalid
        """
        if approach_temp <= 0 or approach_temp > 20:
            raise ValueError(f"Invalid approach_temp: {approach_temp}, must be between 0 and 20 °C")
        if coc < 2 or coc > 10:
            raise ValueError(f"Invalid coc: {coc}, must be between 2 and 10")
        if drift_rate < 0 or drift_rate > 0.01:
            raise ValueError(f"Invalid drift_rate: {drift_rate}, must be between 0 and 0.01")
        if air_to_water_ratio <= 0 or air_to_water_ratio > 5:
            raise ValueError(
                f"Invalid air_to_water_ratio: {air_to_water_ratio}, must be between 0 and 5"
            )

        self.approach = approach_temp
        self.coc = coc
        self.drift_rate = drift_rate
        self.air_to_water_ratio = air_to_water_ratio
        self.cp_water = 4186  # J/(kg·K)
        self.h_fg = 2260e3  # J/kg (latent heat at ~30°C, approximate)

    def calculate_outlet_temp(self, t_wb):
        """
        Calculate outlet water temperature.

        T_out = T_wb + Approach

        Args:
            t_wb: Wet bulb temperature (C)

        Returns:
            t_out: Outlet water temperature (C) [State 8]

        Raises:
            ValueError: If t_wb is invalid
        """
        if t_wb < -20 or t_wb > 50:
            raise ValueError(f"Invalid t_wb: {t_wb}, must be between -20 and 50 C")

        return t_wb + self.approach

    def calculate_evaporation_rate(self, q_cond, m_dot_cw, delta_t):
        """
        Calculate evaporation water loss.

        Method 1 (energy-based): m_evap = Q / h_fg
        Method 2 (empirical): m_evap = 0.00153 * delta_T * m_dot_cw

        Using Method 1 for accuracy.

        Args:
            q_cond: Condenser heat rejection (W)
            m_dot_cw: Circulating water flow rate (kg/s)
            delta_t: Temperature range T_in - T_out (C)

        Returns:
            m_evap: Evaporation rate (kg/s)
        """
        # Energy-based calculation
        m_evap = q_cond / self.h_fg
        return m_evap

    def calculate_drift_loss(self, m_dot_cw):
        """
        Calculate drift loss.

        Modern towers: 0.001% of circulating water

        Args:
            m_dot_cw: Circulating water flow rate (kg/s)

        Returns:
            m_drift: Drift loss (kg/s)
        """
        return self.drift_rate * m_dot_cw

    def calculate_blowdown_rate(self, m_evap):
        """
        Calculate blowdown requirement.

        Blowdown prevents mineral buildup.
        m_blowdown = m_evap / (COC - 1)

        Args:
            m_evap: Evaporation rate (kg/s)

        Returns:
            m_blowdown: Blowdown rate (kg/s)
        """
        return m_evap / (self.coc - 1)

    def calculate_makeup_water(self, m_evap, m_drift, m_blowdown):
        """
        Calculate total makeup water requirement.

        Water Balance: m_makeup = m_evap + m_drift + m_blowdown

        Args:
            m_evap: Evaporation rate (kg/s)
            m_drift: Drift loss (kg/s)
            m_blowdown: Blowdown rate (kg/s)

        Returns:
            m_makeup: Total makeup water (kg/s)
        """
        return m_evap + m_drift + m_blowdown

    def calculate_fan_power(self, q_cond):
        """
        Estimate fan power consumption.

        Typical: 0.5-1.0% of heat rejection
        Using: 0.7% as baseline

        Args:
            q_cond: Heat rejection (W)

        Returns:
            w_fan: Fan power (W)
        """
        fan_power_fraction = 0.007
        return q_cond * fan_power_fraction

    def solve(self, q_cond, m_dot_cw, t_in, t_wb, t_db=None, RH_in=None):
        """
        Solve complete cooling tower performance using psychrometric analysis.

        Solution procedure:
        1. Calculate water outlet temperature: T_out = T_wb + Approach
        2. Determine air inlet psychrometric state (T_db, T_wb) → (w_in, h_in)
        3. Assume air outlet is saturated at T_out → (w_out, h_out)
        4. Calculate dry air mass flow rate from water/air ratio
        5. Solve mass balances for evaporation, drift, blowdown
        6. Verify energy balance: Q_water = Q_air
        7. Check thermodynamic feasibility

        Args:
            q_cond: Heat rejection load (W)
            m_dot_cw: Circulating water flow rate (kg/s)
            t_in: Inlet water temperature (°C) [State 9]
            t_wb: Ambient wet bulb temperature (°C)
            t_db: Ambient dry bulb temperature (°C), if None estimated from T_wb
            RH_in: Ambient relative humidity (0-1), if None calculated from T_db, T_wb

        Returns:
            dict: Complete performance data with psychrometric states

        Raises:
            ValueError: If parameters are invalid or solution is infeasible
        """
        if q_cond <= 0:
            raise ValueError(f"Invalid q_cond: {q_cond}, must be > 0")
        if m_dot_cw <= 0:
            raise ValueError(f"Invalid m_dot_cw: {m_dot_cw}, must be > 0")
        if t_in < 0 or t_in >= 100:
            raise ValueError(f"Invalid t_in: {t_in}, must be between 0 and 100 °C")

        # Step 1: Water side temperatures
        t_out = self.calculate_outlet_temp(t_wb)
        delta_t = t_in - t_out  # Range

        if delta_t <= 0:
            raise ValueError(f"Water inlet temp {t_in}°C must be > outlet temp {t_out}°C")

        # Step 2: Air inlet psychrometric state
        # If T_db not provided, estimate from typical T_db - T_wb relationship
        if t_db is None:
            # Typical depression: T_db - T_wb ≈ 5-15°C depending on humidity
            # For moderate humidity (~50%), depression ~ 10°C
            t_db = t_wb + 10.0

        # Create air inlet state
        try:
            air_in = PsychrometricState(T_db_C=t_db, T_wb_C=t_wb)
        except Exception as e:
            raise ValueError(f"Failed to calculate air inlet state: {e}")

        # Step 3: Air outlet state (assume saturated at water outlet temperature)
        # This is a standard assumption: air leaves nearly saturated
        try:
            air_out = PsychrometricState(T_db_C=t_out, RH=0.95)  # 95% RH, nearly saturated
        except Exception as e:
            raise ValueError(f"Failed to calculate air outlet state: {e}")

        # Step 4: Calculate water-side heat rejection
        q_water = m_dot_cw * self.cp_water * delta_t  # W

        # Step 5: Calculate required air mass flow rate from energy balance
        # Energy balance: Q_water = m_da * (h_out - h_in)
        # Therefore: m_da = Q_water / (h_out - h_in)
        delta_h_air = air_out.h - air_in.h  # J/kg_da

        if delta_h_air <= 0:
            raise ValueError(
                f"Air enthalpy must increase through tower. "
                f"h_in={air_in.h:.0f} J/kg, h_out={air_out.h:.0f} J/kg"
            )

        m_dot_da = q_water / delta_h_air  # kg_da/s

        # Calculate actual air-to-water ratio achieved
        actual_air_to_water_ratio = m_dot_da * (1 + air_in.w) / m_dot_cw

        # Step 6: Mass balances
        # Evaporation from humidity ratio change
        m_evap_air = m_dot_da * (air_out.w - air_in.w)  # kg_water/s

        # Also calculate evaporation from energy balance (for verification)
        m_evap_energy = q_cond / self.h_fg  # kg/s

        # Use air-side calculation as primary (more accurate for cooling towers)
        m_evap = m_evap_air

        # Drift loss
        m_drift = self.calculate_drift_loss(m_dot_cw)

        # Blowdown
        m_blowdown = self.calculate_blowdown_rate(m_evap)

        # Makeup water
        m_makeup = self.calculate_makeup_water(m_evap, m_drift, m_blowdown)

        # Step 7: Verify energy balance
        # Since we calculated m_da from energy balance, error should be minimal
        # But let's verify to catch any numerical issues
        q_air = m_dot_da * (air_out.h - air_in.h)
        energy_balance_error = abs(q_water - q_air) / q_water * 100

        # Energy balance should be very small now (< 1%)
        if energy_balance_error > 5.0:
            import warnings

            warnings.warn(
                f"Cooling tower energy balance error {energy_balance_error:.1f}% exceeds 5%. "
                f"This suggests numerical issues in psychrometric calculations."
            )

        # Fan power
        w_fan = self.calculate_fan_power(q_cond)

        # Step 7: Return complete solution
        return {
            "component": "Cooling Tower (Psychrometric)",
            "Q_cond_MW": q_cond / 1e6,
            "Q_water_MW": q_water / 1e6,
            "Q_air_MW": q_air / 1e6,
            # Water side
            "T_water_in_C": t_in,
            "T_water_out_C": t_out,
            "Range_C": delta_t,
            "Approach_C": self.approach,
            "m_dot_cw_kg_s": m_dot_cw,
            # Air side
            "T_db_in_C": air_in.T_db,
            "T_wb_in_C": t_wb,
            "T_db_out_C": air_out.T_db,
            "RH_in": air_in.RH,
            "RH_out": air_out.RH,
            "w_in_kg_kg": air_in.w,
            "w_out_kg_kg": air_out.w,
            "h_in_J_kg": air_in.h,
            "h_out_J_kg": air_out.h,
            "m_dot_da_kg_s": m_dot_da,
            "air_to_water_ratio": actual_air_to_water_ratio,
            "air_to_water_ratio_design": self.air_to_water_ratio,
            # Mass balances
            "m_evap_kg_s": m_evap,
            "m_evap_energy_kg_s": m_evap_energy,
            "m_drift_kg_s": m_drift,
            "m_blowdown_kg_s": m_blowdown,
            "m_makeup_kg_s": m_makeup,
            "m_makeup_L_s": m_makeup,
            "m_makeup_L_hr": m_makeup * 3600,
            "COC": self.coc,
            # Performance
            "W_fan_MW": w_fan / 1e6,
            "energy_balance_error_pct": energy_balance_error,
            # Thermodynamic states
            "air_inlet_state": air_in,
            "air_outlet_state": air_out,
        }


class CoolingTowerOptimized(CoolingTower):
    """
    Optimized cooling tower with dynamic COC control.

    Optimization Strategy:
        - Increase COC from 5 to maximum feasible value
        - Maximum COC limited by water chemistry (e.g., SiO2 concentration)
        - Reduce blowdown rate: m_blowdown = m_evap / (COC - 1)
    """

    def __init__(self, makeup_silica_ppm=25, max_silica_ppm=150, **kwargs):
        """
        Initialize optimized cooling tower.

        Args:
            makeup_silica_ppm: SiO2 concentration in makeup water (ppm)
            max_silica_ppm: Maximum allowable SiO2 in circulating water (ppm)
            **kwargs: Pass through to base class

        Raises:
            ValueError: If parameters are invalid
        """
        if makeup_silica_ppm <= 0 or makeup_silica_ppm > 100:
            raise ValueError(
                f"Invalid makeup_silica_ppm: {makeup_silica_ppm}, must be between 0 and 100"
            )
        if max_silica_ppm <= makeup_silica_ppm:
            raise ValueError(
                f"max_silica_ppm ({max_silica_ppm}) must be > makeup_silica_ppm ({makeup_silica_ppm})"
            )

        # Calculate maximum COC based on silica limit
        max_coc = max_silica_ppm / makeup_silica_ppm

        # Override COC if not specified
        if "coc" not in kwargs:
            kwargs["coc"] = max_coc

        super().__init__(**kwargs)

        self.makeup_silica_ppm = makeup_silica_ppm
        self.max_silica_ppm = max_silica_ppm
        self.max_coc = max_coc

    def calculate_water_savings(self, baseline_coc=5.0):
        """
        Calculate water savings compared to baseline.

        Args:
            baseline_coc: Baseline cycles of concentration

        Returns:
            dict: Water savings analysis
        """
        # Blowdown reduction
        # Baseline: m_bd_baseline = m_evap / (COC_base - 1)
        # Optimized: m_bd_opt = m_evap / (COC_opt - 1)

        bd_fraction_baseline = 1.0 / (baseline_coc - 1)
        bd_fraction_optimized = 1.0 / (self.coc - 1)

        reduction = (bd_fraction_baseline - bd_fraction_optimized) / bd_fraction_baseline

        return {
            "baseline_COC": baseline_coc,
            "optimized_COC": self.coc,
            "blowdown_reduction_pct": reduction * 100,
            "max_silica_limit_ppm": self.max_silica_ppm,
        }


if __name__ == "__main__":
    """
    Test cooling tower module with typical operating conditions.
    """
    print("\n" + "=" * 80)
    print("COOLING TOWER MODULE TEST - Typical Datacenter Conditions")
    print("=" * 80)

    # Create cooling tower
    tower = CoolingTower(
        approach_temp=4.0,  # 4°C approach
        coc=5.0,  # Cycles of concentration
        drift_rate=0.00001,  # 0.001% drift
        air_to_water_ratio=1.2,  # Air to water ratio
    )

    # Test conditions
    q_cond = 1150e6  # 1150 MW heat rejection
    m_dot_cw = 50000  # kg/s condenser water flow
    t_in = 35.0  # °C water inlet temp (from chiller)
    t_wb = 25.5  # °C ambient wet bulb
    t_db = 35.5  # °C ambient dry bulb

    print(f"\nTest Conditions:")
    print(f"  Heat Rejection:       {q_cond/1e6:.1f} MW")
    print(f"  Water Flow Rate:      {m_dot_cw:.0f} kg/s")
    print(f"  Water Inlet Temp:     {t_in:.1f} °C")
    print(f"  Ambient Wet Bulb:     {t_wb:.1f} °C")
    print(f"  Ambient Dry Bulb:     {t_db:.1f} °C")

    # Solve cooling tower
    result = tower.solve(q_cond=q_cond, m_dot_cw=m_dot_cw, t_in=t_in, t_wb=t_wb, t_db=t_db)

    # Print results
    print(f"\n--- COOLING TOWER PERFORMANCE ---")
    print(f"Component:              {result['component']}")
    print(f"\n--- ENERGY BALANCE ---")
    print(f"Q_cond:                 {result['Q_cond_MW']:.1f} MW")
    print(f"Q_water:                {result['Q_water_MW']:.1f} MW")
    print(f"Q_air:                  {result['Q_air_MW']:.1f} MW")
    print(f"Energy Balance Error:   {result['energy_balance_error_pct']:.2f} %")
    print(f"\n--- WATER SIDE ---")
    print(f"T_in:                   {result['T_water_in_C']:.1f} °C")
    print(f"T_out:                  {result['T_water_out_C']:.1f} °C")
    print(f"Range:                  {result['Range_C']:.1f} °C")
    print(f"Approach:               {result['Approach_C']:.1f} °C")
    print(f"Flow Rate:              {result['m_dot_cw_kg_s']:.0f} kg/s")
    print(f"\n--- AIR SIDE ---")
    print(f"T_db_in:                {result['T_db_in_C']:.1f} °C")
    print(f"T_wb_in:                {result['T_wb_in_C']:.1f} °C")
    print(f"T_db_out:               {result['T_db_out_C']:.1f} °C")
    print(f"RH_in:                  {result['RH_in']*100:.1f} %")
    print(f"RH_out:                 {result['RH_out']*100:.1f} %")
    print(f"w_in:                   {result['w_in_kg_kg']:.6f} kg/kg")
    print(f"w_out:                  {result['w_out_kg_kg']:.6f} kg/kg")
    print(f"h_in:                   {result['h_in_J_kg']/1000:.1f} kJ/kg")
    print(f"h_out:                  {result['h_out_J_kg']/1000:.1f} kJ/kg")
    print(f"Dry Air Flow:           {result['m_dot_da_kg_s']:.0f} kg_da/s")
    print(f"\n--- WATER CONSUMPTION ---")
    print(f"Evaporation (air):      {result['m_evap_kg_s']:.1f} kg/s  ({result['m_evap_kg_s']*3600:.0f} L/hr)")
    print(f"Evaporation (energy):   {result['m_evap_energy_kg_s']:.1f} kg/s")
    print(f"Drift:                  {result['m_drift_kg_s']:.3f} kg/s")
    print(f"Blowdown:               {result['m_blowdown_kg_s']:.1f} kg/s")
    print(f"Total Makeup:           {result['m_makeup_kg_s']:.1f} kg/s  ({result['m_makeup_L_hr']:,.0f} L/hr)")
    print(f"COC:                    {result['COC']:.1f}")
    print(f"\n--- POWER CONSUMPTION ---")
    print(f"Fan Power:              {result['W_fan_MW']:.1f} MW")
    print("=" * 80 + "\n")
