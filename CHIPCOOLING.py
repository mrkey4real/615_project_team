# CHIPCOOLING.py
from dataclasses import dataclass
from math import pi, ceil, log

# ------------------- Cp(T) helpers -------------------
def cp_molar_poly(T_K: float) -> float:
    """Heat capacity (molar): Cp = A + B*t + C*t**2 + D*t**3 + E/(t**2)  [J/mol·K]"""
    A = -203.606
    B = 1523.29
    C = -3196.413
    D = 2474.455
    E = 3.855326
    t = float(T_K) / 1000.0
    return A + B*t + C*(t**2) + D*(t**3) + E/(t**2)

def cp_mass_water(T_C: float) -> float:
    """Convert molar Cp [J/mol·K] to mass basis [J/kg·K] for water."""
    M_kg_per_mol = 0.01801528
    Cp_molar = cp_molar_poly(T_C + 273.15)
    return Cp_molar / M_kg_per_mol

# =================== Data classes (minimal-change) ===================
@dataclass
class LiquidCoolingChip:
    N: int
    P_gpu: float
    T1: float
    T2: float
    rho: float

    def compute(self):
        # mean temps & properties
        T_chip_mean = 0.5 * (self.T1 + self.T2)
        Cp_chip = cp_mass_water(T_chip_mean)
        # GPU heat & chip-side mass flow (UNCHANGED EQUATIONS)
        Q_chip = self.N * self.P_gpu
        dT_c = self.T2 - self.T1
        if dT_c <= 0:
            raise ValueError("Require T2 > T1 for chip cooling.")
        m_c_total = Q_chip / (Cp_chip * dT_c)
        return {
            "Q_chip": Q_chip,
            "Cp_chip": Cp_chip,
            "m_c_total": m_c_total,
            "dT_c": dT_c
        }

@dataclass
class GpuBranches:
    N: int
    m_c_total: float
    rho: float
    # rack, branch, header
    D1: float; L1: float; f1: float
    D2: float; L2: float; f2: float
    D3: float; L3: float; f3: float
    # controls
    B: int | None = None
    gpus_per_branch: int | None = None
    v_cap_branch: float | None = None

    def compute(self):
        # Determine branch count B (UNCHANGED LOGIC)
        B_from_gpb = ceil(self.N / self.gpus_per_branch) if self.gpus_per_branch else None
        if self.v_cap_branch is not None and self.B is None:
            A2_tmp = pi * self.D2**2 / 4.0
            B_from_vcap = ceil(self.m_c_total / (self.rho * A2_tmp * self.v_cap_branch))
        else:
            B_from_vcap = None
        if self.B is None:
            candidates = [x for x in (B_from_gpb, B_from_vcap) if x]
            if not candidates:
                raise ValueError("Specify B, or gpus_per_branch, or v_cap_branch to determine branches.")
            B = max(candidates)
        else:
            B = self.B
        if B <= 0:
            raise ValueError("B must be positive.")

        # Racks
        GPUS_PER_RACK = 8
        R = ceil(self.N / GPUS_PER_RACK)
        racks_per_branch = ceil(R / B)

        # Split flows
        m_branch = self.m_c_total / B
        m_rack   = m_branch / racks_per_branch

        # Areas & velocities
        A1 = pi * self.D1**2 / 4.0
        A2 = pi * self.D2**2 / 4.0
        A3 = pi * self.D3**2 / 4.0

        v1 = m_rack    / (self.rho * A1)
        v2 = m_branch  / (self.rho * A2)
        v3 = self.m_c_total / (self.rho * A3)

        # Darcy–Weisbach pressure drops (UNCHANGED EQUATIONS)
        dp1 = self.f1 * (self.L1 / self.D1) * (self.rho * v1**2 / 2.0)
        dp2 = self.f2 * (self.L2 / self.D2) * (self.rho * v2**2 / 2.0)
        dp3 = self.f3 * (self.L3 / self.D3) * (self.rho * v3**2 / 2.0)
        dp_path = dp1 + dp2 + dp3

        return {
            "B": B, "R": R, "racks_per_branch": racks_per_branch,
            "m_branch": m_branch, "m_rack": m_rack,
            "A1": A1, "A2": A2, "A3": A3,
            "v1": v1, "v2": v2, "v3": v3,
            "dp1": dp1, "dp2": dp2, "dp3": dp3, "dp_path": dp_path
        }

