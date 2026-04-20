## ADDED Requirements

### Requirement: Load theme agent by novel genre
The system SHALL load the corresponding ThemeAgent from ThemeAgentRegistry when generating beat sheets, using Novel.genre as the genre_key.

#### Scenario: Genre with registered theme agent
- **WHEN** BeatSheetService.generate_beat_sheet() is called with a novel that has genre="xuanhuan" or genre="history"
- **THEN** the system SHALL use ThemeAgentRegistry.get(genre) to retrieve the matching ThemeAgent
- **AND** the system SHALL use the agent's beat templates for beat sheet generation

#### Scenario: Genre with no registered theme agent
- **WHEN** BeatSheetService.generate_beat_sheet() is called with a novel that has genre="" or an unregistered genre
- **THEN** the system SHALL fall back to generic beat calculation logic
- **AND** the system SHALL NOT raise an error

### Requirement: Apply genre-specific beat templates based on outline keywords
The system SHALL match outline keywords against ThemeAgent's BeatTemplate keywords and use matching templates to generate beats.

#### Scenario: Outline contains xuanhuan keywords
- **WHEN** the outline for a xuanhuan novel contains keywords like "修炼", "突破", "大比"
- **THEN** the system SHALL use XuanhuanThemeAgent's matching BeatTemplate (priority 80 for 修炼/突破, priority 75 for 大比)
- **AND** the generated beats SHALL follow the template's beat structure and word count distribution

#### Scenario: Outline contains history keywords
- **WHEN** the outline for a history novel contains keywords like "朝堂", "战争", "权谋"
- **THEN** the system SHALL use HistoryThemeAgent's matching BeatTemplate (priority 85 for 朝堂, priority 90 for 战争)
- **AND** the generated beats SHALL follow the template's beat structure and word count distribution

#### Scenario: No keyword match with genre templates
- **WHEN** the outline keywords do not match any ThemeAgent BeatTemplate keywords
- **THEN** the system SHALL use the generic beat calculation logic
- **AND** genre-specific templates SHALL be skipped

### Requirement: Merge genre-specific templates with generic beat count
The system SHALL determine target_beat_count using BeatCalculator.calculate_beat_count(), then assign genre-specific beats respecting the total count.

#### Scenario: Beat count allocation with templates
- **WHEN** target_beat_count is 5 and outline matches a BeatTemplate with 4 beats
- **THEN** the system SHALL generate at least the template's beats
- **AND** additional beats SHALL be allocated based on remaining word count and generic beat structure

### Requirement: Genre-specific beat types in output
The system SHALL include the ThemeAgent's custom beat type labels (e.g., "cultivation", "power_reveal", "court_debate") in the generated Scene entities.

#### Scenario: Beat types included in scenes
- **WHEN** beats are generated using a genre-specific BeatTemplate
- **THEN** each Scene SHALL have a beat_type field populated from the template's beat type label
- **AND** scenes without a matching template SHALL have beat_type="general"
