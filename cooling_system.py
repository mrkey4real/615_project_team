"""
HVAC集成冷却系统 - 完整模块

这个文件包含了完整的HVAC系统建模，所有类都在这一个文件中。

包含的组件：
1. Psychrometrics - 湿空气热力学计算
2. Refrigerant Cycle - 制冷循环建模（蒸气压缩循环）
3. Chiller - 冷水机（基于制冷循环）
4. Cooling Tower - 冷却塔（基于湿空气热力学）
5. Pump System - 泵系统
6. Integrated HVAC System - 完整HVAC系统

使用方法：
    from cooling_system import IntegratedHVACSystem

    system = IntegratedHVACSystem(...)
    results = system.solve()

作者：HVAC Team
日期：2025-11-19
版本：v1.3 - 单文件完整版
"""

import math
from dataclasses import dataclass, is_dataclass, asdict
from typing import Dict, Optional

# ============================================================================
# CoolProp导入
# ============================================================================

try:
    from CoolProp.CoolProp import PropsSI
    COOLPROP_AVAILABLE = True
except ImportError:
    COOLPROP_AVAILABLE = False
    print("Warning: CoolProp not available. Install with: pip install CoolProp")


# ============================================================================
# 物理常数
# ============================================================================

CP_AIR = 1005.0         # J/(kg·K) 空气比热
RHO_AIR_25C = 1.184    # kg/m³ 25°C时空气密度
CP_WATER = 4186.0      # J/(kg·K) 水比热



# ============================================================================
# PSYCHROMETRICS - 湿空气热力学性质计算
# ============================================================================

class MoistAir:

    # Constants
    P_ATM = 101325  # Pa, standard atmospheric pressure
    R_DA = 287.055  # J/(kg·K), gas constant for dry air
    R_WV = 461.52  # J/(kg·K), gas constant for water vapor
    CP_DA = 1006  # J/(kg·K), specific heat of dry air at constant pressure
    CP_WV = 1860  # J/(kg·K), specific heat of water vapor at constant pressure
    H_FG_0 = 2501000  # J/kg, latent heat of vaporization at 0°C

    @staticmethod
    def saturation_pressure(T_C):
        if T_C < -20 or T_C > 50:
            raise ValueError(f"Temperature {T_C}°C out of valid range [-20, 50]°C")

        T_K = T_C + 273.15

        # Antoine equation coefficients for water (ASHRAE)
        if T_C >= 0:
            # Above freezing
            C1 = -5.8002206e3
            C2 = 1.3914993
            C3 = -4.8640239e-2
            C4 = 4.1764768e-5
            C5 = -1.4452093e-8
            C6 = 6.5459673
        else:
            # Below freezing (ice)
            C1 = -5.6745359e3
            C2 = 6.3925247
            C3 = -9.6778430e-3
            C4 = 6.2215701e-7
            C5 = 2.0747825e-9
            C6 = -9.4840240e-13

        ln_Pws = C1 / T_K + C2 + C3 * T_K + C4 * T_K**2 + C5 * T_K**3 + C6 * math.log(T_K)
        P_sat = math.exp(ln_Pws)

        return P_sat

    @staticmethod
    def humidity_ratio_from_RH(T_C, RH, P=P_ATM):
        """
        Calculate humidity ratio from temperature and relative humidity.

        w = 0.622 * P_v / (P - P_v)
        where P_v = RH * P_sat(T)

        Args:
            T_C: Dry bulb temperature (°C)
            RH: Relative humidity (0-1, not percentage)
            P: Atmospheric pressure (Pa)

        Returns:
            w: Humidity ratio (kg_water/kg_dry_air)

        Raises:
            ValueError: If inputs are invalid
        """
        if not 0.0 <= RH <= 1.0:
            raise ValueError(f"RH must be between 0 and 1, got {RH}")
        if P <= 0:
            raise ValueError(f"Pressure must be positive, got {P}")

        P_sat = MoistAir.saturation_pressure(T_C)
        P_v = RH * P_sat

        if P_v >= P:
            raise ValueError(f"Vapor pressure {P_v} Pa exceeds total pressure {P} Pa")

        w = 0.622 * P_v / (P - P_v)
        return w

    @staticmethod
    def humidity_ratio_from_Twb(T_db_C, T_wb_C, P=P_ATM):
        """
        Calculate humidity ratio from dry bulb and wet bulb temperatures.

        Uses iterative solution of psychrometric equation:
        w = (h_sat(T_wb) - cp_da*(T_db - T_wb)) / (h_fg + cp_wv*T_db)

        Args:
            T_db_C: Dry bulb temperature (°C)
            T_wb_C: Wet bulb temperature (°C)
            P: Atmospheric pressure (Pa)

        Returns:
            w: Humidity ratio (kg_water/kg_dry_air)

        Raises:
            ValueError: If T_wb > T_db
        """
        if T_wb_C > T_db_C:
            raise ValueError(f"Wet bulb temp {T_wb_C}°C cannot exceed dry bulb {T_db_C}°C")

        # Saturation humidity ratio at wet bulb temperature
        P_sat_wb = MoistAir.saturation_pressure(T_wb_C)
        w_sat_wb = 0.622 * P_sat_wb / (P - P_sat_wb)

        # Psychrometric equation (simplified, assuming Lewis number = 1)
        h_fg = MoistAir.H_FG_0 - 2400 * T_wb_C  # Approximate variation with temp

        numerator = w_sat_wb * h_fg - MoistAir.CP_DA * (T_db_C - T_wb_C)
        denominator = h_fg + MoistAir.CP_WV * T_db_C

        w = numerator / denominator

        # Ensure non-negative and physical
        w = max(0.0, min(w, w_sat_wb))

        return w

    @staticmethod
    def enthalpy(T_C, w):
        """
        Calculate specific enthalpy of moist air.

        h = cp_da * T + w * (h_fg0 + cp_wv * T)

        Args:
            T_C: Dry bulb temperature (°C)
            w: Humidity ratio (kg_water/kg_dry_air)

        Returns:
            h: Specific enthalpy (J/kg_dry_air)

        Raises:
            ValueError: If w is negative
        """
        if w < 0:
            raise ValueError(f"Humidity ratio must be non-negative, got {w}")

        h = MoistAir.CP_DA * T_C + w * (MoistAir.H_FG_0 + MoistAir.CP_WV * T_C)
        return h

    @staticmethod
    def specific_volume(T_C, w, P=P_ATM):
        """
        Calculate specific volume of moist air.

        v = (R_da * T) / P * (1 + 1.608 * w)

        Args:
            T_C: Temperature (°C)
            w: Humidity ratio (kg_water/kg_dry_air)
            P: Pressure (Pa)

        Returns:
            v: Specific volume (m³/kg_dry_air)
        """
        T_K = T_C + 273.15
        v = (MoistAir.R_DA * T_K / P) * (1 + 1.608 * w)
        return v

    @staticmethod
    def density(T_C, w, P=P_ATM):
        """
        Calculate density of moist air.

        rho = 1/v where v is specific volume

        Args:
            T_C: Temperature (°C)
            w: Humidity ratio (kg_water/kg_dry_air)
            P: Pressure (Pa)

        Returns:
            rho: Density (kg_dry_air/m³)
        """
        v = MoistAir.specific_volume(T_C, w, P)
        return 1.0 / v

    @staticmethod
    def relative_humidity(T_C, w, P=P_ATM):
        """
        Calculate relative humidity from temperature and humidity ratio.

        Args:
            T_C: Temperature (°C)
            w: Humidity ratio (kg_water/kg_dry_air)
            P: Pressure (Pa)

        Returns:
            RH: Relative humidity (0-1)
        """
        P_sat = MoistAir.saturation_pressure(T_C)
        P_v = w * P / (0.622 + w)
        RH = P_v / P_sat
        return min(1.0, max(0.0, RH))