@dataclass
class Pump:
    m_c_total: float
    rho: float
    dp_path: float
    eta_p: float

    def compute(self):
        # Pump power (UNCHANGED EQUATION)
        W_pump = (self.m_c_total / self.rho) * (self.dp_path / self.eta_p)
        return {"W_pump": W_pump}

@dataclass
class HXer:
    # inputs
    Q_chip: float
    m_b: float
    T_bin: float
    T1: float
    T2: float
    Cp_bldg: float
    m_c_total: float
    Cp_chip: float
    # config
    flow_arrangement: str = "counterflow"
    F_correction: float = 1.0
    UA: float | None = None
    epsilon: float | None = None

    def compute(self):
        if self.m_b <= 0: 
            raise ValueError("m_b must be positive.")
        if self.flow_arrangement.lower() != "counterflow":
            raise NotImplementedError("Only COUNTERFLOW implemented.")

        # End temperature deltas for LMTD (UNCHANGED)
        dT1_full = self.T2 - (self.T_bin + self.Q_chip / (self.m_b * self.Cp_bldg))  # hot-in − warm-out
        dT2      = self.T1 - self.T_bin                                             # cold-out − cold-in
        feasible_hot_end  = (dT1_full > 0.0)
        feasible_cold_end = (dT2 > 0.0)

        if feasible_hot_end and feasible_cold_end:
            if abs(dT1_full - dT2) < 1e-12:
                dT_lm = dT1_full
            else:
                dT_lm = (dT1_full - dT2) / log(dT1_full / dT2)
        else:
            dT_lm = None

        # Capacity rates
        Cc = self.m_c_total * self.Cp_chip  # W/K
        Cb = self.m_b * self.Cp_bldg        # W/K
        Cmin = min(Cc, Cb)

        # Enforce HX capacity limits (UNCHANGED)
        Q_limits = [self.Q_chip]
        if (self.UA is not None) and (dT_lm is not None):
            Q_limits.append(self.F_correction * self.UA * dT_lm)
        if self.epsilon is not None:
            Q_limits.append(self.epsilon * Cmin * (self.T2 - self.T_bin))
        Q_HX = min(Q_limits)

        # Final tower inlet temperature
        T_tower = self.T_bin + Q_HX / (self.m_b * self.Cp_bldg)

        # UA required (diagnostic)
        UA_required = (self.Q_chip / (self.F_correction * dT_lm)) if dT_lm not in (None, 0.0) else None

        return {
            "T_tower_C": T_tower,
            "dT1_K": (self.T2 - T_tower),
            "dT2_K": dT2,
            "dT_lm_K": dT_lm,
            "UA_required_W_per_K": UA_required,
            "UA_cap_W_per_K": self.UA,
            "epsilon_cap": self.epsilon,
            "feasible_hot_end": feasible_hot_end,
            "feasible_cold_end": feasible_cold_end,
            "Cc_W_per_K": Cc,
            "Cb_W_per_K": Cb,
            "Q_through_HX_W": Q_HX
        }

