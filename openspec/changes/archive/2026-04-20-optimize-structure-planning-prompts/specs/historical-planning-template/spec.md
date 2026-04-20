## ADDED Requirements

### Requirement: Historical Planning Prompt Template
The historical-planning-template SHALL generate structure plans tailored for historical novels, with adaptive emphasis based on sub-genres.

#### Scenario: Court political focus
- **WHEN** sub_genres include "朝堂权谋" or "官场"
- **THEN** the prompt emphasizes factional struggles, political intrigue, and character decisions within historical context

#### Scenario: Harem/romance focus
- **WHEN** sub_genres include "后宫" or "宫斗"
- **THEN** the prompt emphasizes romantic tension, identity reversals, relationship webs, and emotional stakes

#### Scenario: Workplace/daily life focus
- **WHEN** sub_genres include "职场" or "轻松"
- **THEN** the prompt emphasizes character growth, power accumulation, and satisfying confrontations without heavy political machinations

#### Scenario: Transmigration/knowledge-gap angle
- **WHEN** sub_genres include "穿越" or "架空"
- **THEN** the prompt emphasizes modern knowledge application, information asymmetry advantages, and historical knowledge utilization

#### Scenario: Martial arts/military focus
- **WHEN** sub_genres include "武侠" or "军事"
- **THEN** the prompt emphasizes combat systems, faction conflicts, and martial prowess progression

#### Scenario: Multiple sub-genres combined
- **WHEN** sub_genres include multiple types (e.g., "后宫+职场+轻松")
- **THEN** the prompt blends the corresponding emphases proportionally

### Requirement: Sub-genre Adaptive Tone
The historical planning prompt SHALL adjust system prompt tone based on sub-genre combinations.

#### Scenario: Lighthearted tone selection
- **WHEN** sub_genres indicate "轻松" tone
- **THEN** the system prompt describes the writer as "轻松幽默，擅长反套路叙事和爽感节奏"

#### Scenario: Dark political tone selection
- **WHEN** sub_genres indicate "朝堂权谋" tone
- **THEN** the system prompt describes the writer as "精通历史叙事，注重朝代考据和权谋逻辑"