class PsychrometricState:
    """
    Represents a complete thermodynamic state of moist air.

    Given two independent properties, all other properties are calculated.
    """

    def __init__(self, T_db_C=None, T_wb_C=None, w=None, RH=None, h=None, P=MoistAir.P_ATM):
        """
        Initialize psychrometric state from two independent properties.

        Valid combinations:
        - T_db and T_wb (dry bulb and wet bulb)
        - T_db and w (dry bulb and humidity ratio)
        - T_db and RH (dry bulb and relative humidity)
        - T_db and h (dry bulb and enthalpy)

        Args:
            T_db_C: Dry bulb temperature (°C)
            T_wb_C: Wet bulb temperature (°C)
            w: Humidity ratio (kg_water/kg_dry_air)
            RH: Relative humidity (0-1)
            h: Specific enthalpy (J/kg_dry_air)
            P: Atmospheric pressure (Pa)

        Raises:
            ValueError: If invalid combination of properties provided
        """
        self.P = P

        # Count how many properties are specified
        specified = sum([x is not None for x in [T_db_C, T_wb_C, w, RH, h]])

        if T_db_C is None:
            raise ValueError("T_db_C (dry bulb temperature) is required")

        if specified < 2:
            raise ValueError("At least two properties must be specified")

        self.T_db = T_db_C

        # Calculate humidity ratio from available properties
        if w is not None:
            self.w = w
        elif RH is not None:
            self.w = MoistAir.humidity_ratio_from_RH(T_db_C, RH, P)
        elif T_wb_C is not None:
            self.w = MoistAir.humidity_ratio_from_Twb(T_db_C, T_wb_C, P)
        elif h is not None:
            # Solve for w from h = cp_da * T + w * (h_fg0 + cp_wv * T)
            numerator = h - MoistAir.CP_DA * T_db_C
            denominator = MoistAir.H_FG_0 + MoistAir.CP_WV * T_db_C
            self.w = numerator / denominator
        else:
            raise ValueError("Need one of: w, RH, T_wb, or h in addition to T_db")

        # Calculate all other properties
        self.h = MoistAir.enthalpy(self.T_db, self.w)
        self.RH = MoistAir.relative_humidity(self.T_db, self.w, P)
        self.v = MoistAir.specific_volume(self.T_db, self.w, P)
        self.rho = MoistAir.density(self.T_db, self.w, P)

        # Store wet bulb if provided, otherwise leave as None
        self.T_wb = T_wb_C

    def __repr__(self):
        """String representation of psychrometric state."""
        return (
            f"PsychrometricState(T_db={self.T_db:.1f}°C, "
            f"w={self.w:.6f} kg/kg, RH={self.RH*100:.1f}%, "
            f"h={self.h:.0f} J/kg)"
        )


