"""
Refrigerant Vapor Compression Cycle Module

Models the complete vapor compression refrigeration cycle with refrigerant
thermodynamic states and heat exchanger energy balances.

Based on:
- CoolProp for refrigerant properties
- First law energy balances
- Second law efficiency analysis
- Heat exchanger effectiveness models
"""

try:
    from CoolProp.CoolProp import PropsSI

    COOLPROP_AVAILABLE = True
except ImportError:
    COOLPROP_AVAILABLE = False
    print("Warning: CoolProp not available. Install with: pip install CoolProp")


class RefrigerantState:
    """
    Represents a thermodynamic state point in the refrigeration cycle.

    Properties calculated using CoolProp:
    - Pressure (Pa)
    - Temperature (K, also stored as °C)
    - Enthalpy (J/kg)
    - Entropy (J/kg·K)
    - Quality (0-1, for two-phase states)
    - Density (kg/m³)
    """

    def __init__(self, refrigerant, **kwargs):
        """
        Initialize refrigerant state from two independent properties.

        Args:
            refrigerant: Refrigerant name (e.g., 'R134a', 'R410A', 'R32')
            **kwargs: Two of: P (Pa), T (°C), h (J/kg), s (J/kg·K), Q (quality 0-1)

        Examples:
            state = RefrigerantState('R134a', P=500000, T=10)
            state = RefrigerantState('R134a', P=500000, Q=1.0)
            state = RefrigerantState('R134a', P=500000, h=250000)

        Raises:
            ImportError: If CoolProp is not available
            ValueError: If invalid combination of properties
        """
        if not COOLPROP_AVAILABLE:
            raise ImportError("CoolProp is required for refrigerant property calculations")

        self.refrigerant = refrigerant
        self._validate_refrigerant()

        # Parse input properties
        props = {}
        for key, value in kwargs.items():
            props[key] = value

        # Convert temperature from °C to K if provided
        if "T" in props:
            props["T_K"] = props["T"] + 273.15
            del props["T"]

        # Determine which properties were provided
        if len(props) != 2:
            raise ValueError(
                f"Exactly 2 properties required, got {len(props)}: {list(props.keys())}"
            )

        # Calculate state using CoolProp
        self._calculate_state(props)

    def _validate_refrigerant(self):
        """Validate that refrigerant is supported by CoolProp."""
        try:
            # Test if refrigerant is valid
            PropsSI("Tcrit", self.refrigerant)
        except Exception as e:
            raise ValueError(f"Invalid refrigerant '{self.refrigerant}': {e}")

    def _calculate_state(self, props):
        """
        Calculate all thermodynamic properties from two independent properties.

        Args:
            props: Dictionary with two properties
        """
        # Map property names to CoolProp inputs
        prop_map = {"P": "P", "T_K": "T", "h": "H", "s": "S", "Q": "Q"}

        # Get the two input properties
        keys = list(props.keys())
        input1_name = prop_map[keys[0]]
        input1_val = props[keys[0]]
        input2_name = prop_map[keys[1]]
        input2_val = props[keys[1]]

        # Calculate all properties
        try:
            self.P = PropsSI(
                "P", input1_name, input1_val, input2_name, input2_val, self.refrigerant
            )
            self.T_K = PropsSI(
                "T", input1_name, input1_val, input2_name, input2_val, self.refrigerant
            )
            self.h = PropsSI(
                "H", input1_name, input1_val, input2_name, input2_val, self.refrigerant
            )
            self.s = PropsSI(
                "S", input1_name, input1_val, input2_name, input2_val, self.refrigerant
            )
            self.rho = PropsSI(
                "D", input1_name, input1_val, input2_name, input2_val, self.refrigerant
            )

            # Quality (0-1 for two-phase, -1 for subcooled, >1 for superheated)
            self.Q = PropsSI(
                "Q", input1_name, input1_val, input2_name, input2_val, self.refrigerant
            )

            # Store temperature in Celsius for convenience
            self.T_C = self.T_K - 273.15

        except Exception as e:
            raise ValueError(f"CoolProp error calculating state: {e}")

    @property
    def phase(self):
        """Return phase description."""
        if self.Q < 0:
            return "Subcooled Liquid"
        elif 0 <= self.Q <= 1:
            return f"Two-Phase (x={self.Q:.3f})"
        else:
            return "Superheated Vapor"

    def __repr__(self):
        """String representation of refrigerant state."""
        return (
            f"RefrigerantState({self.refrigerant}: "
            f"P={self.P/1000:.1f} kPa, T={self.T_C:.1f}°C, "
            f"h={self.h/1000:.1f} kJ/kg, {self.phase})"
        )


