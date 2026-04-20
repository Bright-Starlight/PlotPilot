## Context

全托管模式精密规划时，`autopilot_daemon.py` 读取 `planning_config` 结构参数失效。

当前数据流：
1. 前端传入 `planning_config` = `{plan_mode: "precise", structure: {parts: 3, volumes_per_part: 3, acts_per_volume: 3}}`
2. `novel_service.create_novel` 接收 `planning_config` 字典，尝试构建 `PlanningConfig` 实体
3. `autopilot_daemon._generate_macro_plan_if_needed` 读取 `planning_config`，直接访问 `config.parts`

问题：`PlanningConfig` 有顶层属性 `parts/volumes_per_part/acts_per_volume`，但前端数据包装在 `structure` 字段内。两边字段名不匹配，导致精密规划参数永远取默认值。

## Goals / Non-Goals

**Goals:**
- 修复精密规划参数传递链路，确保 `parts/volumes_per_part/acts_per_volume` 正确传递到 LLM

**Non-Goals:**
- 不修改 `PlanningConfig` 数据模型结构（保持向后兼容）
- 不修改前端 API 契约

## Decisions

**决策：优先从 `structure` 子字典读取结构参数**

数据流中 `structure` 字段是实际承载结构参数的位置。`autopilot_daemon.py` 直接访问顶层属性会 miss 掉 `structure`。

替代方案：
1. 修改 `PlanningConfig.__init__` 自动从 `structure` 解包到顶层属性 → 改动大，影响其他调用方
2. 在 `autopilot_daemon.py` 加 `structure` 解包逻辑 → 最小改动，只改一处

选方案 2。

## Risks / Trade-offs

[Risk] `structure` 字段不存在时 → 降级读顶层属性（兼容旧数据）
[Risk] `structure` 是 `None` 而不是字典 → 加 `isinstance` 检查
[Risk] 未来 `PlanningConfig` 顶层属性被废弃 → 届时删除兼容逻辑

## Migration Plan

无需数据迁移，纯代码改动。
回滚：git revert 即可。