def test_psychrometrics():
    """
    Test psychrometric calculations with known values.
    """
    print("\n" + "=" * 70)
    print("PSYCHROMETRIC PROPERTIES TEST")
    print("=" * 70)

    # Test case 1: Standard conditions (25°C, 50% RH)
    print("\nTest 1: Standard conditions (25°C, 50% RH)")
    state1 = PsychrometricState(T_db_C=25.0, RH=0.5)
    print(f"  T_db = {state1.T_db:.1f}°C")
    print(f"  RH = {state1.RH*100:.1f}%")
    print(f"  w = {state1.w:.6f} kg/kg")
    print(f"  h = {state1.h:.1f} J/kg")
    print(f"  rho = {state1.rho:.4f} kg/m³")

    # Test case 2: Saturated air (30°C, 100% RH)
    print("\nTest 2: Saturated air (30°C, 100% RH)")
    state2 = PsychrometricState(T_db_C=30.0, RH=1.0)
    print(f"  T_db = {state2.T_db:.1f}°C")
    print(f"  RH = {state2.RH*100:.1f}%")
    print(f"  w = {state2.w:.6f} kg/kg")
    print(f"  h = {state2.h:.1f} J/kg")

    # Test case 3: From T_db and T_wb
    print("\nTest 3: From dry bulb and wet bulb (35°C db, 25°C wb)")
    state3 = PsychrometricState(T_db_C=35.0, T_wb_C=25.0)
    print(f"  T_db = {state3.T_db:.1f}°C")
    print(f"  T_wb = {state3.T_wb:.1f}°C")
    print(f"  w = {state3.w:.6f} kg/kg")
    print(f"  RH = {state3.RH*100:.1f}%")
    print(f"  h = {state3.h:.1f} J/kg")

    print("\n" + "=" * 70 + "\n")


# ============================================================================
# REFRIGERANT CYCLE - 蒸气压缩制冷循环建模
# ============================================================================

try:

    COOLPROP_AVAILABLE = True
except ImportError:
    COOLPROP_AVAILABLE = False
    print("Warning: CoolProp not available. Install with: pip install CoolProp")


class RefrigerantState:

    def __init__(self, refrigerant, **kwargs):
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


# ============================================================================
# CHILLER - 冷水机模块
# ============================================================================