class VaporCompressionCycle:
    """
    Models a complete vapor compression refrigeration cycle.

    Cycle states:
        1: Compressor inlet (saturated or superheated vapor from evaporator)
        2s: Compressor outlet (isentropic)
        2: Compressor outlet (actual, with isentropic efficiency)
        3: Condenser outlet (saturated or subcooled liquid)
        4: Evaporator inlet (after expansion valve, two-phase)

    Energy balances:
        Q_evap = m_dot_ref * (h1 - h4)    [Cooling capacity]
        W_comp = m_dot_ref * (h2 - h1)    [Compressor power]
        Q_cond = m_dot_ref * (h2 - h3)    [Heat rejection]
        COP = Q_evap / W_comp
    """

    def __init__(self, refrigerant="R134a", eta_is_comp=0.80, superheat_evap=5.0, subcool_cond=3.0):
        """
        Initialize vapor compression cycle.

        Args:
            refrigerant: Refrigerant type (default 'R134a')
            eta_is_comp: Compressor isentropic efficiency (0-1)
            superheat_evap: Evaporator superheat (°C)
            subcool_cond: Condenser subcooling (°C)

        Raises:
            ValueError: If parameters are invalid
        """
        if not 0.5 <= eta_is_comp <= 1.0:
            raise ValueError(f"Compressor efficiency {eta_is_comp} must be between 0.5 and 1.0")
        if superheat_evap < 0 or superheat_evap > 20:
            raise ValueError(f"Superheat {superheat_evap}°C must be between 0 and 20°C")
        if subcool_cond < 0 or subcool_cond > 20:
            raise ValueError(f"Subcooling {subcool_cond}°C must be between 0 and 20°C")

        self.refrigerant = refrigerant
        self.eta_is_comp = eta_is_comp
        self.superheat_evap = superheat_evap
        self.subcool_cond = subcool_cond

        # Cycle states (initialized when solve() is called)
        self.state1 = None  # Evaporator outlet / Compressor inlet
        self.state2s = None  # Compressor outlet (isentropic)
        self.state2 = None  # Compressor outlet (actual)
        self.state3 = None  # Condenser outlet / Expansion valve inlet
        self.state4 = None  # Evaporator inlet

        # Performance metrics
        self.m_dot_ref = None  # Refrigerant mass flow rate (kg/s)
        self.Q_evap = None  # Evaporator cooling capacity (W)
        self.W_comp = None  # Compressor power (W)
        self.Q_cond = None  # Condenser heat rejection (W)
        self.COP = None  # Coefficient of performance

    def solve(self, T_evap_C, T_cond_C, Q_evap_required):
        """
        Solve the refrigeration cycle for given evaporator and condenser temperatures.

        Args:
            T_evap_C: Evaporator saturation temperature (°C)
            T_cond_C: Condenser saturation temperature (°C)
            Q_evap_required: Required cooling capacity (W)

        Returns:
            dict: Complete cycle solution with all states and performance

        Raises:
            ValueError: If temperatures are invalid or cycle cannot be solved
        """
        if T_evap_C >= T_cond_C:
            raise ValueError(f"Evaporator temp {T_evap_C}°C must be < condenser temp {T_cond_C}°C")
        if Q_evap_required <= 0:
            raise ValueError(f"Cooling capacity must be positive, got {Q_evap_required}")

        # Calculate saturation pressures
        P_evap = PropsSI("P", "T", T_evap_C + 273.15, "Q", 1.0, self.refrigerant)
        P_cond = PropsSI("P", "T", T_cond_C + 273.15, "Q", 0.0, self.refrigerant)

        # State 1: Evaporator outlet (superheated vapor)
        T1_C = T_evap_C + self.superheat_evap
        self.state1 = RefrigerantState(self.refrigerant, P=P_evap, T=T1_C)

        # State 2s: Isentropic compression
        self.state2s = RefrigerantState(self.refrigerant, P=P_cond, s=self.state1.s)

        # State 2: Actual compression (with isentropic efficiency)
        h2_actual = self.state1.h + (self.state2s.h - self.state1.h) / self.eta_is_comp
        self.state2 = RefrigerantState(self.refrigerant, P=P_cond, h=h2_actual)

        # State 3: Condenser outlet (subcooled liquid)
        T3_C = T_cond_C - self.subcool_cond
        self.state3 = RefrigerantState(self.refrigerant, P=P_cond, T=T3_C)

        # State 4: After expansion valve (isenthalpic expansion)
        self.state4 = RefrigerantState(self.refrigerant, P=P_evap, h=self.state3.h)

        # Calculate refrigerant mass flow rate
        q_evap_per_kg = self.state1.h - self.state4.h  # J/kg
        self.m_dot_ref = Q_evap_required / q_evap_per_kg  # kg/s

        # Calculate performance
        self.Q_evap = Q_evap_required
        self.W_comp = self.m_dot_ref * (self.state2.h - self.state1.h)
        self.Q_cond = self.m_dot_ref * (self.state2.h - self.state3.h)
        self.COP = self.Q_evap / self.W_comp

        # Verify energy balance
        energy_balance_error = abs(self.Q_cond - (self.Q_evap + self.W_comp)) / self.Q_cond

        return {
            "refrigerant": self.refrigerant,
            "m_dot_ref_kg_s": self.m_dot_ref,
            "Q_evap_W": self.Q_evap,
            "W_comp_W": self.W_comp,
            "Q_cond_W": self.Q_cond,
            "COP": self.COP,
            "P_evap_Pa": P_evap,
            "P_cond_Pa": P_cond,
            "T_evap_C": T_evap_C,
            "T_cond_C": T_cond_C,
            "compression_ratio": P_cond / P_evap,
            "energy_balance_error": energy_balance_error,
            "state1": self.state1,
            "state2": self.state2,
            "state3": self.state3,
            "state4": self.state4,
        }

    def print_cycle_summary(self):
        """Print formatted cycle state point table and performance summary."""
        if self.state1 is None:
            print("Cycle not solved yet. Call solve() first.")
            return

        print("\n" + "=" * 90)
        print("VAPOR COMPRESSION REFRIGERATION CYCLE")
        print("=" * 90)
        print(f"\nRefrigerant: {self.refrigerant}")
        print(f"Compressor Isentropic Efficiency: {self.eta_is_comp*100:.1f}%")

        print("\n--- STATE POINTS ---")
        print(
            f"{'State':<10} {'Description':<25} {'P (kPa)':<12} {'T (°C)':<10} {'h (kJ/kg)':<12} {'Phase':<20}"
        )
        print("-" * 90)

        states = [
            (1, "Evaporator Out / Comp In", self.state1),
            ("2s", "Compressor Out (Isentropic)", self.state2s),
            (2, "Compressor Out (Actual)", self.state2),
            (3, "Condenser Out / Valve In", self.state3),
            (4, "Valve Out / Evaporator In", self.state4),
        ]

        for num, desc, state in states:
            print(
                f"{str(num):<10} {desc:<25} {state.P/1000:<12.1f} {state.T_C:<10.2f} "
                f"{state.h/1000:<12.2f} {state.phase:<20}"
            )

        print("\n--- PERFORMANCE ---")
        print(f"Refrigerant Mass Flow Rate:  {self.m_dot_ref:>10.3f} kg/s")
        print(f"Evaporator Capacity:          {self.Q_evap/1e6:>10.3f} MW")
        print(f"Compressor Power:             {self.W_comp/1e6:>10.3f} MW")
        print(f"Condenser Heat Rejection:     {self.Q_cond/1e6:>10.3f} MW")
        print(f"COP (Coefficient of Performance): {self.COP:>6.3f}")
        print(f"Compression Ratio (P_cond/P_evap): {self.state2.P/self.state1.P:>5.2f}")

        print("\n--- ENERGY BALANCE CHECK ---")
        error = abs(self.Q_cond - (self.Q_evap + self.W_comp)) / self.Q_cond * 100
        print(f"Q_cond vs (Q_evap + W_comp): {error:.6f}% error")

        print("=" * 90 + "\n")


