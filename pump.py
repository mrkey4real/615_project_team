"""
Pump Module - Fluid Dynamics Based Calculations

This module implements pump power calculations based on fundamental
fluid dynamics principles.

Key Features:
- Fluid dynamics based power calculation: P = ρ × g × H × Q / η
- Head calculations (static + dynamic + equipment losses)
- Energy balance verification
- Multiple pump configurations (chilled water, condenser water, GPU coolant)

Author: HVAC Team
Date: 2025-11-10
"""


class Pump:
    """
    Models centrifugal pump using fluid dynamics principles.

    Energy Balance:
        Fluid energy increase: ΔE_fluid = ṁ × g × H
        Pump power input: P_pump = ΔE_fluid / η_pump
        Or: P_pump = (ρ × g × H × Q) / η_pump

    Variables:
        ρ: Fluid density (kg/m³)
        g: Gravitational acceleration (9.81 m/s²)
        H: Total head (m) = H_static + H_dynamic + H_equipment
        Q: Volume flow rate (m³/s)
        η_pump: Pump efficiency (0-1)
        P_pump: Pump power (W)
    """

    def __init__(
        self,
        pump_type,
        static_head=10.0,
        dynamic_head_factor=0.5,
        equipment_head=5.0,
        efficiency=0.85,
    ):
        """
        Initialize pump module.

        Args:
            pump_type: Pump type identifier ('CHW', 'CW', 'GPU')
            static_head: Static head due to elevation (m)
            dynamic_head_factor: Factor for velocity head (-)
            equipment_head: Equipment resistance head (m)
            efficiency: Pump efficiency (0-1)

        Raises:
            ValueError: If parameters are invalid
        """
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


if __name__ == "__main__":
    """
    Test pump module with typical datacenter conditions.
    """
    print("\n" + "=" * 80)
    print("PUMP MODULE TEST - Typical Datacenter Conditions")
    print("=" * 80)

    # Test individual pump
    print("\n--- INDIVIDUAL PUMP TEST ---")
    chw_pump = Pump(
        pump_type="CHW",
        static_head=15.0,  # 15m elevation
        equipment_head=8.0,  # Equipment losses
        efficiency=0.85,
    )

    m_dot = 47770  # kg/s chilled water
    result = chw_pump.solve(m_dot=m_dot, velocity=2.5)

    print(f"\nChilled Water Pump:")
    print(f"  Flow Rate:            {result['m_dot_kg_s']:.0f} kg/s  ({result['Q_L_s']:.0f} L/s)")
    print(f"  Static Head:          {result['H_static_m']:.1f} m")
    print(f"  Equipment Head:       {result['H_equipment_m']:.1f} m")
    print(f"  Total Head:           {result['H_total_m']:.1f} m")
    print(f"  Efficiency:           {result['efficiency']*100:.1f} %")
    print(f"  Pump Power:           {result['P_pump_MW']:.2f} MW")
    print(f"  Energy to Fluid:      {result['E_fluid_W']/1e6:.2f} MW")

    # Test complete pump system
    print("\n--- COMPLETE PUMP SYSTEM TEST ---")
    pump_system = PumpSystem(
        chw_static_head=15.0, cw_static_head=10.0, gpu_static_head=5.0
    )

    # Typical 1 GW datacenter flows
    m_dot_chw = 47770  # kg/s
    m_dot_cw = 50000  # kg/s
    m_dot_gpu = 8600  # kg/s

    system_result = pump_system.solve_all_pumps(
        m_dot_chw=m_dot_chw, m_dot_cw=m_dot_cw, m_dot_gpu=m_dot_gpu
    )

    print(f"\nPump System Summary:")
    print(f"  CHW Pump Power:       {system_result['CHW_pump']['P_pump_MW']:.2f} MW")
    print(f"  CW Pump Power:        {system_result['CW_pump']['P_pump_MW']:.2f} MW")
    print(f"  GPU Pump Power:       {system_result['GPU_pump']['P_pump_MW']:.2f} MW")
    print(f"  Total Pump Power:     {system_result['P_total_MW']:.2f} MW")

    # Compare with simple fraction method
    print("\n--- COMPARISON WITH SIMPLE METHOD ---")
    q_cooling = 1000e6  # 1000 MW
    q_gpu = 900e6  # 900 MW

    p_chw_simple = chw_pump.calculate_power_simple(q_cooling, 0.025)  # 2.5%
    p_cw_simple = chw_pump.calculate_power_simple(q_cooling, 0.018)  # 1.8%
    p_gpu_simple = chw_pump.calculate_power_simple(q_gpu, 0.015)  # 1.5%
    p_total_simple = p_chw_simple + p_cw_simple + p_gpu_simple

    print(f"\nSimple Fraction Method:")
    print(f"  CHW Pump (2.5%):      {p_chw_simple/1e6:.2f} MW")
    print(f"  CW Pump (1.8%):       {p_cw_simple/1e6:.2f} MW")
    print(f"  GPU Pump (1.5%):      {p_gpu_simple/1e6:.2f} MW")
    print(f"  Total:                {p_total_simple/1e6:.2f} MW")

    print(f"\nFluid Dynamics Method:")
    print(f"  Total:                {system_result['P_total_MW']:.2f} MW")

    print(f"\nDifference:             {abs(p_total_simple - system_result['P_total_W'])/1e6:.2f} MW")
    print("=" * 80 + "\n")
