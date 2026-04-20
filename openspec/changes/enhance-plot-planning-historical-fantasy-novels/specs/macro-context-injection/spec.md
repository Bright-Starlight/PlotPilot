## ADDED Requirements

### Requirement: Retrieve act/volume/part ancestors for chapter beat sheet
The system SHALL retrieve the chapter's ancestors in the story node hierarchy (Act → Volume → Part) when generating beat sheets, so the LLM prompt includes macro-level plot designs.

#### Scenario: Chapter has full hierarchy
- **WHEN** BeatSheetService generates a beat sheet for a chapter that belongs to an Act which belongs to a Volume which belongs to a Part
- **THEN** the system SHALL retrieve all three ancestor nodes' description fields
- **AND** the system SHALL inject these descriptions into the beat sheet generation prompt

#### Scenario: Chapter hierarchy is incomplete
- **WHEN** the chapter's ancestor chain is missing (e.g., Act exists but Volume or Part does not)
- **THEN** the system SHALL retrieve only the available ancestors
- **AND** the system SHALL NOT raise an error

#### Scenario: No story nodes exist for chapter
- **WHEN** the chapter has no corresponding entry in story_nodes
- **THEN** the system SHALL skip macro context retrieval
- **AND** the system SHALL fall back to the existing context (characters, storylines, previous chapter)

### Requirement: Inject macro context into beat sheet generation prompt
The system SHALL include the Act/Volume/Part narrative designs in the LLM prompt used for beat sheet generation.

#### Scenario: Prompt includes act description
- **WHEN** generating a beat sheet
- **THEN** the prompt SHALL include the current Act's description (e.g., "本幕核心冲突：主角在宗门大比中击败天才，奠定地位")
- **AND** the Act description SHALL appear before the chapter outline in the prompt

#### Scenario: Prompt includes volume description
- **WHEN** generating a beat sheet
- **THEN** the prompt SHALL include the Volume's description (e.g., "本卷主线：主角从外门弟子成长为内门核心")
- **AND** the Volume description SHALL appear before the act description in the prompt

#### Scenario: Prompt includes part description
- **WHEN** generating a beat sheet
- **THEN** the prompt SHALL include the Part's description (e.g., "第一部：废柴觉醒，踏上修炼之路")
- **AND** the Part description SHALL appear before the volume description in the prompt

### Requirement: Macro context combined with genre-specific templates
The system SHALL merge macro context injection with genre-specific beat templates, ensuring both macro narrative and genre conventions inform beat sheet generation.

#### Scenario: Xuanhuan chapter with act/volume/part context
- **WHEN** generating a beat sheet for genre="xuanhuan" with macro context available
- **THEN** the prompt SHALL include both the Part/Volume/Act descriptions AND the xuanhuan-specific writing rules and beat templates

#### Scenario: History chapter with act/volume/part context
- **WHEN** generating a beat sheet for genre="history" with macro context available
- **THEN** the prompt SHALL include both the Part/Volume/Act descriptions AND the history-specific writing rules and beat templates
