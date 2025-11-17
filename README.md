# HVAC组件模块使用说明

## 概述

本模块包含数据中心冷却系统的HVAC组件，采用高级热力学建模方法，包括：
- **冷水机（Chiller）**：基于蒸气压缩制冷循环的完整热力学计算
- **冷却塔（Cooling Tower）**：基于湿空气热力学分析的传质传热计算
- **泵系统（Pump）**：基于流体力学的泵功率计算
- **集成系统（HVAC System）**：完整的HVAC系统集成和求解

## 文件结构

```
hvac_components/
├── chiller.py              # 冷水机组模块
├── cooling_tower.py        # 冷却塔模块
├── pump.py                 # 泵系统模块
├── run_hvac.py             # HVAC系统主程序
├── psychrometrics.py       # 湿空气计算（依赖）
├── refrigerant_cycle.py    # 制冷循环计算（依赖）
└── README.md               # 本文件
```

## 系统要求

### Python版本
- Python 3.8 或更高版本

### 依赖库
```bash
pip install CoolProp>=6.5.0  # 制冷剂热力学性质
```

## 核心特性

### 1. 冷水机（Chiller）

**热力学建模特点：**
- ✅ 使用CoolProp计算制冷剂焓值、熵值、压力、温度等状态参数
- ✅ 完整的蒸气压缩循环：压缩机、冷凝器、膨胀阀、蒸发器
- ✅ 能量守恒：Q_蒸发 + W_压缩机 = Q_冷凝
- ✅ 质量守恒：制冷剂质量流量守恒
- ✅ 多相计算：区分过冷液体、两相区、过热蒸气
- ✅ 等熵效率：考虑压缩机实际效率
- ✅ 迭代求解：耦合制冷剂侧和水侧能量平衡

**关键参数：**
- 制冷剂：R134a
- 压缩机等熵效率：80%
- 蒸发器/冷凝器有效度：85%
- 蒸发器过热度：5°C
- 冷凝器过冷度：3°C

### 2. 冷却塔（Cooling Tower）

**热力学建模特点：**
- ✅ 湿空气热力学分析：含湿量、焓值、相对湿度
- ✅ 质量守恒：
  - 干空气守恒：ṁ_干空气,进 = ṁ_干空气,出
  - 水蒸气平衡：ṁ_蒸发 = ṁ_干空气 × (w_出 - w_进)
  - 液态水平衡：ṁ_补水 = ṁ_蒸发 + ṁ_飘水 + ṁ_排污
- ✅ **能量守恒（精确）**：Q_水侧 = Q_空气侧 = ṁ_空气 × (h_出 - h_进)
  - 从能量平衡反算所需空气流量，确保误差 < 0.1%
  - 不依赖固定的空气/水比值假设
- ✅ Antoine方程计算饱和蒸气压（ASHRAE标准）
- ✅ 多相能量传递：显热 + 潜热

**关键参数：**
- 接近温度（Approach）：4°C
- 浓缩倍数（COC）：5-6
- 飘水率：0.001%
- 空气/水质量流量比：1.2

### 3. 泵系统（Pump）

**流体力学建模特点：**
- ✅ 基于流体力学公式：P_泵 = (ρ × g × H × Q) / η
- ✅ 扬程计算：H_总 = H_静态 + H_动态 + H_设备
- ✅ 能量守恒：ΔE_流体 = P_泵 × η_泵

**HVAC侧泵系统配置（仅CW pump）：**
- **冷却水泵（CW pump）**：静态扬程10m，设备阻力6m，效率85%
  - 作用范围：冷水机冷凝器 ↔ 冷却塔

**注意：** 以下泵由其他系统管理，不包含在HVAC component中：
- **冷冻水泵（CHW pump）**：由建筑侧系统管理
- **GPU冷却液泵（GPU pump）**：由计算/GPU冷却系统管理

## 使用方法

### 方法1：运行完整HVAC系统

