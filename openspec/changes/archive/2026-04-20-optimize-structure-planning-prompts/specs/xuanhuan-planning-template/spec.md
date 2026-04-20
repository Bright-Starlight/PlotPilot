## ADDED Requirements

### Requirement: Xuanhuan Planning Prompt Template
The xuanhuan-planning-template SHALL generate structure plans tailored for xuanhuan (fantasy cultivation) novels, with adaptive emphasis based on sub-genres.

#### Scenario: Cultivation progression focus
- **WHEN** sub_genres include "修炼升级流"
- **THEN** the prompt emphasizes realm breakthroughs, escalating power tiers, and satisfying upgrade moments

#### Scenario: Mortal/grassroots focus
- **WHEN** sub_genres include "凡人流" or "苟道流"
- **THEN** the prompt emphasizes resource competition, cautious development, and underdog victories

#### Scenario: System/interface focus
- **WHEN** sub_genres include "系统流"
- **THEN** the prompt emphasizes task-reward cycles, quantified progression, and system mechanics integration

#### Scenario: Invincible/bottom-tier focus
- **WHEN** sub_genres include "无敌流"
- **THEN** the prompt emphasizes overwhelming power displays, enemy reactions, and satisfying crushing moments

#### Scenario: Infinite/anthology focus
- **WHEN** sub_genres include "无限流" or "综漫"
- **THEN** the prompt emphasizes dungeon/instance structure, world-switching, and variety of challenges

#### Scenario: Multiple sub-genres combined
- **WHEN** sub_genres include multiple types (e.g., "系统流+凡人流")
- **THEN** the prompt blends corresponding emphases proportionally

### Requirement: Xuanhuan Sub-genre Adaptive Tone
The xuanhuan planning prompt SHALL adjust system prompt tone based on sub-genre combinations.

#### Scenario: Lighthearted cultivation tone
- **WHEN** sub_genres indicate casual/satisfying tone
- **THEN** the system prompt describes the writer as "擅长玄幻爽文，精通修炼体系设定和升级节奏控制"

#### Scenario: Dark survival tone
- **WHEN** sub_genres indicate survival/competition tone
- **THEN** the system prompt emphasizes "资源争夺"、"生存压力"、"厚黑发育"
