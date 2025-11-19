"""
Integrated Cooling System Module
整合的冷却系统模块

This module consolidates all cooling system components:
- Refrigerant vapor compression cycle
- Chiller (evaporator + compressor + condenser)
- Cooling tower (heat rejection to ambient)
- Pump system (fluid circulation)
- Complete HVAC integration

Author: HVAC Team
Date: 2025-11-19
"""

from typing import Dict, Optional
import math

# ============================================================================
# REFRIGERANT CYCLE - Vapor Compression
# ============================================================================

try:
    from CoolProp.CoolProp import PropsSI
    COOLPROP_AVAILABLE = True
except ImportError:
    COOLPROP_AVAILABLE = False
    print("Warning: CoolProp not available. Install with: pip install CoolProp")


class RefrigerantState:
    """
    Thermodynamic state point in refrigeration cycle.
    制冷循环中的热力学状态点
    """

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

        if len(props) != 2:
            raise ValueError(f"Exactly 2 properties required, got {len(props)}: {list(props.keys())}")

        self._calculate_state(props)

    def _validate_refrigerant(self):
        try:
            PropsSI("Tcrit", self.refrigerant)
        except Exception as e:
            raise ValueError(f"Invalid refrigerant '{self.refrigerant}': {e}")

    def _calculate_state(self, props):
        prop_map = {"P": "P", "T_K": "T", "h": "H", "s": "S", "Q": "Q"}

        keys = list(props.keys())
        input1_name = prop_map[keys[0]]
        input1_val = props[keys[0]]
        input2_name = prop_map[keys[1]]
        input2_val = props[keys[1]]

        try:
            self.P = PropsSI("P", input1_name, input1_val, input2_name, input2_val, self.refrigerant)
            self.T_K = PropsSI("T", input1_name, input1_val, input2_name, input2_val, self.refrigerant)
            self.h = PropsSI("H", input1_name, input1_val, input2_name, input2_val, self.refrigerant)
            self.s = PropsSI("S", input1_name, input1_val, input2_name, input2_val, self.refrigerant)
            self.rho = PropsSI("D", input1_name, input1_val, input2_name, input2_val, self.refrigerant)
            self.Q = PropsSI("Q", input1_name, input1_val, input2_name, input2_val, self.refrigerant)
            self.T_C = self.T_K - 273.15
        except Exception as e:
            raise ValueError(f"CoolProp error calculating state: {e}")

    @property
    def phase(self):
        if self.Q < 0:
            return "Subcooled Liquid"
        elif 0 <= self.Q <= 1:
            return f"Two-Phase (x={self.Q:.3f})"
        else:
            return "Superheated Vapor"


