## ADDED Requirements

### Requirement: Novel Type and Sub-genre Selector
The Home.vue novel creation modal SHALL include a type selector and sub-genre multi-select.

#### Scenario: User creates historical novel with sub-genres
- **WHEN** user selects type "历史"
- **THEN** system displays sub-genre checkboxes: 朝堂权谋, 后宫, 职场, 轻松, 穿越, 武侠
- **AND** user can select multiple sub-genres

#### Scenario: User creates xuanhuan novel with sub-genres
- **WHEN** user selects type "玄幻"
- **THEN** system displays sub-genre checkboxes: 修炼升级流, 凡人流, 系统流, 无敌流, 无限流

#### Scenario: User creates hybrid novel
- **WHEN** user selects type "混合"
- **THEN** system displays both historical and xuanhuan sub-genres

#### Scenario: Novel creation includes sub_genres in API payload
- **WHEN** user submits novel creation form
- **THEN** API payload includes sub_genres array

### Requirement: MacroPlanModal Display
The MacroPlanModal.vue SHALL display the current novel's type and sub-genres.

#### Scenario: Display type information
- **WHEN** MacroPlanModal renders for a novel with genre and sub_genres
- **THEN** it shows a readonly label with type and sub-genres
