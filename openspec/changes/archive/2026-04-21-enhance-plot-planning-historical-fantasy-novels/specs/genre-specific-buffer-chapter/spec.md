## ADDED Requirements

### Requirement: Generate genre-specific buffer chapter outlines
The system SHALL use ThemeAgent.get_buffer_chapter_template(outline) when the chapter type is designated as a buffer chapter.

#### Scenario: Buffer chapter for xuanhuan novel
- **WHEN** a buffer chapter is generated for a novel with genre="xuanhuan"
- **THEN** the system SHALL call XuanhuanThemeAgent.get_buffer_chapter_template(outline)
- **AND** the resulting outline SHALL include xuanhuan buffer elements (闭关悟道, 炼丹采药, 宗门日常)

#### Scenario: Buffer chapter for history novel
- **WHEN** a buffer chapter is generated for a novel with genre="history"
- **THEN** the system SHALL call HistoryThemeAgent.get_buffer_chapter_template(outline)
- **AND** the resulting outline SHALL include history buffer elements (庙堂之余, 军旅生活, 民间百态)

### Requirement: Fallback to generic buffer chapter template
The system SHALL use a generic buffer chapter template when no ThemeAgent is available for the genre.

#### Scenario: Buffer chapter for unregistered genre
- **WHEN** a buffer chapter is generated with genre="" or unregistered genre
- **THEN** the system SHALL use the default generic buffer chapter template
- **AND** the outline SHALL follow a general "休息调整 + 铺垫下一冲突" structure

### Requirement: Buffer chapter preserves story momentum
The system SHALL ensure genre-specific buffer chapter outlines include foreshadowing elements for upcoming conflicts.

#### Scenario: Xuanhuan buffer includes cultivation foreshadowing
- **WHEN** a xuanhuan buffer chapter outline is generated
- **THEN** the outline SHALL include hints about upcoming trials, rival sightings, or inheritance opportunities

#### Scenario: History buffer includes political foreshadowing
- **WHEN** a history buffer chapter outline is generated
- **THEN** the outline SHALL include hints about upcoming power shifts, enemy movements, or court intrigue