class Chiller:

    def __init__(
        self,
        rated_capacity_mw,
        rated_cop,
        t_chw_supply,
        refrigerant="R134a",
        eta_is_comp=0.80,
        evap_effectiveness=0.85,
        cond_effectiveness=0.85,
        curves_file=None,
    ):
        """
        Initialize chiller module with full thermodynamic cycle modeling.

        Args:
            rated_capacity_mw: Rated cooling capacity (MW)
            rated_cop: COP at rated conditions (for validation)
            t_chw_supply: Chilled water supply temperature (°C)
            refrigerant: Refrigerant type (default 'R134a')
            eta_is_comp: Compressor isentropic efficiency (0-1)
            evap_effectiveness: Evaporator heat exchanger effectiveness (0-1)
            cond_effectiveness: Condenser heat exchanger effectiveness (0-1)
            curves_file: Deprecated (kept for backward compatibility)

        Raises:
            ValueError: If parameters are invalid
            ImportError: If CoolProp is not available
        """
        if not COOLPROP_AVAILABLE:
            raise ImportError(
                "CoolProp is required for refrigeration cycle modeling. "
                "Install with: pip install CoolProp"
            )

        if rated_capacity_mw <= 0:
            raise ValueError(f"Invalid rated_capacity_mw: {rated_capacity_mw}, must be > 0")
        if rated_cop <= 0 or rated_cop > 10:
            raise ValueError(f"Invalid rated_cop: {rated_cop}, must be between 0 and 10")
        if t_chw_supply < 0 or t_chw_supply >= 30:
            raise ValueError(f"Invalid t_chw_supply: {t_chw_supply}, must be between 0 and 30 °C")

        self.rated_capacity = rated_capacity_mw * 1e6  # W
        self.rated_cop = rated_cop
        self.t_chw_supply = t_chw_supply
        self.cp_water = 4186  # J/(kg·K)

        # Refrigeration cycle components
        self.refrigerant = refrigerant
        self.ref_cycle = VaporCompressionCycle(
            refrigerant=refrigerant,
            eta_is_comp=eta_is_comp,
            superheat_evap=5.0,  # 5°C superheat at evaporator outlet
            subcool_cond=3.0,  # 3°C subcooling at condenser outlet
        )

        # Heat exchangers
        self.evap_hx = HeatExchanger(effectiveness=evap_effectiveness)
        self.cond_hx = HeatExchanger(effectiveness=cond_effectiveness)

        # Approximate specific heats for refrigerant (will be refined in calculations)
        self.cp_ref_liquid = 1400  # J/(kg·K), approximate for R134a liquid
        self.cp_ref_vapor = 1200  # J/(kg·K), approximate for R134a vapor

    def solve_energy_balance(
        self, q_evap, m_dot_chw, m_dot_cw, t_cw_in, t_chw_return=None, max_iter=20, tolerance=0.1
    ):
        """
        Solve complete chiller energy balance using refrigeration cycle and HX models.

        Iterative solution procedure:
        1. Estimate evaporator and condenser temperatures
        2. Solve refrigeration cycle for refrigerant states
        3. Solve evaporator HX: match refrigerant-side and water-side energy
        4. Solve condenser HX: match refrigerant-side and water-side energy
        5. Update evaporator/condenser temperatures
        6. Check convergence
        7. Repeat until converged

        Args:
            q_evap: Required evaporator cooling capacity (W)
            m_dot_chw: Chilled water flow rate (kg/s)
            m_dot_cw: Condenser water flow rate (kg/s)
            t_cw_in: Condenser water inlet temperature (°C)
            t_chw_return: Chilled water return temperature (°C), if None calculated from Q
            max_iter: Maximum iterations for convergence
            tolerance: Convergence tolerance for temperatures (°C)

        Returns:
            dict: Complete thermodynamic state information

        Raises:
            ValueError: If parameters are invalid or solution doesn't converge
        """
        if q_evap <= 0:
            raise ValueError(f"Invalid q_evap: {q_evap}, must be > 0")
        if m_dot_chw <= 0:
            raise ValueError(f"Invalid m_dot_chw: {m_dot_chw}, must be > 0")
        if m_dot_cw <= 0:
            raise ValueError(f"Invalid m_dot_cw: {m_dot_cw}, must be > 0")

        # Calculate chilled water return temperature if not provided
        if t_chw_return is None:
            delta_t_chw = q_evap / (m_dot_chw * self.cp_water)
            t_chw_return = self.t_chw_supply + delta_t_chw

        # Initial guess for evaporator and condenser temperatures
        # Evaporator sat temp ~5°C below CHW supply to allow heat transfer
        T_evap = self.t_chw_supply - 5.0
        # Condenser sat temp ~5°C above CW inlet to allow heat transfer
        T_cond = t_cw_in + 5.0

        # Iterative solution
        for iteration in range(max_iter):
            T_evap_old = T_evap
            T_cond_old = T_cond

            # Step 1: Solve refrigeration cycle
            try:
                cycle_result = self.ref_cycle.solve(
                    T_evap_C=T_evap, T_cond_C=T_cond, Q_evap_required=q_evap
                )
            except Exception as e:
                raise ValueError(
                    f"Refrigeration cycle solution failed at iteration {iteration}: {e}"
                )

            m_dot_ref = cycle_result["m_dot_ref_kg_s"]
            q_cond_ref = cycle_result["Q_cond_W"]
            w_comp = cycle_result["W_comp_W"]

            # Step 2: Verify evaporator energy balance and pinch points
            # Water side: being cooled from t_chw_return to t_chw_supply
            # Refrigerant side: evaporating at T_evap, then superheating
            T_ref_evap_out = self.ref_cycle.state1.T_C  # Superheated vapor out

            # Check pinch point: evaporator sat temp should be below CHW supply
            pinch_evap = self.t_chw_supply - T_evap
            if pinch_evap < 3.0:  # Minimum pinch
                T_evap -= 0.5  # Decrease evap temp to increase pinch
            elif pinch_evap > 8.0:  # Too much pinch
                T_evap += 0.3  # Increase evap temp

            # Step 3: Calculate condenser water outlet temperature
            # Refrigerant side: desuperheating, condensing, subcooling
            # Water side: being heated from t_cw_in
            T_ref_cond_in = self.ref_cycle.state2.T_C  # Superheated vapor in
            T_ref_cond_out = self.ref_cycle.state3.T_C  # Subcooled liquid out

            # Water side energy balance
            t_cw_out = t_cw_in + q_cond_ref / (m_dot_cw * self.cp_water)

            # Check pinch point: condenser sat temp should be above CW outlet
            pinch_cond = T_cond - t_cw_out
            if pinch_cond < 3.0:  # Minimum pinch
                T_cond += 0.5  # Increase cond temp to increase pinch
            elif pinch_cond > 8.0:  # Too much pinch
                T_cond -= 0.3  # Decrease cond temp

            # Heat exchanger effectiveness (informational)
            evap_effectiveness = 0.85  # Typical value
            cond_effectiveness = 0.85  # Typical value

            # Check convergence
            delta_T_evap = abs(T_evap - T_evap_old)
            delta_T_cond = abs(T_cond - T_cond_old)

            if delta_T_evap < tolerance and delta_T_cond < tolerance:
                # Converged
                cop = cycle_result["COP"]
                plr = q_evap / self.rated_capacity

                return {
                    "component": "Chiller (Thermodynamic Cycle)",
                    "refrigerant": self.refrigerant,
                    "converged": True,
                    "iterations": iteration + 1,
                    # Performance
                    "Q_evap_MW": q_evap / 1e6,
                    "Q_cond_MW": q_cond_ref / 1e6,
                    "W_comp_MW": w_comp / 1e6,
                    "COP": cop,
                    "PLR": plr,
                    # Chilled water side
                    "T_chw_supply_C": self.t_chw_supply,
                    "T_chw_return_C": t_chw_return,
                    "delta_T_chw_C": t_chw_return - self.t_chw_supply,
                    "m_dot_chw_kg_s": m_dot_chw,
                    # Condenser water side
                    "T_cw_in_C": t_cw_in,
                    "T_cw_out_C": t_cw_out,
                    "delta_T_cw_C": t_cw_out - t_cw_in,
                    "m_dot_cw_kg_s": m_dot_cw,
                    # Refrigerant side
                    "T_evap_sat_C": T_evap,
                    "T_cond_sat_C": T_cond,
                    "m_dot_ref_kg_s": m_dot_ref,
                    "P_evap_kPa": cycle_result["P_evap_Pa"] / 1000,
                    "P_cond_kPa": cycle_result["P_cond_Pa"] / 1000,
                    "compression_ratio": cycle_result["compression_ratio"],
                    # Energy balance check
                    "energy_balance_error_pct": abs(q_cond_ref - (q_evap + w_comp))
                    / q_cond_ref
                    * 100,
                    # Heat exchanger effectiveness
                    "evap_effectiveness": evap_effectiveness,
                    "cond_effectiveness": cond_effectiveness,
                }

        # Did not converge
        raise ValueError(
            f"Chiller solution did not converge after {max_iter} iterations. "
            f"Last changes: ΔT_evap={delta_T_evap:.3f}°C, ΔT_cond={delta_T_cond:.3f}°C"
        )