class HeatExchanger:
    """
    Models counterflow heat exchanger between refrigerant and water/air.

    Uses effectiveness-NTU method for heat transfer analysis.
    """

    def __init__(self, effectiveness=0.85, fouling_resistance=0.0001):
        """
        Initialize heat exchanger.

        Args:
            effectiveness: Heat exchanger effectiveness (0-1)
            fouling_resistance: Fouling resistance (m²·K/W)

        Raises:
            ValueError: If parameters are invalid
        """
        if not 0.5 <= effectiveness <= 1.0:
            raise ValueError(f"Effectiveness {effectiveness} must be between 0.5 and 1.0")
        if fouling_resistance < 0:
            raise ValueError("Fouling resistance must be non-negative")

        self.effectiveness = effectiveness
        self.fouling_resistance = fouling_resistance

    def solve_counterflow(
        self, m_dot_hot, cp_hot, T_hot_in, m_dot_cold, cp_cold, T_cold_in, Q_target=None
    ):
        """
        Solve counterflow heat exchanger.

        Energy balance:
            Q = m_dot_hot * cp_hot * (T_hot_in - T_hot_out)
            Q = m_dot_cold * cp_cold * (T_cold_out - T_cold_in)

        Effectiveness:
            epsilon = Q_actual / Q_max
            Q_max = C_min * (T_hot_in - T_cold_in)

        Args:
            m_dot_hot: Hot side mass flow rate (kg/s)
            cp_hot: Hot side specific heat (J/kg·K)
            T_hot_in: Hot side inlet temperature (°C)
            m_dot_cold: Cold side mass flow rate (kg/s)
            cp_cold: Cold side specific heat (J/kg·K)
            T_cold_in: Cold side inlet temperature (°C)
            Q_target: Target heat transfer rate (W), if None uses effectiveness

        Returns:
            dict: Heat exchanger solution with outlet temperatures and heat transfer

        Raises:
            ValueError: If T_hot_in <= T_cold_in
        """
        if T_hot_in <= T_cold_in:
            raise ValueError(f"Hot inlet {T_hot_in}°C must be > cold inlet {T_cold_in}°C")

        # Calculate heat capacity rates
        C_hot = m_dot_hot * cp_hot
        C_cold = m_dot_cold * cp_cold
        C_min = min(C_hot, C_cold)
        C_max = max(C_hot, C_cold)
        C_ratio = C_min / C_max

        # Maximum possible heat transfer
        Q_max = C_min * (T_hot_in - T_cold_in)

        if Q_target is not None:
            # Given heat transfer, solve for outlet temperatures
            Q_actual = Q_target
            if Q_actual > Q_max:
                raise ValueError(f"Target Q={Q_actual/1e6:.3f} MW exceeds Q_max={Q_max/1e6:.3f} MW")

            T_hot_out = T_hot_in - Q_actual / C_hot
            T_cold_out = T_cold_in + Q_actual / C_cold

            # Calculate actual effectiveness
            epsilon_actual = Q_actual / Q_max

        else:
            # Use given effectiveness
            epsilon_actual = self.effectiveness
            Q_actual = epsilon_actual * Q_max

            T_hot_out = T_hot_in - Q_actual / C_hot
            T_cold_out = T_cold_in + Q_actual / C_cold

        # Calculate LMTD for reference
        delta_T1 = T_hot_in - T_cold_out
        delta_T2 = T_hot_out - T_cold_in

        if delta_T1 > 0 and delta_T2 > 0:
            import math

            if math.isclose(delta_T1, delta_T2, rel_tol=1e-9, abs_tol=1e-6):
                LMTD = delta_T1
            else:
                LMTD = (delta_T1 - delta_T2) / math.log(delta_T1 / delta_T2)
        else:
            LMTD = 0

        return {
            "Q_W": Q_actual,
            "Q_max_W": Q_max,
            "effectiveness": epsilon_actual,
            "T_hot_in_C": T_hot_in,
            "T_hot_out_C": T_hot_out,
            "T_cold_in_C": T_cold_in,
            "T_cold_out_C": T_cold_out,
            "LMTD_C": LMTD,
            "C_hot": C_hot,
            "C_cold": C_cold,
            "C_min": C_min,
            "C_ratio": C_ratio,
        }


