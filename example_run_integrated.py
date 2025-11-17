
from hvac_integrated import IntegratedHVACSystem
import json

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
    t_db_C=None,
    chiller_cop=6.0,
)
out = system.solve()
from hvac_integrated import to_jsonable
print(json.dumps(to_jsonable(out), indent=2))
