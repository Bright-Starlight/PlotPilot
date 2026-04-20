## 1. Setup - ThemeAgentRegistry Accessibility

- [x] 1.1 Verify ThemeAgentRegistry.auto_discover() is called at application startup
- [x] 1.2 Confirm ThemeAgentRegistry is accessible from BeatSheetService (via DI or import)

## 2. BeatSheetService - Macro Context (Act/Volume/Part)

- [x] 2.1 Inject StoryNodeRepository into BeatSheetService constructor (if not already)
- [x] 2.2 Add _get_macro_context(chapter_node) method to traverse chapter → act → volume → part
- [x] 2.3 Modify _retrieve_relevant_context() to call _get_macro_context() and include ancestors in returned context
- [x] 2.4 Modify _build_beat_sheet_prompt() to accept and include Part/Volume/Act descriptions in prompt
- [x] 2.5 Add unit test for macro context retrieval with complete hierarchy
- [x] 2.6 Add unit test for macro context retrieval with partial hierarchy

## 3. BeatSheetService - Genre-Aware Beat Templates

- [x] 3.1 Inject ThemeAgentRegistry into BeatSheetService constructor
- [x] 3.2 Add _get_theme_agent(novel) method that returns ThemeAgent or None
- [x] 3.3 Add _match_beat_template(theme_agent, outline) method to find matching BeatTemplate by keywords
- [x] 3.4 (Optional) _build_genre_beats - not needed since LLM generates beats with type labels
- [x] 3.5 Modify generate_beat_sheet() to call theme agent when available and template matches
- [x] 3.6 Add Scene.beat_type field propagation from template beat type labels

## 4. ContinuousPlanningService - Genre Context Injection

- [x] 4.1 Inject ThemeAgentRegistry into ContinuousPlanningService (if not already)
- [x] 4.2 Add _build_theme_context_prompt(novel_genre, outline) method
- [x] 4.3 Modify _build_outline_prompt() to append ThemeDirectives content (world_rules, atmosphere, taboos, tropes)
- [x] 4.4 Ensure fallback to generic prompt when genre is empty/unregistered

## 5. Buffer Chapter - Genre-Specific Templates

- [x] 5.1 Find where buffer chapter outlines are generated (autopilot_daemon.py already has this)
- [x] 5.2 Add ThemeAgentRegistry.get_or_default(genre) call for buffer chapters
- [x] 5.3 Call theme_agent.get_buffer_chapter_template(outline) when agent exists
- [x] 5.4 Fallback to generic buffer template when no agent

## 6. Testing

- [x] 6.1 Add unit test for BeatSheetService with genre="xuanhuan" - verifies correct beat template is used
- [x] 6.2 Add unit test for BeatSheetService with genre="history" - verifies correct beat template is used
- [x] 6.3 Add unit test for BeatSheetService with empty genre - verifies fallback behavior
- [x] 6.4 Add unit test for ContinuousPlanningService with xuanhuan genre - verifies context injection
- [x] 6.5 Add unit test for buffer chapter with xuanhuan - verifies xuanhuan-specific template (buffer logic exists in autopilot daemon)
- [x] 6.6 Add unit test for buffer chapter with history - verifies history-specific template (buffer logic exists in autopilot daemon)
- [x] 6.7 Add unit test for macro context injection - verifies Act/Volume/Part descriptions in prompt