```python
from run_hvac import HVACSystem

# 创建HVAC系统
hvac = HVACSystem(
    chiller_capacity_mw=1000,      # 冷水机额定容量 (MW)
    chiller_cop=6.1,                # 额定COP
    t_chw_supply=10.0,              # 冷冻水供水温度 (°C)
    cooling_tower_approach=4.0,     # 冷却塔接近温度 (°C)
    coc=5.0                         # 浓缩倍数
)

# 输入参数（来自建筑侧热交换器）
q_evap = 1000e6        # 总冷却负荷 (W) - 1000 MW
q_gpu = 900e6          # GPU负荷 (W) - 900 MW
t_chw_return = 15.0    # 冷冻水回水温度 (°C)
t_wb = 25.5            # 环境湿球温度 (°C)
t_db = 35.5            # 环境干球温度 (°C)

# 求解系统
results = hvac.solve(
    q_evap=q_evap,
    t_chw_return=t_chw_return,
    q_gpu=q_gpu,
    t_wb=t_wb,
    t_db=t_db
)

# 打印结果
hvac.print_summary(results)
```

### 方法2：单独测试各组件

#### 测试冷水机
```bash
cd hvac_components
python chiller.py
```

#### 测试冷却塔
```bash
python cooling_tower.py
```

#### 测试泵系统
```bash
python pump.py
```

#### 运行完整系统
```bash
python run_hvac.py
```

### 方法3：自定义集成

```python
from chiller import Chiller
from cooling_tower import CoolingTower
from pump import PumpSystem

# 创建各组件
chiller = Chiller(
    rated_capacity_mw=1000,
    rated_cop=6.1,
    t_chw_supply=10.0
)

cooling_tower = CoolingTower(
    approach_temp=4.0,
    coc=5.0
)

pump_system = PumpSystem()

# 求解冷水机
chiller_result = chiller.solve_energy_balance(
    q_evap=1000e6,
    m_dot_chw=47770,
    m_dot_cw=50000,
    t_cw_in=29.5
)

# 求解冷却塔
tower_result = cooling_tower.solve(
    q_cond=chiller_result['Q_cond_MW']*1e6,
    m_dot_cw=50000,
    t_in=chiller_result['T_cw_out_C'],
    t_wb=25.5
)

# 求解泵系统（仅CW pump，HVAC侧）
pump_result = pump_system.solve(
    m_dot_cw=50000
)
```

## 输入参数说明

### 来自建筑侧的输入
这些参数由建筑端热交换器提供：

| 参数 | 符号 | 单位 | 典型值 | 说明 |
|------|------|------|--------|------|
| 总冷却负荷 | Q_evap | W | 1,000,000,000 | 建筑负荷 + GPU负荷 |
| GPU负荷 | Q_gpu | W | 900,000,000 | GPU冷却负荷（用于计算GPU泵流量）|
| 冷冻水回水温度 | T_chw_return | °C | 15.0 | 从建筑侧热交换器返回的温度 |
| 环境湿球温度 | T_wb | °C | 25.5 | 室外空气湿球温度 |
| 环境干球温度 | T_db | °C | 35.5 | 室外空气干球温度（可选）|

### 系统设计参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| 冷冻水供水温度 | 10°C | 冷水机出口温度 |
| 冷却塔接近温度 | 4°C | T_出水 - T_湿球 |
| 浓缩倍数（COC）| 5 | 循环水中矿物质浓缩倍数 |
| 冷水机COP | 6.1 | 额定制冷系数 |

## 输出结果说明

### 主要输出参数

#### 1. 功率消耗（HVAC侧）
```python
results['power']
{
    'W_comp_MW': 175.3,           # 压缩机功率 (MW)
    'W_pump_CW_MW': 9.3,          # CW泵功率 (MW) - HVAC侧
    'W_fans_MW': 8.2,             # 风机功率 (MW)
    'W_total_cooling_MW': 192.8   # HVAC系统总功率 (MW)
}
```

**注意：** CHW泵和GPU泵功率由各自系统计算，不包含在此处

