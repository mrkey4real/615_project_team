# CHIPCOOLING.py
from math import pi, ceil, log

# ------------------- Cp(T) helpers -------------------
def cp_molar_poly(T_K: float) -> float:
    """Heat capacity (molar): Cp = A + B*t + C*t^2 + D*t^3 + E/(t^2)  [J/mol·K]"""
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

# ------------------- Main solver -------------------
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

    # ---- Thermophysical properties (mass basis) ----
    T_chip_mean = 0.5 * (T1 + T2)     # °C
    T_bldg_mean = T_bin               # °C
    Cp_chip = cp_mass_water(T_chip_mean)  # J/(kg·K)
    Cp_bldg = cp_mass_water(T_bldg_mean)  # J/(kg·K)

    # ---- GPU heat & chip-side mass flow ----
    # If N is liquid-cooled count already, this is total chip heat on liquid loop.
    Q_chip = N * P_gpu
    dT_c = T2 - T1
    if dT_c <= 0:
        raise ValueError("Require T2 > T1 for chip cooling.")
    m_c_total = Q_chip / (Cp_chip * dT_c)  # kg/s

    # ---- Determine branch count B ----
    B_from_gpb = ceil(N / gpus_per_branch) if gpus_per_branch else None
    if v_cap_branch is not None and B is None:
        A2_tmp = pi * D2**2 / 4.0
        B_from_vcap = ceil(m_c_total / (rho * A2_tmp * v_cap_branch))
    else:
        B_from_vcap = None
    if B is None:
        candidates = [x for x in (B_from_gpb, B_from_vcap) if x]
        if not candidates:
            raise ValueError("Specify B, or gpus_per_branch, or v_cap_branch to determine branches.")
        B = max(candidates)
    if B <= 0:
        raise ValueError("B must be positive.")

    # ---- Racks ----
    GPUS_PER_RACK = 8
    R = ceil(N / GPUS_PER_RACK)
    racks_per_branch = ceil(R / B)

    # ---- Split flows ----
    m_branch = m_c_total / B
    m_rack   = m_branch / racks_per_branch

    # ---- Areas and velocities ----
    A1 = pi * D1**2 / 4.0
    A2 = pi * D2**2 / 4.0
    A3 = pi * D3**2 / 4.0

    v1 = m_rack    / (rho * A1)
    v2 = m_branch  / (rho * A2)
    v3 = m_c_total / (rho * A3)

    # ---- Darcy–Weisbach pressure drops ----
    dp1 = f1 * (L1 / D1) * (rho * v1**2 / 2.0)
    dp2 = f2 * (L2 / D2) * (rho * v2**2 / 2.0)
    dp3 = f3 * (L3 / D3) * (rho * v3**2 / 2.0)
    dp_path = dp1 + dp2 + dp3

    # ---- Pump power ----
    W_pump = (m_c_total / rho) * (dp_path / eta_p)

    # ---- HX feasibility & capacity (counterflow) ----
    if m_b <= 0: raise ValueError("m_b must be positive.")
    if flow_arrangement.lower() != "counterflow":
        raise NotImplementedError("Only COUNTERFLOW implemented.")

    # End temperature deltas for LMTD (full-load guess for warm-out):
    dT1_full = T2 - (T_bin + Q_chip / (m_b * Cp_bldg))  # hot-in − warm-out
    dT2      = T1 - T_bin                               # cold-out − cold-in

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
    Cc = m_c_total * Cp_chip  # W/K
    Cb = m_b        * Cp_bldg # W/K
    Cmin = min(Cc, Cb)

    # Enforce HX capacity limits
    Q_limits = [Q_chip]
    if UA is not None and dT_lm is not None:
        Q_limits.append(F_correction * UA * dT_lm)
    if epsilon is not None:
        Q_limits.append(epsilon * Cmin * (T2 - T_bin))
    Q_HX = min(Q_limits)

    # Final tower inlet temperature based on actual transferred heat
    T_tower = T_bin + Q_HX / (m_b * Cp_bldg)
    m_to_tower = m_b

    # UA required to pass full Q (for diagnostics)
    UA_required = (Q_chip / (F_correction * dT_lm)) if dT_lm not in (None, 0.0) else None

    return {
        # --- required minimal outputs ---
        "Q_chip_W": Q_chip,
        "Q_through_HX_W": Q_HX,
        "m_chip_kg_s": m_c_total,
        "W_pump_W": W_pump,
        "T_to_tower_C": T_tower,
        "m_to_tower_kg_s": m_to_tower,

        # --- HXer ---
        "hx": {
            "T_tower_C": T_tower,
            "dT1_K": T2 - T_tower,      # with actual warm-out
            "dT2_K": dT2,
            "dT_lm_K": dT_lm,           # from full-load ends
            "UA_required_W_per_K": UA_required,
            "UA_cap_W_per_K": UA,
            "epsilon_cap": epsilon,
            "feasible_hot_end": feasible_hot_end,
            "feasible_cold_end": feasible_cold_end,
            "Cc_W_per_K": Cc,
            "Cb_W_per_K": Cb
        },

        # --- Hydraulics ---
        "hydraulics": {
            "B": B,
            "R": R,
            "racks_per_branch": racks_per_branch,
            "A1_rack_m2": A1, "A2_branch_m2": A2, "A3_header_m2": A3,
            "v1_rack_m_s": v1, "v2_branch_m_s": v2, "v3_header_m_s": v3,
            "dp1_rack_Pa": dp1, "dp2_branch_Pa": dp2, "dp3_header_Pa": dp3,
            "dp_path_Pa": dp_path,
            "m_rack_kg_s": m_rack, "m_branch_kg_s": m_branch,
            "D1_rack_m": D1, "L1_rack_m": L1, "f1_rack": f1,
            "D2_branch_m": D2, "L2_branch_m": L2, "f2_branch": f2,
            "D3_header_m": D3, "L3_header_m": L3, "f3_header": f3,
        }
    }

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