def test_refrigeration_cycle():
    """Test refrigeration cycle with typical chiller conditions."""
    if not COOLPROP_AVAILABLE:
        print("CoolProp not available. Skipping test.")
        return

    print("\n" + "=" * 90)
    print("REFRIGERATION CYCLE TEST - Typical Water Chiller Conditions")
    print("=" * 90)

    # Create cycle
    cycle = VaporCompressionCycle(
        refrigerant="R134a", eta_is_comp=0.80, superheat_evap=5.0, subcool_cond=3.0
    )

    # Solve for typical chiller conditions
    # Evaporator: 5°C (chilled water at 10°C requires evap at ~5°C)
    # Condenser: 40°C (condenser water at 35°C requires cond at ~40°C)
    # Cooling capacity: 1 MW
    result = cycle.solve(T_evap_C=5.0, T_cond_C=40.0, Q_evap_required=1.0e6)  # 1 MW

    # Print results
    cycle.print_cycle_summary()

    # Test heat exchangers
    print("\n--- EVAPORATOR HEAT EXCHANGER ---")
    evap_hx = HeatExchanger(effectiveness=0.85)

    # Chilled water side: 15°C in, need to cool to 10°C, 47.8 kg/s for 1 MW
    m_dot_chw = 1.0e6 / (4186 * 5)  # kg/s
    evap_result = evap_hx.solve_counterflow(
        m_dot_hot=m_dot_chw,
        cp_hot=4186,
        T_hot_in=15.0,
        m_dot_cold=result["m_dot_ref_kg_s"],
        cp_cold=1400,  # Approximate for R134a liquid
        T_cold_in=result["state4"].T_C,
        Q_target=result["Q_evap_W"],
    )

    print(f"Chilled Water: {evap_result['T_hot_in_C']:.1f}°C → {evap_result['T_hot_out_C']:.1f}°C")
    print(f"Refrigerant: {evap_result['T_cold_in_C']:.1f}°C → {evap_result['T_cold_out_C']:.1f}°C")
    print(f"Heat Transfer: {evap_result['Q_W']/1e6:.3f} MW")
    print(f"Effectiveness: {evap_result['effectiveness']:.3f}")

    print("\n--- CONDENSER HEAT EXCHANGER ---")
    cond_hx = HeatExchanger(effectiveness=0.85)

    # Condenser water side: 29.5°C in, will heat up
    m_dot_cw = result["Q_cond_W"] / (4186 * 5.5)  # kg/s, assuming 5.5°C rise
    cond_result = cond_hx.solve_counterflow(
        m_dot_hot=result["m_dot_ref_kg_s"],
        cp_hot=1200,  # Approximate for R134a vapor
        T_hot_in=result["state2"].T_C,
        m_dot_cold=m_dot_cw,
        cp_cold=4186,
        T_cold_in=29.5,
        Q_target=result["Q_cond_W"],
    )

    print(f"Refrigerant: {cond_result['T_hot_in_C']:.1f}°C → {cond_result['T_hot_out_C']:.1f}°C")
    print(
        f"Condenser Water: {cond_result['T_cold_in_C']:.1f}°C → {cond_result['T_cold_out_C']:.1f}°C"
    )
    print(f"Heat Transfer: {cond_result['Q_W']/1e6:.3f} MW")
    print(f"Effectiveness: {cond_result['effectiveness']:.3f}")

    print("=" * 90 + "\n")


if __name__ == "__main__":
    test_refrigeration_cycle()