# ============================================================================
# COOLING TOWER - 冷却塔模块
# ============================================================================

class CoolingTower:

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


# ============================================================================
# PUMP SYSTEM - 泵系统模块
# ============================================================================

class Pump:

    def __init__(
        self,
        pump_type,
        static_head=10.0,
        dynamic_head_factor=0.5,
        equipment_head=5.0,
        efficiency=0.85,
    ):
        if static_head < 0 or static_head > 100:
            raise ValueError(f"Invalid static_head: {static_head}, must be between 0 and 100 m")
        if equipment_head < 0 or equipment_head > 50:
            raise ValueError(
                f"Invalid equipment_head: {equipment_head}, must be between 0 and 50 m"
            )
        if efficiency <= 0 or efficiency > 1.0:
            raise ValueError(f"Invalid efficiency: {efficiency}, must be between 0 and 1.0")

        self.pump_type = pump_type
        self.static_head = static_head  # m
        self.dynamic_head_factor = dynamic_head_factor
        self.equipment_head = equipment_head  # m
        self.efficiency = efficiency
        self.g = 9.81  # m/s², gravitational acceleration
        self.rho_water = 998  # kg/m³, water density at ~20°C

    def calculate_dynamic_head(self, velocity):
        """
        Calculate dynamic head (velocity head).

        H_dynamic = (v²/2g) × factor

        Args:
            velocity: Flow velocity (m/s)

        Returns:
            H_dynamic: Dynamic head (m)
        """
        velocity_head = velocity**2 / (2 * self.g)
        return velocity_head * self.dynamic_head_factor

    def calculate_total_head(self, velocity=None, dynamic_head=None):
        """
        Calculate total pump head.

        H_total = H_static + H_dynamic + H_equipment

        Args:
            velocity: Flow velocity (m/s), optional if dynamic_head provided
            dynamic_head: Dynamic head (m), optional if velocity provided

        Returns:
            H_total: Total head (m)
        """
        # Calculate dynamic head if not provided
        if dynamic_head is None:
            if velocity is not None:
                dynamic_head = self.calculate_dynamic_head(velocity)
            else:
                # Default assumption: low velocity, ~2 m/s typical
                dynamic_head = self.calculate_dynamic_head(2.0)

        H_total = self.static_head + dynamic_head + self.equipment_head
        return H_total

    def calculate_power(self, m_dot, density=None, H_total=None, velocity=None):
        """
        Calculate pump power consumption.

        P_pump = (ρ × g × H × Q) / η
        where Q = ṁ / ρ

        Args:
            m_dot: Mass flow rate (kg/s)
            density: Fluid density (kg/m³), default is water at 20°C
            H_total: Total head (m), if None will calculate from velocity
            velocity: Flow velocity (m/s), used if H_total not provided

        Returns:
            P_pump: Pump power (W)

        Raises:
            ValueError: If m_dot is invalid
        """
        if m_dot <= 0:
            raise ValueError(f"Invalid m_dot: {m_dot}, must be > 0")

        # Use default water density if not specified
        if density is None:
            density = self.rho_water

        # Calculate volume flow rate
        Q = m_dot / density  # m³/s

        # Calculate total head if not provided
        if H_total is None:
            H_total = self.calculate_total_head(velocity=velocity)

        # Calculate pump power
        # P = (ρ × g × H × Q) / η
        P_pump = (density * self.g * H_total * Q) / self.efficiency

        return P_pump

    def calculate_power_simple(self, q_thermal, power_fraction):
        """
        Calculate pump power using simple fraction of thermal load.

        This is a simplified method based on industry guidelines.
        Used for quick estimates when detailed hydraulic info not available.

        Typical fractions:
        - Chilled water pumps: 2-3% of cooling load
        - Condenser water pumps: 1.5-2% of cooling load
        - GPU coolant pumps: 1-2% of GPU load

        Args:
            q_thermal: Thermal load (W)
            power_fraction: Power as fraction of thermal load (-)

        Returns:
            P_pump: Pump power (W)
        """
        return q_thermal * power_fraction

    def solve(self, m_dot, density=None, velocity=None):
        """
        Solve pump performance for given flow conditions.

        Args:
            m_dot: Mass flow rate (kg/s)
            density: Fluid density (kg/m³)
            velocity: Flow velocity (m/s), optional

        Returns:
            dict: Complete pump performance data
        """
        if density is None:
            density = self.rho_water

        # Calculate parameters
        Q = m_dot / density  # m³/s
        H_total = self.calculate_total_head(velocity=velocity)
        P_pump = self.calculate_power(m_dot, density=density, H_total=H_total)

        # Calculate energy transfer to fluid
        E_fluid = m_dot * self.g * H_total  # W

        return {
            "component": f"Pump ({self.pump_type})",
            "m_dot_kg_s": m_dot,
            "Q_m3_s": Q,
            "Q_L_s": Q * 1000,
            "density_kg_m3": density,
            "H_static_m": self.static_head,
            "H_equipment_m": self.equipment_head,
            "H_total_m": H_total,
            "efficiency": self.efficiency,
            "P_pump_W": P_pump,
            "P_pump_kW": P_pump / 1000,
            "P_pump_MW": P_pump / 1e6,
            "E_fluid_W": E_fluid,
            "energy_efficiency": E_fluid / P_pump if P_pump > 0 else 0,
        }


