"""
Psychrometric Properties Module

Provides thermodynamic property calculations for moist air analysis
in cooling tower modeling. Based on ASHRAE fundamentals.

All properties use:
- Temperature in Celsius (converted to K internally)
- Pressure in Pa (standard atmospheric = 101325 Pa)
- Humidity ratio w in kg_water/kg_dry_air
- Specific enthalpy in J/kg_dry_air
"""

import math


class MoistAir:
    """
    Calculates thermodynamic properties of moist air.

    Based on ASHRAE Fundamentals and ideal gas assumptions.
    Valid for temperatures -20°C to 50°C and atmospheric pressure.
    """

    # Constants
    P_ATM = 101325  # Pa, standard atmospheric pressure
    R_DA = 287.055  # J/(kg·K), gas constant for dry air
    R_WV = 461.52  # J/(kg·K), gas constant for water vapor
    CP_DA = 1006  # J/(kg·K), specific heat of dry air at constant pressure
    CP_WV = 1860  # J/(kg·K), specific heat of water vapor at constant pressure
    H_FG_0 = 2501000  # J/kg, latent heat of vaporization at 0°C

    @staticmethod
    def saturation_pressure(T_C):
        """
        Calculate saturation pressure of water vapor.

        Uses Antoine equation valid for -20°C to 50°C.

        Args:
            T_C: Temperature (°C)

        Returns:
            P_sat: Saturation pressure (Pa)

        Raises:
            ValueError: If temperature is out of valid range
        """
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


if __name__ == "__main__":
    test_psychrometrics()