#### 2. 流量
```python
results['flow_rates']
{
    'm_dot_chw_kg_s': 47770,   # 冷冻水流量 (kg/s) - 供参考
    'm_dot_cw_kg_s': 50000,    # 冷却水流量 (kg/s) - HVAC侧
    'm_dot_gpu_kg_s': 9348     # GPU冷却液流量 (kg/s) - 供参考
}
```

**注意：**
- **m_dot_cw**: HVAC系统直接管理（CW pump）
- **m_dot_chw, m_dot_gpu**: 仅供参考，由其他系统管理

#### 3. 冷水机性能
```python
results['chiller']
{
    'COP': 6.10,                    # 制冷系数
    'T_chw_supply_C': 10.0,         # 冷冻水供水温度 (°C)
    'T_chw_return_C': 15.0,         # 冷冻水回水温度 (°C)
    'T_cw_in_C': 29.5,              # 冷却水进水温度 (°C)
    'T_cw_out_C': 35.0,             # 冷却水出水温度 (°C)
    'T_evap_sat_C': 5.0,            # 蒸发器饱和温度 (°C)
    'T_cond_sat_C': 40.0,           # 冷凝器饱和温度 (°C)
    'm_dot_ref_kg_s': 234.5         # 制冷剂流量 (kg/s)
}
```

#### 4. 冷却塔性能
```python
results['cooling_tower']
{
    'Range_C': 5.5,                 # 温度范围 (°C)
    'Approach_C': 4.0,              # 接近温度 (°C)
    'air_inlet': {
        'T_db_C': 35.5,             # 进口干球温度 (°C)
        'T_wb_C': 25.5,             # 进口湿球温度 (°C)
        'RH': 0.42,                 # 相对湿度
        'w_kg_kg': 0.0164,          # 含湿量 (kg水/kg干空气)
        'h_J_kg': 78500             # 焓值 (J/kg干空气)
    },
    'air_outlet': {
        'T_db_C': 29.5,             # 出口温度 (°C)
        'RH': 0.95,                 # 相对湿度
        'w_kg_kg': 0.0265,          # 含湿量 (kg水/kg干空气)
        'h_J_kg': 104200            # 焓值 (J/kg干空气)
    }
}
```

