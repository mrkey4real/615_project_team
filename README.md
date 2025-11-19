# HVAC集成系统

数据中心冷却系统的热力学建模模块，采用精确的能量和质量守恒计算。

## 快速开始

### 安装依赖

```bash
pip install CoolProp>=6.5.0
```

### 运行示例

```bash
python main.py
```

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    HVAC集成系统                              │
│                                                              │
│  ┌────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │ 空气循环    │───▶│ 热交换器      │◀───│ 冷却系统      │   │
│  │ Air Loop   │    │ Heat Exchange│    │ Cooling Sys  │   │
│  └────────────┘    └──────────────┘    └──────────────┘   │
│                                              │              │
│                                              │              │
│                                    ┌─────────┴─────────┐   │
│                                    │                   │   │
│                              ┌─────▼────┐      ┌──────▼────┐
│                              │ 冷水机    │      │ 冷却塔     │
│                              │ Chiller  │◀────▶│ Cooling   │
│                              │          │      │ Tower     │
│                              └──────────┘      └───────────┘
└─────────────────────────────────────────────────────────────┘
```

## 文件结构

```
├── main.py                 # 主程序（运行示例）
├── cooling_system.py       # 统一入口模块（导出所有组件）
├── hvac_integrated.py      # HVAC集成系统
├── chiller.py             # 冷水机模块
├── cooling_tower.py       # 冷却塔模块
├── pump.py                # 泵系统模块
├── psychrometrics.py      # 湿空气热力学
├── refrigerant_cycle.py   # 制冷循环计算
├── README.md              # 本文件（用户文档）
└── claude.md              # 开发文档
```

**注意**：`cooling_system.py` 是统一入口，导入所有HVAC组件。使用时只需：
```python
from cooling_system import IntegratedHVACSystem
```

## 核心模块

### 1. 集成HVAC系统 (`hvac_integrated.py`)

完整的HVAC系统，包括空气循环、热交换器和冷却系统。

**使用示例：**
```python
from cooling_system import IntegratedHVACSystem

system = IntegratedHVACSystem(
    pump_power_W=250_000.0,
    air_delta_p_Pa=900.0,
    air_eta=0.65,
    t_air_in_C=20.0,
    q_air_load_W=100e6,          # 100 MW
    t_air_max_C=25.0,
    t_chw_supply_C=7.0,
    deltaT_chw_design_C=5.0,
    hx_effectiveness=0.80,
    t_wb_C=24.0,
    t_db_C=35.0,
    chiller_cop=6.0,
)

results = system.solve()
```

**输出结构：**
- `for_heat_exchanger`: 下游接口（供热交换器使用）
- `internal_diagnostics`: 内部诊断（用于监控）

### 2. 冷却系统 (`cooling_system.py`)

冷水机和冷却塔的集成模块，自动处理两者的耦合迭代。

**使用示例：**
```python
from cooling_system import CoolingSystem

cooling_sys = CoolingSystem(
    chiller_capacity_MW=100.0,
    chiller_cop=6.0,
    t_chw_supply_C=7.0,
    tower_approach_C=4.0,
    tower_coc=4.0,
)

