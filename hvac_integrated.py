"""
Integrated HVAC Steady-State (Air Loop + Building HX + Chiller + Cooling Tower + Pump)
See docstring inside for usage. This file is self-contained and uses team modules when available.
"""
from dataclasses import dataclass
from typing import Dict, Optional

# ---- Physical constants ----
CP_AIR = 1005.0
RHO_AIR_25C = 1.184
CP_WATER = 4186.0


# --------- JSON serialization helper ---------
def to_jsonable(obj):
    """Recursively convert objects (including dataclasses and custom classes like PsychrometricState)
    into JSON-serializable types. Fallback to string for anything else."""
    try:
        import numpy as _np
    except Exception:
        _np = None

    from dataclasses import is_dataclass, asdict

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
    from cooling_system import CoolingSystem

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


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("INTEGRATED HVAC SYSTEM TEST")
    print("=" * 80)

    system = IntegratedHVACSystem(
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

    print("\nSolving system...")
    results = system.solve()

    # ===== SHOW HEAT EXCHANGER INTERFACE =====
    print("\n" + "=" * 80)
    print("FOR HEAT EXCHANGER / BUILDING (Downstream Interface)")
    print("=" * 80)
    hx_interface = results["for_heat_exchanger"]
    print(f"Component:             {hx_interface['component']}")
    print(f"CHW Supply Temp:       {hx_interface['T_chw_supply_C']:.2f} °C")
    print(f"CHW Return Temp:       {hx_interface['T_chw_return_C']:.2f} °C")
    print(f"CHW Flow Rate:         {hx_interface['m_dot_chw_kg_s']:.0f} kg/s")
    print(f"CHW Delta-T:           {hx_interface['deltaT_chw_C']:.2f} °C")
    print(f"Cooling Capacity:      {hx_interface['Q_cooling_MW']:.1f} MW")
    print(f"System COP:            {hx_interface['system_COP']:.2f}")
    print(f"Total Power:           {hx_interface['total_power_MW']:.1f} MW")

    # ===== SHOW INTERNAL DIAGNOSTICS (SUMMARY) =====
    print("\n" + "=" * 80)
    print("INTERNAL DIAGNOSTICS (Summary)")
    print("=" * 80)
    diagnostics = results["internal_diagnostics"]

    print("\n--- Air Loop ---")
    print(f"Air Flow:              {diagnostics['air_loop']['air_pump']['m_dot_air_kg_s']:.0f} kg/s")
    print(f"Air Pump Power:        {diagnostics['air_loop']['air_pump']['power_W']/1e6:.2f} MW")
    print(f"Heat Absorbed:         {diagnostics['air_loop']['air_cooled_equipment']['Q_absorbed_W']/1e6:.1f} MW")

    print("\n--- Building Heat Exchanger ---")
    print(f"Heat Transferred:      {diagnostics['building_heat_exchanger']['Q_transferred_MW']:.1f} MW")
    print(f"Effectiveness:         {diagnostics['building_heat_exchanger']['effectiveness']:.2f}")

    print("\n--- Cooling System ---")
    cs = diagnostics['cooling_system']
    print(f"Chiller COP:           {cs['chiller']['COP']:.2f}")
    print(f"Compressor Power:      {cs['chiller']['W_comp_MW']:.1f} MW")
    print(f"Tower Fan Power:       {cs['cooling_tower']['W_fan_MW']:.1f} MW")
    print(f"Water Makeup:          {cs['cooling_tower']['m_makeup_L_hr']:,.0f} L/hr")

    # ===== OPTIONALLY SHOW FULL JSON =====
    print("\n" + "=" * 80)
    print("Full results available in JSON format (uncomment to see)")
    print("=" * 80)
    # import json
    # print(json.dumps(to_jsonable(results), indent=2))
