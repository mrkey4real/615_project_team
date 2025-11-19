"""
HVAC集成系统示例程序

这是一个简单的示例，展示如何使用HVAC集成系统进行计算。
系统包括：冷水机、冷却塔、泵系统、热交换器和空气循环。

运行方法：
    python main.py
"""

from cooling_system import IntegratedHVACSystem, to_jsonable
import json


def main():
    """运行HVAC系统示例"""

    print("=" * 80)
    print("HVAC集成系统 - 示例运行")
    print("=" * 80)

    # 创建集成HVAC系统
    system = IntegratedHVACSystem(
        pump_power_W=250_000.0,          # 泵功率 (W)
        air_delta_p_Pa=900.0,            # 空气压降 (Pa)
        air_eta=0.65,                    # 风机效率
        t_air_in_C=20.0,                 # 进气温度 (°C)
        q_air_load_W=100e6,              # 空气冷却负荷 (W) = 100 MW
        t_air_max_C=25.0,                # 最大出气温度 (°C)
        t_chw_supply_C=7.0,              # 冷冻水供水温度 (°C)
        deltaT_chw_design_C=5.0,         # 冷冻水设计温差 (°C)
        hx_effectiveness=0.80,           # 热交换器效率
        t_wb_C=24.0,                     # 环境湿球温度 (°C)
        t_db_C=35.0,                     # 环境干球温度 (°C)
        chiller_cop=6.0,                 # 冷水机COP
    )

    print("\n输入参数：")
    print(f"  空气冷却负荷:        {100.0:.1f} MW")
    print(f"  冷冻水供水温度:      {7.0:.1f} °C")
    print(f"  环境温度:            {35.0:.1f}°C (干球), {24.0:.1f}°C (湿球)")
    print(f"  冷水机COP:           {6.0:.1f}")

    # 求解系统
    print("\n正在求解系统...")
    results = system.solve()

    # 提取关键结果
    hx_interface = results["for_heat_exchanger"]

    print("\n" + "=" * 80)
    print("系统运行结果")
    print("=" * 80)

    print("\n--- 热交换器接口 ---")
    print(f"  冷冻水供水温度:      {hx_interface['T_chw_supply_C']:.2f} °C")
    print(f"  冷冻水回水温度:      {hx_interface['T_chw_return_C']:.2f} °C")
    print(f"  冷冻水流量:          {hx_interface['m_dot_chw_kg_s']:.0f} kg/s")
    print(f"  冷冻水温差:          {hx_interface['deltaT_chw_C']:.2f} °C")
    print(f"  冷却容量:            {hx_interface['Q_cooling_MW']:.1f} MW")
    print(f"  系统COP:             {hx_interface['system_COP']:.2f}")
    print(f"  总功率:              {hx_interface['total_power_MW']:.2f} MW")

    # 内部诊断摘要
    diag = results["internal_diagnostics"]

    print("\n--- 系统性能摘要 ---")
    print(f"  冷水机COP:           {diag['cooling_system']['chiller']['COP']:.2f}")
    print(f"  压缩机功率:          {diag['cooling_system']['chiller']['W_comp_MW']:.1f} MW")
    print(f"  冷却塔接近温度:      {diag['cooling_system']['cooling_tower']['approach_C']:.1f} °C")
    print(f"  补水量:              {diag['cooling_system']['cooling_tower']['m_makeup_L_hr']:,.0f} L/hr")

    print("\n--- 能量平衡验证 ---")
    print(f"  冷水机能量平衡误差:  {diag['cooling_system']['energy_balance']['chiller_error_pct']:.4f} %")
    print(f"  冷却塔能量平衡误差:  {diag['cooling_system']['energy_balance']['tower_error_pct']:.4f} %")

    print("\n" + "=" * 80)
    print("计算完成！")
    print("=" * 80)

    # 可选：保存完整结果到JSON文件
    save_results = input("\n是否保存完整结果到 results.json? (y/n): ").strip().lower()
    if save_results == 'y':
        with open('results.json', 'w', encoding='utf-8') as f:
            json.dump(to_jsonable(results), f, indent=2, ensure_ascii=False)
        print("结果已保存到 results.json")


if __name__ == "__main__":
    main()