class PumpSystem:
    """
    Models HVAC-side pump system (condenser water loop only).

    IMPORTANT: This class only includes the condenser water (CW) pump,
    which is the pump in the HVAC system between the chiller condenser
    and the cooling tower.

    The following pumps are NOT included (managed by other systems):
    - CHW pump: Managed by building-side system
    - GPU pump: Managed by compute/GPU cooling system

    Scope:
    - Condenser water pumps (CW loop): Chiller condenser ↔ Cooling tower
    """

    def __init__(
        self,
        cw_static_head=10.0,
        cw_efficiency=0.85,
    ):
        """
        Initialize HVAC pump system (CW pump only).

        Args:
            cw_static_head: Condenser water pump static head (m)
            cw_efficiency: Condenser water pump efficiency (0-1)
        """
        # Condenser water pump (only pump managed by HVAC system)
        self.cw_pump = Pump(
            pump_type="CW",
            static_head=cw_static_head,
            equipment_head=6.0,  # Chiller condenser, cooling tower
            efficiency=cw_efficiency,
        )

    def solve(self, m_dot_cw):
        """
        Solve condenser water pump.

        Args:
            m_dot_cw: Condenser water flow rate (kg/s)

        Returns:
            dict: CW pump performance data
        """
        # Solve CW pump
        cw_result = self.cw_pump.solve(m_dot_cw)

        return {
            "component": "HVAC Pump System (CW Loop)",
            "CW_pump": cw_result,
            "P_pump_W": cw_result["P_pump_W"],
            "P_pump_kW": cw_result["P_pump_kW"],
            "P_pump_MW": cw_result["P_pump_MW"],
        }


# ============================================================================
# INTEGRATED HVAC SYSTEM - 完整HVAC集成系统
# ============================================================================

# ---- Physical constants ----
CP_AIR = 1005.0
RHO_AIR_25C = 1.184
CP_WATER = 4186.0


# --------- JSON serialization helper ---------
def to_jsonable(obj):
    try:
        import numpy as _np
    except Exception:
        _np = None


    # Base types
    if obj is None or isinstance(obj, (str, int, float, bool)):
        # Normalize numpy scalars if they sneak in
        return float(obj) if isinstance(obj, float) else obj

    # Numpy scalars
    if _np is not None and isinstance(obj, _np.generic):
        return obj.item()

    # Containers
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {to_jsonable(k): to_jsonable(v) for k, v in obj.items()}

    # Dataclasses
    if is_dataclass(obj):
        return to_jsonable(asdict(obj))

    # Objects: try attribute dict, otherwise str()
    # Filter out private/callable attributes
    out = {}
    for name in dir(obj):
        if name.startswith("_"):
            continue
        try:
            val = getattr(obj, name)
        except Exception:
            continue
        if callable(val):
            continue
        try:
            out[name] = to_jsonable(val)
        except Exception:
            out[name] = str(val)
    if out:
        return out

    return str(obj)


# ---------------- Air Pump ----------------
@dataclass
class AirPump:                                                          # Ruikang's Airpump
    power_W: float = 200_000.0
    delta_p_Pa: float = 800.0
    efficiency: float = 0.6
    rho_air: float = RHO_AIR_25C

    def mass_flow_rate(self) -> float:
        if self.delta_p_Pa <= 0 or self.efficiency <= 0:
            raise ValueError("delta_p_Pa and efficiency must be positive.")
        Q_v = self.power_W * self.efficiency / self.delta_p_Pa
        return self.rho_air * Q_v


# ------------- Air-Cooled Equipment -------------
@dataclass
class AirCooledEquipment:                                                       # Ruikang's AC
    q_in_W: float = 100e6
    t_air_in_C: float = 20.0
    t_air_max_C: float = 25.0
    cp_air: float = CP_AIR

    def solve(self, m_dot_air_kg_s: float) -> Dict[str, float]:
        if m_dot_air_kg_s <= 0:
            raise ValueError("Air mass flow must be positive.")
        dT_required = self.q_in_W / (self.cp_air * m_dot_air_kg_s)
        t_out_no_cap = self.t_air_in_C + dT_required
        if t_out_no_cap <= self.t_air_max_C:
            t_out = t_out_no_cap
            q_abs = self.q_in_W
            q_unmet = 0.0
        else:
            t_out = self.t_air_max_C
            q_abs = (t_out - self.t_air_in_C) * self.cp_air * m_dot_air_kg_s
            q_unmet = max(self.q_in_W - q_abs, 0.0)
        return {
            "m_dot_air_kg_s": m_dot_air_kg_s,
            "T_in_air_C": self.t_air_in_C,
            "T_out_air_C": t_out,
            "Q_in_W": self.q_in_W,
            "Q_absorbed_W": q_abs,
            "Q_unmet_W": q_unmet,
        }