class VaporCompressionCycle:
    """
    Complete vapor compression refrigeration cycle.
    完整的蒸汽压缩制冷循环

    States: 1(evap out) -> 2(comp out) -> 3(cond out) -> 4(valve out) -> 1
    """

    def __init__(self, refrigerant="R134a", eta_is_comp=0.80, superheat_evap=5.0, subcool_cond=3.0):
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

        self.state1 = None
        self.state2s = None
        self.state2 = None
        self.state3 = None
        self.state4 = None

    def solve(self, T_evap_C, T_cond_C, Q_evap_required):
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

        # State 2: Actual compression
        h2_actual = self.state1.h + (self.state2s.h - self.state1.h) / self.eta_is_comp
        self.state2 = RefrigerantState(self.refrigerant, P=P_cond, h=h2_actual)

        # State 3: Condenser outlet (subcooled liquid)
        T3_C = T_cond_C - self.subcool_cond
        self.state3 = RefrigerantState(self.refrigerant, P=P_cond, T=T3_C)

        # State 4: After expansion valve
        self.state4 = RefrigerantState(self.refrigerant, P=P_evap, h=self.state3.h)

        # Calculate refrigerant mass flow rate
        q_evap_per_kg = self.state1.h - self.state4.h
        m_dot_ref = Q_evap_required / q_evap_per_kg

        # Calculate performance
        Q_evap = Q_evap_required
        W_comp = m_dot_ref * (self.state2.h - self.state1.h)
        Q_cond = m_dot_ref * (self.state2.h - self.state3.h)
        COP = Q_evap / W_comp

        energy_balance_error = abs(Q_cond - (Q_evap + W_comp)) / Q_cond

        return {
            "refrigerant": self.refrigerant,
            "m_dot_ref_kg_s": m_dot_ref,
            "Q_evap_W": Q_evap,
            "W_comp_W": W_comp,
            "Q_cond_W": Q_cond,
            "COP": COP,
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


class HeatExchanger:
    """
    Counterflow heat exchanger (effectiveness-NTU method).
    逆流换热器（效能-传热单元数法）
    """

    def __init__(self, effectiveness=0.85, fouling_resistance=0.0001):
        if not 0.5 <= effectiveness <= 1.0:
            raise ValueError(f"Effectiveness {effectiveness} must be between 0.5 and 1.0")
        if fouling_resistance < 0:
            raise ValueError("Fouling resistance must be non-negative")

        self.effectiveness = effectiveness
        self.fouling_resistance = fouling_resistance

    def solve_counterflow(self, m_dot_hot, cp_hot, T_hot_in, m_dot_cold, cp_cold, T_cold_in, Q_target=None):
        if T_hot_in <= T_cold_in:
            raise ValueError(f"Hot inlet {T_hot_in}°C must be > cold inlet {T_cold_in}°C")

        C_hot = m_dot_hot * cp_hot
        C_cold = m_dot_cold * cp_cold
        C_min = min(C_hot, C_cold)
        C_max = max(C_hot, C_cold)
        C_ratio = C_min / C_max

        Q_max = C_min * (T_hot_in - T_cold_in)

        if Q_target is not None:
            Q_actual = Q_target
            if Q_actual > Q_max:
                raise ValueError(f"Target Q={Q_actual/1e6:.3f} MW exceeds Q_max={Q_max/1e6:.3f} MW")
            T_hot_out = T_hot_in - Q_actual / C_hot
            T_cold_out = T_cold_in + Q_actual / C_cold
            epsilon_actual = Q_actual / Q_max
        else:
            epsilon_actual = self.effectiveness
            Q_actual = epsilon_actual * Q_max
            T_hot_out = T_hot_in - Q_actual / C_hot
            T_cold_out = T_cold_in + Q_actual / C_cold

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


# ============================================================================
# PUMP SYSTEM - Fluid Circulation
# ============================================================================

class Pump:
    """
    Centrifugal pump using fluid dynamics principles.
    离心泵（基于流体动力学原理）

    P_pump = (ρ × g × H × Q) / η
    """

    def __init__(self, pump_type, static_head=10.0, dynamic_head_factor=0.5,
                 equipment_head=5.0, efficiency=0.85):
        if static_head < 0 or static_head > 100:
            raise ValueError(f"Invalid static_head: {static_head}, must be between 0 and 100 m")
        if equipment_head < 0 or equipment_head > 50:
            raise ValueError(f"Invalid equipment_head: {equipment_head}, must be between 0 and 50 m")
        if efficiency <= 0 or efficiency > 1.0:
            raise ValueError(f"Invalid efficiency: {efficiency}, must be between 0 and 1.0")

        self.pump_type = pump_type
        self.static_head = static_head
        self.dynamic_head_factor = dynamic_head_factor
        self.equipment_head = equipment_head
        self.efficiency = efficiency
        self.g = 9.81
        self.rho_water = 998

    def calculate_dynamic_head(self, velocity):
        velocity_head = velocity**2 / (2 * self.g)
        return velocity_head * self.dynamic_head_factor

    def calculate_total_head(self, velocity=None, dynamic_head=None):
        if dynamic_head is None:
            if velocity is not None:
                dynamic_head = self.calculate_dynamic_head(velocity)
            else:
                dynamic_head = self.calculate_dynamic_head(2.0)

        H_total = self.static_head + dynamic_head + self.equipment_head
        return H_total

    def calculate_power(self, m_dot, density=None, H_total=None, velocity=None):
        if m_dot <= 0:
            raise ValueError(f"Invalid m_dot: {m_dot}, must be > 0")

        if density is None:
            density = self.rho_water

        Q = m_dot / density

        if H_total is None:
            H_total = self.calculate_total_head(velocity=velocity)

        P_pump = (density * self.g * H_total * Q) / self.efficiency
        return P_pump

    def solve(self, m_dot, density=None, velocity=None):
        if density is None:
            density = self.rho_water

        Q = m_dot / density
        H_total = self.calculate_total_head(velocity=velocity)
        P_pump = self.calculate_power(m_dot, density=density, H_total=H_total)
        E_fluid = m_dot * self.g * H_total

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
    Condenser water pump system.
    冷凝水泵系统
    """

    def __init__(self, cw_static_head=10.0, cw_efficiency=0.85):
        self.cw_pump = Pump(
            pump_type="CW",
            static_head=cw_static_head,
            equipment_head=6.0,
            efficiency=cw_efficiency,
        )

    def solve(self, m_dot_cw):
        cw_result = self.cw_pump.solve(m_dot_cw)

        return {
            "component": "Pump System (CW Loop)",
            "CW_pump": cw_result,
            "P_pump_W": cw_result["P_pump_W"],
            "P_pump_kW": cw_result["P_pump_kW"],
            "P_pump_MW": cw_result["P_pump_MW"],
            "static_head_m": self.cw_pump.static_head,
            "efficiency": self.cw_pump.efficiency,
        }


# ============================================================================
# CHILLER - Water-Cooled Chiller
# ============================================================================

class Chiller:
    """
    Water-cooled chiller using vapor compression refrigeration cycle.
    水冷式冷水机组（采用蒸汽压缩制冷循环）
    """

    def __init__(self, rated_capacity_mw, rated_cop, t_chw_supply, refrigerant="R134a",
                 eta_is_comp=0.80, evap_effectiveness=0.85, cond_effectiveness=0.85, curves_file=None):
        if not COOLPROP_AVAILABLE:
            raise ImportError("CoolProp is required for refrigeration cycle modeling. "
                            "Install with: pip install CoolProp")

        if rated_capacity_mw <= 0:
            raise ValueError(f"Invalid rated_capacity_mw: {rated_capacity_mw}, must be > 0")
        if rated_cop <= 0 or rated_cop > 10:
            raise ValueError(f"Invalid rated_cop: {rated_cop}, must be between 0 and 10")
        if t_chw_supply < 0 or t_chw_supply >= 30:
            raise ValueError(f"Invalid t_chw_supply: {t_chw_supply}, must be between 0 and 30 °C")

        self.rated_capacity = rated_capacity_mw * 1e6
        self.rated_cop = rated_cop
        self.t_chw_supply = t_chw_supply
        self.cp_water = 4186

        self.refrigerant = refrigerant
        self.ref_cycle = VaporCompressionCycle(
            refrigerant=refrigerant,
            eta_is_comp=eta_is_comp,
            superheat_evap=5.0,
            subcool_cond=3.0,
        )

        self.evap_hx = HeatExchanger(effectiveness=evap_effectiveness)
        self.cond_hx = HeatExchanger(effectiveness=cond_effectiveness)

    def solve_energy_balance(self, q_evap, m_dot_chw, m_dot_cw, t_cw_in,
                           t_chw_return=None, max_iter=20, tolerance=0.1):
        if q_evap <= 0:
            raise ValueError(f"Invalid q_evap: {q_evap}, must be > 0")
        if m_dot_chw <= 0:
            raise ValueError(f"Invalid m_dot_chw: {m_dot_chw}, must be > 0")
        if m_dot_cw <= 0:
            raise ValueError(f"Invalid m_dot_cw: {m_dot_cw}, must be > 0")

        if t_chw_return is None:
            delta_t_chw = q_evap / (m_dot_chw * self.cp_water)
            t_chw_return = self.t_chw_supply + delta_t_chw

        T_evap = self.t_chw_supply - 5.0
        T_cond = t_cw_in + 5.0

        for iteration in range(max_iter):
            T_evap_old = T_evap
            T_cond_old = T_cond

            try:
                cycle_result = self.ref_cycle.solve(
                    T_evap_C=T_evap, T_cond_C=T_cond, Q_evap_required=q_evap
                )
            except Exception as e:
                raise ValueError(f"Refrigeration cycle solution failed at iteration {iteration}: {e}")

            m_dot_ref = cycle_result["m_dot_ref_kg_s"]
            q_cond_ref = cycle_result["Q_cond_W"]
            w_comp = cycle_result["W_comp_W"]

            T_ref_evap_out = self.ref_cycle.state1.T_C
            pinch_evap = self.t_chw_supply - T_evap
            if pinch_evap < 3.0:
                T_evap -= 0.5
            elif pinch_evap > 8.0:
                T_evap += 0.3

            T_ref_cond_in = self.ref_cycle.state2.T_C
            T_ref_cond_out = self.ref_cycle.state3.T_C

            t_cw_out = t_cw_in + q_cond_ref / (m_dot_cw * self.cp_water)

            pinch_cond = T_cond - t_cw_out
            if pinch_cond < 3.0:
                T_cond += 0.5
            elif pinch_cond > 8.0:
                T_cond -= 0.3

            evap_effectiveness = 0.85
            cond_effectiveness = 0.85

            delta_T_evap = abs(T_evap - T_evap_old)
            delta_T_cond = abs(T_cond - T_cond_old)

            if delta_T_evap < tolerance and delta_T_cond < tolerance:
                cop = cycle_result["COP"]
                plr = q_evap / self.rated_capacity

                return {
                    "component": "Chiller (Thermodynamic Cycle)",
                    "refrigerant": self.refrigerant,
                    "converged": True,
                    "iterations": iteration + 1,
                    "Q_evap_MW": q_evap / 1e6,
                    "Q_cond_MW": q_cond_ref / 1e6,
                    "W_comp_MW": w_comp / 1e6,
                    "COP": cop,
                    "PLR": plr,
                    "T_chw_supply_C": self.t_chw_supply,
                    "T_chw_return_C": t_chw_return,
                    "delta_T_chw_C": t_chw_return - self.t_chw_supply,
                    "m_dot_chw_kg_s": m_dot_chw,
                    "T_cw_in_C": t_cw_in,
                    "T_cw_out_C": t_cw_out,
                    "delta_T_cw_C": t_cw_out - t_cw_in,
                    "m_dot_cw_kg_s": m_dot_cw,
                    "T_evap_sat_C": T_evap,
                    "T_cond_sat_C": T_cond,
                    "m_dot_ref_kg_s": m_dot_ref,
                    "P_evap_kPa": cycle_result["P_evap_Pa"] / 1000,
                    "P_cond_kPa": cycle_result["P_cond_Pa"] / 1000,
                    "compression_ratio": cycle_result["compression_ratio"],
                    "energy_balance_error_pct": abs(q_cond_ref - (q_evap + w_comp)) / q_cond_ref * 100,
                    "evap_effectiveness": evap_effectiveness,
                    "cond_effectiveness": cond_effectiveness,
                }

        raise ValueError(
            f"Chiller solution did not converge after {max_iter} iterations. "
            f"Last changes: ΔT_evap={delta_T_evap:.3f}°C, ΔT_cond={delta_T_cond:.3f}°C"
        )


# ============================================================================
# COOLING TOWER - Heat Rejection to Ambient
# ============================================================================

# Import psychrometrics for cooling tower calculations
from psychrometrics import MoistAir, PsychrometricState


class CoolingTower:
    """
    Induced-draft cooling tower using psychrometric analysis.
    诱导通风冷却塔（采用湿空气分析）
    """

    def __init__(self, approach_temp, coc, drift_rate=0.00001, air_to_water_ratio=1.2):
        if approach_temp <= 0 or approach_temp > 20:
            raise ValueError(f"Invalid approach_temp: {approach_temp}, must be between 0 and 20 °C")
        if coc < 2 or coc > 10:
            raise ValueError(f"Invalid coc: {coc}, must be between 2 and 10")
        if drift_rate < 0 or drift_rate > 0.01:
            raise ValueError(f"Invalid drift_rate: {drift_rate}, must be between 0 and 0.01")
        if air_to_water_ratio <= 0 or air_to_water_ratio > 5:
            raise ValueError(f"Invalid air_to_water_ratio: {air_to_water_ratio}, must be between 0 and 5")

        self.approach = approach_temp
        self.coc = coc
        self.drift_rate = drift_rate
        self.air_to_water_ratio = air_to_water_ratio
        self.cp_water = 4186
        self.h_fg = 2260e3

    def calculate_outlet_temp(self, t_wb):
        if t_wb < -20 or t_wb > 50:
            raise ValueError(f"Invalid t_wb: {t_wb}, must be between -20 and 50 C")
        return t_wb + self.approach

    def calculate_evaporation_rate(self, q_cond, m_dot_cw, delta_t):
        m_evap = q_cond / self.h_fg
        return m_evap

    def calculate_drift_loss(self, m_dot_cw):
        return self.drift_rate * m_dot_cw

    def calculate_blowdown_rate(self, m_evap):
        return m_evap / (self.coc - 1)

    def calculate_makeup_water(self, m_evap, m_drift, m_blowdown):
        return m_evap + m_drift + m_blowdown

    def calculate_fan_power(self, q_cond):
        fan_power_fraction = 0.007
        return q_cond * fan_power_fraction

    def solve(self, q_cond, m_dot_cw, t_in, t_wb, t_db=None, RH_in=None):
        if q_cond <= 0:
            raise ValueError(f"Invalid q_cond: {q_cond}, must be > 0")
        if m_dot_cw <= 0:
            raise ValueError(f"Invalid m_dot_cw: {m_dot_cw}, must be > 0")
        if t_in < 0 or t_in >= 100:
            raise ValueError(f"Invalid t_in: {t_in}, must be between 0 and 100 °C")

        t_out = self.calculate_outlet_temp(t_wb)
        delta_t = t_in - t_out

        if delta_t <= 0:
            raise ValueError(f"Water inlet temp {t_in}°C must be > outlet temp {t_out}°C")

        if t_db is None:
            t_db = t_wb + 10.0

        try:
            air_in = PsychrometricState(T_db_C=t_db, T_wb_C=t_wb)
        except Exception as e:
            raise ValueError(f"Failed to calculate air inlet state: {e}")

        try:
            air_out = PsychrometricState(T_db_C=t_out, RH=0.95)
        except Exception as e:
            raise ValueError(f"Failed to calculate air outlet state: {e}")

        q_water = m_dot_cw * self.cp_water * delta_t

        delta_h_air = air_out.h - air_in.h

        if delta_h_air <= 0:
            raise ValueError(
                f"Air enthalpy must increase through tower. "
                f"h_in={air_in.h:.0f} J/kg, h_out={air_out.h:.0f} J/kg"
            )

        m_dot_da = q_water / delta_h_air

        actual_air_to_water_ratio = m_dot_da * (1 + air_in.w) / m_dot_cw

        m_evap_air = m_dot_da * (air_out.w - air_in.w)
        m_evap_energy = q_cond / self.h_fg
        m_evap = m_evap_air

        m_drift = self.calculate_drift_loss(m_dot_cw)
        m_blowdown = self.calculate_blowdown_rate(m_evap)
        m_makeup = self.calculate_makeup_water(m_evap, m_drift, m_blowdown)

        q_air = m_dot_da * (air_out.h - air_in.h)
        energy_balance_error = abs(q_water - q_air) / q_water * 100

        if energy_balance_error > 5.0:
            import warnings
            warnings.warn(
                f"Cooling tower energy balance error {energy_balance_error:.1f}% exceeds 5%. "
                f"This suggests numerical issues in psychrometric calculations."
            )

        w_fan = self.calculate_fan_power(q_cond)

        return {
            "component": "Cooling Tower (Psychrometric)",
            "Q_cond_MW": q_cond / 1e6,
            "Q_water_MW": q_water / 1e6,
            "Q_air_MW": q_air / 1e6,
            "T_water_in_C": t_in,
            "T_water_out_C": t_out,
            "Range_C": delta_t,
            "Approach_C": self.approach,
            "m_dot_cw_kg_s": m_dot_cw,
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
            "m_evap_kg_s": m_evap,
            "m_evap_energy_kg_s": m_evap_energy,
            "m_drift_kg_s": m_drift,
            "m_blowdown_kg_s": m_blowdown,
            "m_makeup_kg_s": m_makeup,
            "m_makeup_L_s": m_makeup,
            "m_makeup_L_hr": m_makeup * 3600,
            "COC": self.coc,
            "W_fan_MW": w_fan / 1e6,
            "energy_balance_error_pct": energy_balance_error,
            "air_inlet_state": air_in,
            "air_outlet_state": air_out,
        }


# ============================================================================
# INTEGRATED COOLING SYSTEM - Complete Integration
# ============================================================================

class CoolingSystem:
    """
    Integrated cooling system combining chiller, cooling tower, and pumps.
    整合的冷却系统（冷水机组+冷却塔+泵）

    This is the main class that provides cooling to the building heat exchanger.
    这是向建筑热交换器提供冷却的主类。
    """

    def __init__(
        self,
        chiller_capacity_MW: float = 1000.0,
        chiller_cop: float = 6.0,
        t_chw_supply_C: float = 7.0,
        refrigerant: str = "R134a",
        tower_approach_C: float = 4.0,
        tower_coc: float = 4.0,
        pump_static_head_m: float = 10.0,
        pump_efficiency: float = 0.85,
        max_iter: int = 50,
        tol_C: float = 0.05,
    ):
        """
        Initialize integrated cooling system.
        初始化整合冷却系统
        """
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
            drift_rate=1e-5,
            air_to_water_ratio=1.2,
        )

        self.pump_system = PumpSystem(
            cw_static_head=pump_static_head_m,
            cw_efficiency=pump_efficiency,
        )

        self.t_chw_supply = t_chw_supply_C
        self.max_iter = max_iter
        self.tol_C = tol_C
        self.cp_water = 4186.0

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
        为给定的冷负荷求解完整的冷却系统

        Args:
            q_cooling_load_W: Required cooling capacity (W) 需要的冷量
            m_dot_chw_kg_s: Chilled water mass flow rate (kg/s) 冷冻水流量
            t_chw_return_C: Chilled water return temperature (°C) 冷冻水回水温度
            t_wb_ambient_C: Ambient wet bulb temperature (°C) 环境湿球温度
            t_db_ambient_C: Ambient dry bulb temperature (°C) 环境干球温度
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
        deltaT_cw_design = 5.5
        q_cond_est = q_cooling_load_W * 1.15
        m_dot_cw = q_cond_est / (self.cp_water * deltaT_cw_design)

        # Initial guess for condenser water inlet temperature
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
                q_cond=chiller_result["Q_cond_MW"] * 1e6,
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
    Test integrated cooling system.
    测试整合冷却系统
    """
    print("\n" + "=" * 80)
    print("整合冷却系统测试 - INTEGRATED COOLING SYSTEM TEST")
    print("=" * 80)

    cooling_system = CoolingSystem(
        chiller_capacity_MW=1000.0,
        chiller_cop=6.0,
        t_chw_supply_C=7.0,
        tower_approach_C=4.0,
        tower_coc=4.0,
    )

    # Operating conditions
    q_cooling = 1000e6  # 1000 MW
    m_dot_chw = 47770  # kg/s
    t_chw_return = 12.0  # °C
    t_wb = 24.0  # °C
    t_db = 35.0  # °C

    print(f"\n运行条件 Operating Conditions:")
    print(f"  冷负荷 Cooling Load:        {q_cooling/1e6:.1f} MW")
    print(f"  冷冻水流量 CHW Flow:         {m_dot_chw:.0f} kg/s")
    print(f"  冷冻水供水温度 CHW Supply:   {cooling_system.t_chw_supply:.1f} °C")
    print(f"  冷冻水回水温度 CHW Return:   {t_chw_return:.1f} °C")
    print(f"  环境湿球温度 Wet Bulb:       {t_wb:.1f} °C")
    print(f"  环境干球温度 Dry Bulb:       {t_db:.1f} °C")

    result = cooling_system.solve(
        q_cooling_load_W=q_cooling,
        m_dot_chw_kg_s=m_dot_chw,
        t_chw_return_C=t_chw_return,
        t_wb_ambient_C=t_wb,
        t_db_ambient_C=t_db,
    )

    print("\n" + "=" * 80)
    print("下游接口 DOWNSTREAM INTERFACE (for Heat Exchanger / Building)")
    print("=" * 80)
    ds = result["downstream_interface"]
    print(f"CHW Supply Temp:       {ds['T_chw_supply_C']:.2f} °C")
    print(f"CHW Return Temp:       {ds['T_chw_return_C']:.2f} °C")
    print(f"CHW Flow Rate:         {ds['m_dot_chw_kg_s']:.0f} kg/s")
    print(f"Cooling Capacity:      {ds['Q_cooling_MW']:.1f} MW")
    print(f"System COP:            {ds['system_COP']:.2f}")
    print(f"Total Power:           {ds['total_power_MW']:.1f} MW")

    print("\n" + "=" * 80)
    print("内部状态 INTERNAL STATES")
    print("=" * 80)

    internal = result["internal_states"]

    print(f"\n收敛 Convergence: {internal['convergence']['converged']} (迭代 {internal['convergence']['iterations']} 次)")

    ch = internal["chiller"]
    print(f"\n冷水机组 Chiller:")
    print(f"  Q_evap:    {ch['Q_evap_MW']:.1f} MW")
    print(f"  W_comp:    {ch['W_comp_MW']:.1f} MW")
    print(f"  Q_cond:    {ch['Q_cond_MW']:.1f} MW")
    print(f"  COP:       {ch['COP']:.2f}")

    ct = internal["cooling_tower"]
    print(f"\n冷却塔 Cooling Tower:")
    print(f"  Heat Rejected: {ct['Q_rejected_MW']:.1f} MW")
    print(f"  Fan Power:     {ct['W_fan_MW']:.1f} MW")
    print(f"  Water Makeup:  {ct['m_makeup_L_hr']:,.0f} L/hr")

    print("=" * 80 + "\n")