# ------------------- Main solver (signature preserved) -------------------
def compute_selected_with_branches_and_hx(
    N: int,
    P_gpu: float,
    # Building side (to towers)
    m_b: float,
    T_bin: float,
    # Chip-side properties (defaults moved here)
    T1: float = 30.0,        # °C (Compute HX -> chips)
    T2: float = 40.0,        # °C (chips -> pump)
    rho: float = 997.0,      # kg/m^3

    # ---------- Input (keyword-only) ----------
    *,
    # GPU arrangement (now with defaults)
    D1: float = 0.020, L1: float = 600.0, f1: float = 0.02,  # rack
    D2: float = 0.10,  L2: float = 12.0,  f2: float = 0.02,  # branch
    D3: float = 1.65,  L3: float = 25.0,  f3: float = 0.02,  # header

    # Pump efficiency
    eta_p: float = 0.80,

    # Parallelization controls
    B: int | None = None,
    gpus_per_branch: int | None = None,
    v_cap_branch: float | None = None,

    # HX configuration / capacity limits
    flow_arrangement: str = "counterflow",
    F_correction: float = 1.0,
    UA: float | None = None,
    epsilon: float | None = None
):
    """
    Compute loop + HX model using a CDU plate heat exchanger (counterflow).
    Streams:
      * Chip loop (HOT):   inlet T2 (hot-in from chip->pump), outlet T1 (cold-out to chips)
      * Building loop:     inlet T_bin (from building/HX), outlet T_tower (to cooling towers)
    """
    # ---- Properties
    T_bldg_mean = T_bin
    Cp_bldg = cp_mass_water(T_bldg_mean)

    # ---- LiquidCoolingChip
    chip = LiquidCoolingChip(N=N, P_gpu=P_gpu, T1=T1, T2=T2, rho=rho).compute()
    Q_chip = chip["Q_chip"]
    m_c_total = chip["m_c_total"]
    Cp_chip = chip["Cp_chip"]

    # ---- GpuBranches
    branches = GpuBranches(
        N=N, m_c_total=m_c_total, rho=rho,
        D1=D1, L1=L1, f1=f1, D2=D2, L2=L2, f2=f2, D3=D3, L3=L3, f3=f3,
        B=B, gpus_per_branch=gpus_per_branch, v_cap_branch=v_cap_branch
    ).compute()

    # ---- Pump
    pump = Pump(m_c_total=m_c_total, rho=rho, dp_path=branches["dp_path"], eta_p=eta_p).compute()

    # ---- HXer
    hx = HXer(
        Q_chip=Q_chip, m_b=m_b, T_bin=T_bin, T1=T1, T2=T2,
        Cp_bldg=Cp_bldg, m_c_total=m_c_total, Cp_chip=Cp_chip,
        flow_arrangement=flow_arrangement, F_correction=F_correction,
        UA=UA, epsilon=epsilon
    ).compute()

    # Assemble outputs (keys preserved from previous structure)
    out = {
        "Q_chip_W": Q_chip,
        "Q_through_HX_W": hx["Q_through_HX_W"],
        "m_chip_kg_s": m_c_total,
        "W_pump_W": pump["W_pump"],
        "T_to_tower_C": hx["T_tower_C"],
        "m_to_tower_kg_s": m_b,
        "hx": hx,
        "hydraulics": {
            "B": branches["B"],
            "R": branches["R"],
            "racks_per_branch": branches["racks_per_branch"],
            "A1_rack_m2": branches["A1"], "A2_branch_m2": branches["A2"], "A3_header_m2": branches["A3"],
            "v1_rack_m_s": branches["v1"], "v2_branch_m_s": branches["v2"], "v3_header_m_s": branches["v3"],
            "dp1_rack_Pa": branches["dp1"], "dp2_branch_Pa": branches["dp2"], "dp3_header_Pa": branches["dp3"],
            "dp_path_Pa": branches["dp_path"],
            "m_rack_kg_s": branches["m_rack"], "m_branch_kg_s": branches["m_branch"],
            "D1_rack_m": D1, "L1_rack_m": L1, "f1_rack": f1,
            "D2_branch_m": D2, "L2_branch_m": L2, "f2_branch": f2,
            "D3_header_m": D3, "L3_header_m": L3, "f3_header": f3,
        }
    }
    return out