# ------------- Building Heat Exchanger (ε-model) -------------
@dataclass
class BuildingHeatExchanger:                                                        #Ruikang's BD HX
    m_dot_hot_kg_s: float
    cp_hot_J_kgK: float
    t_hot_in_C: float
    m_dot_cold_kg_s: float
    cp_cold_J_kgK: float
    t_cold_in_C: float
    effectiveness: float = 0.75

    def solve(self) -> Dict[str, float]:
        if not (0.0 < self.effectiveness <= 1.0):
            raise ValueError("effectiveness must be in (0,1].")
        C_hot = self.m_dot_hot_kg_s * self.cp_hot_J_kgK
        C_cold = self.m_dot_cold_kg_s * self.cp_cold_J_kgK
        C_min = min(C_hot, C_cold)
        Q_max = C_min * max(self.t_hot_in_C - self.t_cold_in_C, 0.0)
        Q = self.effectiveness * Q_max
        t_hot_out = self.t_hot_in_C - Q / C_hot if C_hot > 0 else self.t_hot_in_C
        t_cold_out = self.t_cold_in_C + Q / C_cold if C_cold > 0 else self.t_cold_in_C
        return {
            "Q_transferred_W": Q,
            "T_hot_in_C": self.t_hot_in_C,
            "T_hot_out_C": t_hot_out,
            "T_cold_in_C": self.t_cold_in_C,
            "T_cold_out_C": t_cold_out,
            "m_dot_hot_kg_s": self.m_dot_hot_kg_s,
            "m_dot_cold_kg_s": self.m_dot_cold_kg_s,
        }


# ------------- Simple COP-based Chiller -------------
@dataclass
class SimpleChiller:                                                                    # ZQ's Chiller
    rated_cop: float = 6.0
    t_chw_supply_C: float = 7.0
    cp_water: float = CP_WATER

    def solve_energy_balance(self, q_evap_W: float, m_dot_chw_kg_s: float, m_dot_cw_kg_s: float, t_cw_in_C: float,
                             t_chw_return_C: Optional[float] = None) -> Dict[str, float]:
        if q_evap_W <= 0:
            raise ValueError("q_evap_W must be positive.")
        p_comp = q_evap_W / max(self.rated_cop, 1e-6)
        q_cond = q_evap_W + p_comp
        t_chw_out = self.t_chw_supply_C + q_evap_W / (self.cp_water * max(m_dot_chw_kg_s, 1e-9))
        t_cw_out = t_cw_in_C + q_cond / (self.cp_water * max(m_dot_cw_kg_s, 1e-9))
        return {
            "component": "SimpleChiller (COP-based)",
            "Q_evap_W": q_evap_W,
            "Q_cond_W": q_cond,
            "T_chw_in_C": self.t_chw_supply_C,
            "T_chw_out_C": t_chw_out,
            "m_dot_chw_kg_s": m_dot_chw_kg_s,
            "T_cw_in_C": t_cw_in_C,
            "T_cw_out_C": t_cw_out,
            "m_dot_cw_kg_s": m_dot_cw_kg_s,
            "P_comp_W": p_comp,
        }


# --------- Helper: normalize chiller output keys to SI (W) ---------
def _normalize_chiller_out(ch_out: dict) -> dict:
    """Return a dict with standardized keys in SI (W, °C) regardless of source chiller."""
    out = dict(ch_out) if ch_out else {}
    # Map heats/power to W
    if "Q_cond_W" not in out and "Q_cond_MW" in out:
        out["Q_cond_W"] = out["Q_cond_MW"] * 1e6
    if "Q_evap_W" not in out and "Q_evap_MW" in out:
        out["Q_evap_W"] = out["Q_evap_MW"] * 1e6
    if "P_comp_W" not in out and "W_comp_MW" in out:
        out["P_comp_W"] = out["W_comp_MW"] * 1e6

    # Normalize CHW labels
    if "T_chw_in_C" not in out and "T_chw_supply_C" in out:
        out["T_chw_in_C"] = out["T_chw_supply_C"]
    if "T_chw_out_C" not in out and "T_chw_return_C" in out:
        out["T_chw_out_C"] = out["T_chw_return_C"]

    # Keep condenser water temps as-is (both versions use *_C keys)
    return out


# --------- Imports of team modules (optional) ---------
_COOLING_SYSTEM_AVAILABLE = False
try:

    _COOLING_SYSTEM_AVAILABLE = True
except Exception:
    pass