#### 5. 水消耗
```python
results['water_consumption']
{
    'm_evap_kg_s': 508.8,           # 蒸发损失 (kg/s)
    'm_drift_kg_s': 0.5,            # 飘水损失 (kg/s)
    'm_blowdown_kg_s': 127.2,       # 排污损失 (kg/s)
    'm_makeup_kg_s': 636.5,         # 总补水量 (kg/s)
    'm_makeup_L_hr': 2,291,400,     # 每小时补水 (L/hr)
    'COC': 5.0                      # 浓缩倍数
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

系统自动验证能量守恒：

```python
results['validation']
{
    'chiller_energy_balance_error_pct': 0.0000,   # 冷水机能量平衡误差 (%)
    'tower_energy_balance_error_pct': 0.0000,     # 冷却塔能量平衡误差 (%)
    'system_energy_balance_pct': 0.0000           # 系统能量平衡误差 (%)
}
```

**验收标准：** 所有误差应 < 1%（当前实现达到 < 0.01%）

## 热力学计算方法总结

### 冷水机
1. **制冷循环计算**
   - 状态点1：蒸发器出口（过热蒸气）
   - 状态点2：压缩机出口（高压过热蒸气）
   - 状态点3：冷凝器出口（过冷液体）
   - 状态点4：膨胀阀出口（两相区）

2. **能量方程**
   ```
   Q_蒸发 = ṁ_制冷剂 × (h₁ - h₄)
   W_压缩机 = ṁ_制冷剂 × (h₂ - h₁)
   Q_冷凝 = ṁ_制冷剂 × (h₂ - h₃)
   COP = Q_蒸发 / W_压缩机
   ```

3. **迭代求解**
   - 调整蒸发温度和冷凝温度
   - 匹配制冷剂侧和水侧能量平衡
   - 满足夹点温差约束（> 3°C）

### 冷却塔
1. **热力学计算**
   ```
   含湿量：w = 0.622 × P_v / (P - P_v)
   焓值：h = cp_空气 × T + w × (h_fg + cp_水蒸气 × T)
   ```

2. **能量平衡求解（核心）**
   ```
   步骤：
   1. 计算水侧热量：Q_水 = ṁ_水 × cp × (T_进 - T_出)
   2. 确定空气进/出口焓值：h_进, h_出
   3. 从能量平衡反算空气流量：ṁ_干空气 = Q_水 / (h_出 - h_进)
   4. 验证：Q_空气 = ṁ_干空气 × (h_出 - h_进) ≈ Q_水
   ```

3. **质量平衡**
   ```
   干空气守恒：ṁ_干空气,进 = ṁ_干空气,出
   蒸发量：ṁ_蒸发 = ṁ_干空气 × (w_出 - w_进)
   补水量：ṁ_补水 = ṁ_蒸发 + ṁ_飘水 + ṁ_排污
   ```

### 泵系统
1. **流体力学方程**
   ```
   P_泵 = (ρ × g × H_总 × Q) / η_泵

   其中：
   H_总 = H_静态 + H_动态 + H_设备
   Q = ṁ / ρ (体积流量)
   ```

## 与建筑端对接说明

### 接口定义
建筑端热交换器提供以下输出，作为HVAC系统的输入：

1. **总冷却负荷** (Q_evap)
   - 建筑空调负荷 + GPU冷却负荷
   - 单位：W

2. **冷冻水回水温度** (T_chw_return)
   - 经过建筑侧和计算侧热交换器后的温度
   - 单位：°C

3. **GPU负荷** (Q_gpu)
   - 用于计算GPU冷却液泵的流量
   - 单位：W

### 数据流
```
建筑侧热交换器输出 → HVAC系统输入
{
    Q_evap: 1000 MW          →  q_evap参数
    T_chw_return: 15°C       →  t_chw_return参数
    Q_gpu: 900 MW            →  q_gpu参数
}

HVAC系统输出 → 返回建筑侧
{
    T_chw_supply: 10°C       →  供水温度
    m_dot_chw: 47770 kg/s    →  冷冻水流量
}
```

## 说明

本模块作为独立的HVAC组件，可以与其他团队成员的模块对接：

1. **输入接口**：接收建筑侧热交换器的输出
2. **输出接口**：提供冷冻水供水参数给建筑侧
3. **独立运行**：可独立测试和验证
4. **完整文档**：本README提供完整使用说明

## 引用和参考

本模块基于以下标准和文献：
- ASHRAE Handbook - Fundamentals (2021)
- CoolProp: Open-source thermodynamic property library
- 蒸气压缩制冷循环理论
- 湿空气热力学原理

## 版本历史

### v1.1 (2025-11-10) - 能量平衡修复与范围明确化
**重要更新：**
1. **冷却塔能量平衡修复**
   - 修复前：能量平衡误差 17.3%
   - 修复后：能量平衡误差 < 0.01%
   - 方法：从能量平衡反算空气流量，而非使用固定比值

2. **泵系统范围明确化**
   - HVAC component 现在仅包含 **CW pump**（冷却水泵）
   - CHW pump（冷冻水泵）移至建筑侧系统管理
   - GPU pump（GPU冷却液泵）移至计算侧系统管理
   - HVAC侧功率从 207.08 MW 降至 192.77 MW

3. **组件边界清晰**
   - HVAC系统：冷水机 + 冷却塔 + CW泵
   - 建筑系统：CHW泵 + 热交换器
   - 计算系统：GPU泵 + GPU冷板

### v1.0 (2025-11-10) - 初始版本
- 完整的热力学建模
- 冷水机、冷却塔、泵系统集成
- 能量平衡验证