result = cooling_sys.solve(
    q_cooling_load_W=100e6,
    m_dot_chw_kg_s=4777,
    t_chw_return_C=12.0,
    t_wb_ambient_C=24.0,
    t_db_ambient_C=35.0,
)
```

**输出结构：**
- `downstream_interface`: 下游接口
- `internal_states`: 内部状态（冷水机、冷却塔详细信息）

### 3. 冷水机 (`chiller.py`)

基于蒸气压缩制冷循环的冷水机模型。

**特点：**
- 使用CoolProp计算制冷剂热力学性质
- 完整的制冷循环：蒸发器、压缩机、冷凝器、膨胀阀
- 能量守恒：Q_蒸发 + W_压缩机 = Q_冷凝
- 支持制冷剂：R134a

**关键参数：**
- 压缩机等熵效率：80%
- 蒸发器过热度：5°C
- 冷凝器过冷度：3°C

### 4. 冷却塔 (`cooling_tower.py`)

基于湿空气热力学的冷却塔模型。

**特点：**
- 精确的能量平衡（误差 < 0.01%）
- 从能量守恒反算空气流量
- 完整的质量守恒：蒸发、飘水、排污、补水
- 使用Antoine方程计算饱和蒸气压

**关键参数：**
- 接近温度（Approach）：4°C
- 浓缩倍数（COC）：4-6
- 飘水率：0.001%

### 5. 泵系统 (`pump.py`)

基于流体力学的泵功率计算。

**特点：**
- 公式：P = (ρ × g × H × Q) / η
- 包含：冷却水泵（CW pump）
- 扬程计算：静态扬程 + 动态扬程 + 设备阻力

## 主要功能

### ✅ 精确的热力学计算

- 冷水机：完整的制冷循环，使用CoolProp
- 冷却塔：湿空气热力学，精确的能量和质量平衡
- 能量平衡误差 < 0.01%

### ✅ 模块化设计

- 清晰的接口定义
- 下游接口和内部诊断分离
- 易于集成和扩展

### ✅ 迭代求解

- 自动处理冷水机-冷却塔耦合
- 可配置的收敛条件
- 稳定的数值求解

## 输入参数说明

### HVAC集成系统输入

| 参数 | 单位 | 说明 |
|------|------|------|
| `q_air_load_W` | W | 空气冷却负荷 |
| `t_air_in_C` | °C | 进气温度 |
| `t_chw_supply_C` | °C | 冷冻水供水温度 |
| `t_wb_C` | °C | 环境湿球温度 |
| `t_db_C` | °C | 环境干球温度 |
| `chiller_cop` | - | 冷水机COP |

### 冷却系统输入

| 参数 | 单位 | 说明 |
|------|------|------|
| `q_cooling_load_W` | W | 冷却负荷 |
| `m_dot_chw_kg_s` | kg/s | 冷冻水流量 |
| `t_chw_return_C` | °C | 冷冻水回水温度 |
| `t_wb_ambient_C` | °C | 环境湿球温度 |
| `t_db_ambient_C` | °C | 环境干球温度（可选）|

## 输出结果说明

### 下游接口（for_heat_exchanger）

关键参数供下游组件使用：

```python
{
    'T_chw_supply_C': 7.0,        # 冷冻水供水温度
    'T_chw_return_C': 12.0,       # 冷冻水回水温度
    'm_dot_chw_kg_s': 4777,       # 冷冻水流量
    'Q_cooling_MW': 100.0,        # 冷却容量
    'system_COP': 5.8,            # 系统COP
    'total_power_MW': 17.2,       # 总功率
}
```

### 内部诊断（internal_diagnostics）

详细的系统状态信息：

```python
{
    'cooling_system': {
        'chiller': {
            'COP': 6.0,
            'W_comp_MW': 16.7,
            'T_evap_sat_C': 5.0,
            'T_cond_sat_C': 40.0,
        },
        'cooling_tower': {
            'approach_C': 4.0,
            'm_makeup_L_hr': 458000,
        },
        'energy_balance': {
            'chiller_error_pct': 0.0001,
            'tower_error_pct': 0.0001,
        }
    }
}
```

## 性能指标

### PUE (Power Usage Effectiveness)

```
PUE = (IT功率 + 冷却功率) / IT功率
```

典型值：1.10 - 1.20（优秀）

### WUE (Water Usage Effectiveness)

```
WUE = 年用水量(L) / 年IT能耗(kWh)
```

典型值：0.6 - 0.8 L/kWh

## 能量平衡验证

系统自动验证所有能量守恒：

- **冷水机**：Q_蒸发 + W_压缩机 = Q_冷凝
- **冷却塔**：Q_水侧 = Q_空气侧
- **验收标准**：误差 < 1%（当前实现 < 0.01%）

## 常见问题

### Q1: 如何修改制冷剂？

在创建冷水机时指定：
```python
chiller = Chiller(refrigerant="R134a")  # 默认
```

### Q2: 如何调整冷却塔性能？

修改接近温度和浓缩倍数：
```python
cooling_sys = CoolingSystem(
    tower_approach_C=3.0,  # 更小的接近温度 = 更好的性能
    tower_coc=5.0,         # 更高的COC = 更少的补水
)
```

### Q3: 系统不收敛怎么办？

检查输入参数是否合理，或增加最大迭代次数：
```python
result = cooling_sys.solve(..., max_iter=100, tolerance=0.05)
```

## 开发文档

详细的开发文档和系统架构说明请参见 [claude.md](./claude.md)

## 依赖库

- Python >= 3.8
- CoolProp >= 6.5.0

## 版本历史

### v1.2 (2025-11-19)
- 代码清理，删除冗余示例代码
- 创建简单的main.py作为运行入口
- 创建cooling_system.py作为统一模块入口
- 优化文档结构，分离用户文档和开发文档

### v1.1 (2025-11-10)
- 修复冷却塔能量平衡（误差从17.3%降至<0.01%）
- 明确泵系统范围（HVAC只包含CW泵）
- 创建集成模块（hvac_integrated.py, cooling_system.py）

### v1.0 (2025-11-10)
- 初始版本
- 完整的热力学建模
- 冷水机、冷却塔、泵系统集成

## 参考资料

- ASHRAE Handbook - Fundamentals (2021)
- CoolProp Documentation: http://www.coolprop.org/
- 蒸气压缩制冷循环理论
- 湿空气热力学原理

---

**开发团队**: HVAC Team
**最后更新**: 2025-11-19
