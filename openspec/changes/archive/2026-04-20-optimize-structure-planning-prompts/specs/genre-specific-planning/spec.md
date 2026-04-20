## ADDED Requirements

### Requirement: Genre-based Prompt Routing
The system SHALL route planning prompts based on the novel's genre field.

#### Scenario: Historical novel routing
- **WHEN** novel.genre contains "历史"
- **THEN** system uses historical-planning-template for structure planning

#### Scenario: Xuanhuan novel routing
- **WHEN** novel.genre contains "玄幻"
- **THEN** system uses xuanhuan-planning-template for structure planning

#### Scenario: Hybrid genre routing
- **WHEN** novel.genre contains both "历史" and "玄幻"
- **THEN** system uses hybrid-planning-template for structure planning

#### Scenario: Unknown genre fallback
- **WHEN** novel.genre does not match known types
- **THEN** system uses the default generic planning prompt

### Requirement: Genre Parameter Injection
The planning service SHALL accept a genre parameter and inject it into the prompt selection logic.

#### Scenario: Genre passed to planning service
- **WHEN** continuous_planning_service builds act planning prompt
- **THEN** it receives novel.genre and selects appropriate template
