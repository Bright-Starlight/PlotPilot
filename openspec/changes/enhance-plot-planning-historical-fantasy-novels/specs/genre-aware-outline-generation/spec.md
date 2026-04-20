## ADDED Requirements

### Requirement: Inject theme agent context into outline generation
The system SHALL inject ThemeAgent.get_context_directives() content into the LLM prompt when ContinuousPlanningService generates chapter outlines.

#### Scenario: Xuanhuan novel outline generation includes world rules
- **WHEN** ContinuousPlanningService generates an outline for a novel with genre="xuanhuan"
- **THEN** the LLM prompt SHALL include XuanhuanThemeAgent's world_rules (修炼体系, 灵气, 功法, 宗门等级)
- **AND** the LLM prompt SHALL include atmosphere directives (快意恩仇 + 热血成长)

#### Scenario: History novel outline generation includes court directives
- **WHEN** ContinuousPlanningService generates an outline for a novel with genre="history"
- **THEN** the LLM prompt SHALL include HistoryThemeAgent's world_rules (皇权, 门阀, 军事, 礼法)
- **AND** the LLM prompt SHALL include atmosphere directives (厚重沧桑 + 热血豪情)

### Requirement: Apply taboos from theme agent
The system SHALL append ThemeAgent's taboos to the LLM prompt to prevent prohibited content.

#### Scenario: Xuanhuan taboos applied
- **WHEN** generating outline for genre="xuanhuan"
- **THEN** the prompt SHALL include xuanhuan taboos (no modern tech, no inexplicable power gains)
- **AND** the LLM SHALL avoid generating content violating these taboos

#### Scenario: History taboos applied
- **WHEN** generating outline for genre="history"
- **THEN** the prompt SHALL include history taboos (no modern speech, no ignoring transportation limits)
- **AND** the LLM SHALL avoid generating anachronistic content

### Requirement: Include tropes guidance from theme agent
The system SHALL add ThemeAgent's tropes_to_use and tropes_to_avoid to the prompt for guided outline generation.

#### Scenario: Xuanhuan tropes guidance
- **WHEN** generating outline for genre="xuanhuan"
- **THEN** the prompt SHALL include tropes_to_use (扮猪吃老虎, 步步高升, 伏笔回收)
- **AND** the prompt SHALL include tropes_to_avoid (无脑碾压, 金手指滥用, 境界注水)

#### Scenario: History tropes guidance
- **WHEN** generating outline for genre="history"
- **THEN** the prompt SHALL include tropes_to_use (权谋博弈, 草蛇灰线, 英雄末路)
- **AND** the prompt SHALL include tropes_to_avoid (现代思维套古人, 一人之力改天下)

### Requirement: Fallback for unregistered genres
The system SHALL NOT inject theme context when genre is empty or unregistered.

#### Scenario: Empty genre uses generic prompt
- **WHEN** novel.genre is "" or None
- **THEN** the system SHALL use the generic outline generation prompt
- **AND** no theme-specific context SHALL be injected