# ------------- Integrated System -------------
@dataclass
class IntegratedHVACSystem:
    pump_power_W: float = 200_000.0
    air_delta_p_Pa: float = 800.0
    air_eta: float = 0.6
    t_air_in_C: float = 20.0
    q_air_load_W: float = 100e6
    t_air_max_C: float = 25.0

    t_chw_supply_C: float = 7.0
    deltaT_chw_design_C: float = 5.0
    hx_effectiveness: float = 0.75

    t_wb_C: float = 24.0
    t_db_C: Optional[float] = None

    chiller_cop: float = 6.0

    max_iter: int = 50
    tol_C: float = 0.05

    def solve(self) -> Dict[str, Dict]:
        """
        Solve complete HVAC system including air loop, building HX, and cooling system.

        Returns:
            dict with two main sections:
                - for_heat_exchanger: Interface values for heat exchanger/building
                - internal_diagnostics: Detailed component states for monitoring
        """
        # ===== AIR LOOP =====
        air_pump = AirPump(self.pump_power_W, self.air_delta_p_Pa, self.air_eta, RHO_AIR_25C)
        m_dot_air = air_pump.mass_flow_rate()

        ace = AirCooledEquipment(self.q_air_load_W, self.t_air_in_C, self.t_air_max_C, CP_AIR)
        ace_result = ace.solve(m_dot_air_kg_s=m_dot_air)
        q_hot_to_hx = ace_result["Q_absorbed_W"]
        t_hot_in = ace_result["T_out_air_C"]

        # ===== BUILDING HEAT EXCHANGER =====
        # Estimate CHW flow based on load
        m_dot_chw_guess = max(q_hot_to_hx, 1e-3) / (CP_WATER * max(self.deltaT_chw_design_C, 1e-6))

        hx = BuildingHeatExchanger(
            m_dot_hot_kg_s=m_dot_air,
            cp_hot_J_kgK=CP_AIR,
            t_hot_in_C=t_hot_in,
            m_dot_cold_kg_s=m_dot_chw_guess,
            cp_cold_J_kgK=CP_WATER,
            t_cold_in_C=self.t_chw_supply_C,
            effectiveness=self.hx_effectiveness,
        )
        hx_result = hx.solve()

        q_evap = hx_result["Q_transferred_W"]
        t_chw_return = hx_result["T_cold_out_C"]
        m_dot_chw = hx_result["m_dot_cold_kg_s"]

        # ===== COOLING SYSTEM (Chiller + Tower) =====
        if not _COOLING_SYSTEM_AVAILABLE:
            raise ImportError(
                "cooling_system module missing. Please ensure cooling_system.py is available."
            )

        cooling_sys = CoolingSystem(
            chiller_capacity_MW=q_evap / 1e6,  # Size to load
            chiller_cop=self.chiller_cop,
            t_chw_supply_C=self.t_chw_supply_C,
            tower_approach_C=4.0,
            tower_coc=4.0,
        )

        cooling_result = cooling_sys.solve(
            q_cooling_load_W=q_evap,
            m_dot_chw_kg_s=m_dot_chw,
            t_chw_return_C=t_chw_return,
            t_wb_ambient_C=self.t_wb_C,
            t_db_ambient_C=self.t_db_C,
        )

        # ===== PACKAGE RESULTS =====
        # Separate outputs for downstream vs internal monitoring
        return {
            # ========================================
            # FOR HEAT EXCHANGER / BUILDING
            # ========================================
            # These are the key values that downstream components need
            "for_heat_exchanger": {
                "component": "HVAC_System",
                # Chilled water interface
                "T_chw_supply_C": self.t_chw_supply_C,
                "T_chw_return_C": t_chw_return,
                "m_dot_chw_kg_s": m_dot_chw,
                "deltaT_chw_C": t_chw_return - self.t_chw_supply_C,
                "Q_cooling_W": q_evap,
                "Q_cooling_MW": q_evap / 1e6,
                # System performance
                "system_COP": cooling_result["downstream_interface"]["system_COP"],
                "total_power_MW": cooling_result["downstream_interface"]["total_power_MW"],
            },

            # ========================================
            # INTERNAL DIAGNOSTICS
            # ========================================
            # Detailed states for monitoring, debugging, validation
            "internal_diagnostics": {
                "air_loop": {
                    "air_pump": {
                        "m_dot_air_kg_s": m_dot_air,
                        "power_W": self.pump_power_W,
                        "delta_p_Pa": self.air_delta_p_Pa,
                        "efficiency": self.air_eta,
                    },
                    "air_cooled_equipment": {
                        "Q_load_W": ace_result["Q_in_W"],
                        "Q_absorbed_W": ace_result["Q_absorbed_W"],
                        "Q_unmet_W": ace_result["Q_unmet_W"],
                        "T_air_in_C": ace_result["T_in_air_C"],
                        "T_air_out_C": ace_result["T_out_air_C"],
                    },
                },
                "building_heat_exchanger": {
                    "Q_transferred_W": hx_result["Q_transferred_W"],
                    "Q_transferred_MW": hx_result["Q_transferred_W"] / 1e6,
                    "effectiveness": self.hx_effectiveness,
                    "hot_side": {
                        "fluid": "air",
                        "T_in_C": hx_result["T_hot_in_C"],
                        "T_out_C": hx_result["T_hot_out_C"],
                        "m_dot_kg_s": hx_result["m_dot_hot_kg_s"],
                    },
                    "cold_side": {
                        "fluid": "chilled_water",
                        "T_in_C": self.t_chw_supply_C,
                        "T_out_C": t_chw_return,
                        "m_dot_kg_s": m_dot_chw,
                    },
                },
                "cooling_system": cooling_result["internal_states"],
                "design_parameters": {
                    "deltaT_chw_design_C": self.deltaT_chw_design_C,
                    "t_chw_supply_C": self.t_chw_supply_C,
                    "chiller_cop": self.chiller_cop,
                    "hx_effectiveness": self.hx_effectiveness,
                },
            },
        }


# ============================================================================
# 主程序 - 用于测试
# ============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("HVAC集成冷却系统")
    print("=" * 80)
    print("\n这个文件包含所有HVAC组件的完整实现。")
    print("\n包含的类：")
    print("  - MoistAir, PsychrometricState (湿空气)")
    print("  - RefrigerantState, VaporCompressionCycle, HeatExchanger (制冷循环)")
    print("  - Chiller (冷水机)")
    print("  - CoolingTower (冷却塔)")
    print("  - Pump, PumpSystem (泵系统)")
    print("  - IntegratedHVACSystem (完整HVAC系统)")
    print("\n使用方法：")
    print("  from cooling_system import IntegratedHVACSystem")
    print("  system = IntegratedHVACSystem(...)")
    print("  results = system.solve()")
    print("\n运行示例：")
    print("  python main.py")
    print("=" * 80)
