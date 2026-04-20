# fix-planning-config-act-chapter-split

## 问题

全托管模式使用精密规划时，小说结构参数（parts/volumes_per_part/acts_per_volume）没有被幕拆章节使用。

## 根因

`autopilot_daemon.py` 读取 `planning_config` 时，直接访问 `config.parts` 等顶层属性：

```python
# autopilot_daemon.py:442-446
structure_preference = {
    'parts': getattr(config, 'parts', 1),
    'volumes_per_part': getattr(config, 'volumes_per_part', 1),
    'acts_per_volume': getattr(config, 'acts_per_volume', 4),
}
```

但 `PlanningConfig` 的 `parts/volumes_per_part/acts_per_volume` 是顶层属性，而前端传递的结构参数包装在 `structure` 字段里。`Novel` 实体存储时没有将 `structure` 正确映射到顶层属性，导致 `_generate_macro_plan_if_needed` 调用时 `structure_preference` 永远取默认值，精密规划失效。

## 修复

在 `autopilot_daemon.py` 添加 `structure` 字段解包逻辑：从 `planning_config.structure`（如果存在）读取结构参数，而非直接读顶层属性。

## 影响范围

- `application/engine/services/autopilot_daemon.py` - `_generate_macro_plan_if_needed`
