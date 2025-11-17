
"""hvac_components_v3.py
Steady-state components tailored to the user's requirements:
  - Pump: computes air flow rate from input power using fixed efficiency and pressure rise.
  - AirCooledComponent: applies a fixed heat load to an air stream but enforces a max outlet temperature.
  - BuildingHeatExchanger: generic two-stream exchanger using a single 'efficiency' value
    (effectiveness) with inputs as flow rate, heat capacity, and inlet temperature of both fluids.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional

###############################################################################
# Pump
###############################################################################

@dataclass
class Pump:
    """Simple pump/fan that converts electrical power to volumetric flow.

    Assumes a constant overall efficiency and a representative system pressure rise.
    It uses: V_dot = (P_in * eta) / delta_p. Mass flow is V_dot * rho.

    Parameters
    ----------
    eta : float
        Overall efficiency (0 < eta <= 1).
    delta_p_Pa : float
        Representative pressure rise across the path [Pa].
    rho : float
        Fluid density [kg/m^3]. For air, ~1.2 at room conditions.
    name : str
        Label for identification.
    """
    eta: float = 0.6
    delta_p_Pa: float = 300.0
    rho: float = 1.2
    name: str = "Air Pump"

    def flow_from_power(self, P_in_W: float) -> Dict[str, float]:
        if self.eta <= 0 or self.eta > 1:
            raise ValueError("eta must be in (0, 1].")
        if self.delta_p_Pa <= 0:
            raise ValueError("delta_p_Pa must be > 0.")
        V_dot = (P_in_W * self.eta) / self.delta_p_Pa  # m^3/s
        m_dot = V_dot * self.rho                       # kg/s
        return {
            "component": self.name,
            "P_in_W": P_in_W,
            "eta": self.eta,
            "delta_p_Pa": self.delta_p_Pa,
            "rho": self.rho,
            "V_dot_m3_s": V_dot,
            "m_dot_kg_s": m_dot,
        }

###############################################################################
# Air-cooled component
###############################################################################

@dataclass
class AirCooledComponent:
    """Applies a known heat load to an airstream with an outlet temperature cap.

    The model computes:
      - the 'ideal' outlet temperature without any cap,
      - the capped outlet temperature (max_outlet_C), and
      - the heat actually absorbed by the air at the given flow.
    If the cap is active, it also reports the unmet heat and the minimum
    required mass flow to meet both the heat and the cap.

    Parameters
    ----------
    Q_W : float
        Total sensible heat load added to the air [W]. Example: 100e6 for 100 MW.
    max_outlet_C : float
        Upper bound on outlet air temperature [degC]. Example: 25.
    cp_air : float
        Specific heat of air [J/(kg*K)]. Default 1005.
    name : str
        Label for identification.
    """
    Q_W: float = 100e6
    max_outlet_C: float = 25.0
    cp_air: float = 1005.0
    name: str = "Air Cooled Component"

    def process(self, T_in_C: float, m_dot_air_kg_s: float) -> Dict[str, float]:
        if m_dot_air_kg_s <= 0:
            raise ValueError("Air mass flow must be > 0.")
        deltaT_ideal = self.Q_W / (m_dot_air_kg_s * self.cp_air)
        T_out_ideal = T_in_C + deltaT_ideal
        # Heat that can be absorbed without exceeding the cap:
        allowable_deltaT = max(0.0, self.max_outlet_C - T_in_C)
        Q_absorbable = m_dot_air_kg_s * self.cp_air * allowable_deltaT
        if T_out_ideal <= self.max_outlet_C:
            # No cap hit.
            T_out_C = T_out_ideal
            Q_absorbed = self.Q_W
            Q_unmet = 0.0
            cap_active = False
            m_dot_required_min = max(0.0, self.Q_W / (self.cp_air * max(1e-9, allowable_deltaT))) if allowable_deltaT > 0 else float('inf')
        else:
            # Cap hit. Only a portion of Q can be absorbed.
            T_out_C = self.max_outlet_C
            Q_absorbed = Q_absorbable
            Q_unmet = max(0.0, self.Q_W - Q_absorbable)
            cap_active = True
            m_dot_required_min = (self.Q_W / (self.cp_air * max(1e-9, allowable_deltaT))) if allowable_deltaT > 0 else float('inf')

        return {
            "component": self.name,
            "T_in_C": T_in_C,
            "T_out_C": T_out_C,
            "T_out_ideal_C": T_out_ideal,
            "max_outlet_C": self.max_outlet_C,
            "m_dot_air_kg_s": m_dot_air_kg_s,
            "cp_air_J_per_kgK": self.cp_air,
            "Q_load_W": self.Q_W,
            "Q_absorbed_W": Q_absorbed,
            "Q_unmet_W": Q_unmet,
            "cap_active": cap_active,
            "m_dot_required_min_kg_s": m_dot_required_min
        }

###############################################################################
# Building heat exchanger (generic two-stream, single efficiency)
###############################################################################

@dataclass
class BuildingHeatExchanger:
    """Two-stream heat exchanger using a single efficiency (effectiveness).

    Inputs (per call):
      - m_dot_1, cp_1, T1_in_C
      - m_dot_2, cp_2, T2_in_C
      - efficiency (0..1), interpreted as effectiveness
    Outputs:
      - m_dot_1, m_dot_2 (unchanged)
      - T1_out_C, T2_out_C
      - Q_transferred_W

    The hotter inlet is treated as the hot side, and the colder inlet as the cold side.
    The transferred heat is: Q = eff * C_min * (T_hot_in - T_cold_in).
    """
    name: str = "Building Heat Exchanger"

    def exchange(self,
                 m_dot_1_kg_s: float, cp_1_J_per_kgK: float, T1_in_C: float,
                 m_dot_2_kg_s: float, cp_2_J_per_kgK: float, T2_in_C: float,
                 efficiency: float) -> Dict[str, float]:

        if m_dot_1_kg_s <= 0 or m_dot_2_kg_s <= 0:
            raise ValueError("Mass flows must be > 0.")
        if cp_1_J_per_kgK <= 0 or cp_2_J_per_kgK <= 0:
            raise ValueError("Heat capacities must be > 0.")
        eff = max(0.0, min(1.0, efficiency))

        # Identify hot and cold streams by inlet temperature
        if T1_in_C >= T2_in_C:
            # stream 1 is hot
            C_hot = m_dot_1_kg_s * cp_1_J_per_kgK
            C_cold = m_dot_2_kg_s * cp_2_J_per_kgK
            Th_in, Tc_in = T1_in_C, T2_in_C
            hot_is_1 = True
        else:
            C_hot = m_dot_2_kg_s * cp_2_J_per_kgK
            C_cold = m_dot_1_kg_s * cp_1_J_per_kgK
            Th_in, Tc_in = T2_in_C, T1_in_C
            hot_is_1 = False

        deltaT_in = Th_in - Tc_in
        if deltaT_in <= 0:
            Q = 0.0
        else:
            C_min = min(C_hot, C_cold)
            Q = eff * C_min * deltaT_in

        # Compute outlet temperatures
        if hot_is_1:
            T1_out = T1_in_C - (Q / C_hot if C_hot > 0 else 0.0)
            T2_out = T2_in_C + (Q / C_cold if C_cold > 0 else 0.0)
        else:
            T1_out = T1_in_C + (Q / C_cold if C_cold > 0 else 0.0)
            T2_out = T2_in_C - (Q / C_hot if C_hot > 0 else 0.0)

        return {
            "component": self.name,
            "m_dot_1_kg_s": m_dot_1_kg_s,
            "cp_1_J_per_kgK": cp_1_J_per_kgK,
            "T1_in_C": T1_in_C,
            "T1_out_C": T1_out,
            "m_dot_2_kg_s": m_dot_2_kg_s,
            "cp_2_J_per_kgK": cp_2_J_per_kgK,
            "T2_in_C": T2_in_C,
            "T2_out_C": T2_out,
            "efficiency": eff,
            "Q_transferred_W": Q
        }

###############################################################################
# Minimal demonstration (can be removed)
###############################################################################
if __name__ == "__main__":
    # Pump provides air flow from power
    pump = Pump(eta=0.6, delta_p_Pa=600.0, rho=1.2, name="Air Pump")
    pump_res = pump.flow_from_power(P_in_W=2.0e7)  # 20 MW as an example
    print("Pump:", pump_res)

    # Air component with 100 MW and max 25C outlet
    air_comp = AirCooledComponent(Q_W=100e6, max_outlet_C=25.0, cp_air=1005.0, name="ACE")
    # Assume inlet air at 20C
    ace_res = air_comp.process(T_in_C=20.0, m_dot_air_kg_s=pump_res["m_dot_kg_s"])
    print("Air component:", ace_res)

    # Building HX: use air as stream 1, water as stream 2
    hx = BuildingHeatExchanger(name="Building HX")
    hx_res = hx.exchange(
        m_dot_1_kg_s=ace_res["m_dot_air_kg_s"], cp_1_J_per_kgK=1005.0, T1_in_C=ace_res["T_out_C"],
        m_dot_2_kg_s=500.0, cp_2_J_per_kgK=4184.0, T2_in_C=7.0,
        efficiency=0.9
    )
    print("HX:", hx_res)
