## 1. Backend: Prompt Templates

- [x] 1.1 Add historical-planning-template to prompts_defaults.json (id: `planning-historical`)
- [x] 1.2 Add xuanhuan-planning-template to prompts_defaults.json (id: `planning-xuanhuan`)
- [x] 1.3 Add hybrid-planning-template to prompts_defaults.json (id: `planning-hybrid`)

## 2. Backend: Service Layer

- [x] 2.1 Modify `continuous_planning_service.py::_build_act_planning_prompt()` accept genre + sub_genres
- [x] 2.2 Add `_select_planning_template(genre, sub_genres)` helper
- [x] 2.3 Modify `story_structure_service.py` pass novel.genre + sub_genres (continuous_planning_service fetches directly from repository)
- [x] 2.4 Check novel entity has sub_genres field, add if missing

## 3. Frontend: Type Selector

- [x] 3.1 Add type selector component (历史/玄幻/混合) in Home.vue novel creation modal
- [x] 3.2 Add sub-genres multi-select based on selected type in Home.vue
- [x] 3.3 Update novel creation API payload to include sub_genres
- [x] 3.4 MacroPlanModal.vue display current novel type/sub-genres (readonly)

## 4. Testing

- [ ] 4.1 Test historical planning with 权谋 subtype
- [ ] 4.2 Test historical planning with 后宫+职场+轻松 subtypes
- [ ] 4.3 Test xuanhuan planning with 系统流+凡人流 subtypes
- [ ] 4.4 Test hybrid planning output
- [ ] 4.5 Verify unknown genre falls back to generic prompt
- [ ] 4.6 Test frontend type selector UI