# ------------------- Print -------------------
def print_results(res, mode="HX"):
    mode = (mode or "").strip().upper()
    if mode not in {"HX", "SIMPLE", "ALL"}:
        raise ValueError('mode must be one of: "HX", "SIMPLE", "ALL"')

    Q_chip = res.get("Q_chip_W", None)
    Q_hx   = res.get("Q_through_HX_W", None)
    m_chip = res.get("m_chip_kg_s", None)
    Wpump  = res.get("W_pump_W", None)
    T_to_tower = res.get("T_to_tower_C", None)
    m_to_tower = res.get("m_to_tower_kg_s", None)
    hx = res.get("hx", {})
    hyd = res.get("hydraulics", {})

    if mode in {"SIMPLE", "ALL"}:
        print("=== SIMPLE SUMMARY ===")
        if Q_chip is not None:     print(f"Heat at chips [W]        : {Q_chip:.6e}")
        if Q_hx   is not None:     print(f"Heat removed by HX [W]   : {Q_hx:.6e}")
        if m_chip is not None:     print(f"m_chip [kg/s]            : {m_chip:.3f}")
        if Wpump  is not None:     print(f"Pump power [kW]          : {Wpump/1000:.3f}")
        if T_to_tower is not None: print(f"T_to_tower [°C]          : {T_to_tower:.3f}")
        if m_to_tower is not None: print(f"m_to_tower [kg/s]        : {m_to_tower:.3f}")
        if mode == "SIMPLE":
            return

    if mode in {"HX", "ALL"}:
        if hx:
            print("\n=== COMPUTE HXer (Plate HX in CDU, Counterflow) ===")
            print(f"T_tower [°C]             : {hx['T_tower_C']:.3f}")
            print(f"Cc, Cb [W/K]             : {hx['Cc_W_per_K']:.6e}, {hx['Cb_W_per_K']:.6e}")
            print(f"dT1 (hot-in−warm-out) [K]: {hx['dT1_K']:.3f}")
            print(f"dT2 (cold-out−cold-in)[K]: {hx['dT2_K']:.3f}")
            if hx['dT_lm_K'] is not None:
                print(f"LMTD [K]                 : {hx['dT_lm_K']:.3f}")
                if hx.get("UA_required_W_per_K") is not None:
                    print(f"UA required [W/K]        : {hx['UA_required_W_per_K']:.6e}  (to move full Q_chip)")
                if hx.get("UA_cap_W_per_K") is not None:
                    print(f"UA cap used [W/K]        : {hx['UA_cap_W_per_K']:.6e}")
                if hx.get("epsilon_cap") is not None:
                    print(f"ε cap used [-]           : {hx['epsilon_cap']:.3f}")
            else:
                print("LMTD / UA                : infeasible (check end temps)")
            if Q_chip is not None and Q_hx is not None and Q_hx < Q_chip:
                print(f"NOTE: HX-limited. Removed {Q_hx/Q_chip:0.2%} of chip heat.")
            print(f"Feasible hot end?        : {hx['feasible_hot_end']}")
            print(f"Feasible cold end?       : {hx['feasible_cold_end']}")
        elif mode == "HX":
            print("No HX block found in result.")

    if mode == "ALL":
        if hyd:
            print("\n=== HYDRAULICS (Rack → Branch → Header) ===")
            print(f"Branches B               : {hyd['B']}")
            print(f"Total racks R            : {hyd['R']}")
            print(f"Racks per branch         : {hyd['racks_per_branch']}")
            print(f"v1_rack [m/s]            : {hyd['v1_rack_m_s']:.3f}")
            print(f"v2_branch [m/s]          : {hyd['v2_branch_m_s']:.3f}")
            print(f"v3_header [m/s]          : {hyd['v3_header_m_s']:.3f}")
            print(f"Δp_rack [Pa]             : {hyd['dp1_rack_Pa']:.3f}")
            print(f"Δp_branch [Pa]           : {hyd['dp2_branch_Pa']:.3f}")
            print(f"Δp_header [Pa]           : {hyd['dp3_header_Pa']:.3f}")
            print(f"Δp_path total [Pa]       : {hyd['dp_path_Pa']:.3f}")
            print(f"A1_rack [m^2]            : {hyd['A1_rack_m2']:.6f}")
            print(f"A2_branch [m^2]          : {hyd['A2_branch_m2']:.6f}")
            print(f"A3_header [m^2]          : {hyd['A3_header_m2']:.6f}")
