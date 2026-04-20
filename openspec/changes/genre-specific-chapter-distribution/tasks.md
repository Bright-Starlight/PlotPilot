## 1. Core Distribution Logic

- [ ] 1.1 Add `_get_distribution_for_genre(genre)` method to route to xuanhuan/historical/dushi/default
- [ ] 1.2 Add `_xuanhuan_distribution(total_chapters, parts)` — 倒V形比例 (10/20/25/20/15...)
- [ ] 1.3 Add `_historical_distribution(total_chapters, parts)` — 幂函数比例 (25/50/25 或 20/30/30/20)
- [ ] 1.4 Add `_dushi_distribution(total_chapters, parts)` — 波浪形比例 (15/20/25/20/20)
- [ ] 1.5 Modify `_calculate_chapter_distribution(genre)` accept optional genre str parameter, delegate to genre-specific method
- [ ] 1.6 Keep backward compatibility: if genre is empty/None, fall back to default黄金分割

## 2. Pacing Guide Enhancement

- [ ] 2.1 Add `_get_genre_part_label(genre, part_index, total_parts)` — returns genre-specific part label (e.g. "起源卷" for xuanhuan, "崛起篇" for historical)
- [ ] 2.2 Modify `_build_precise_macro_prompt` to use genre-specific part labels in pacing_guide
- [ ] 2.3 Enhance pacing_guide with genre-specific narrative focus description per part (not just "起源/深渊/决战")

## 3. End-to-End Wiring

- [ ] 3.1 Ensure `generate_macro_plan` passes `novel.genre` to `_calculate_chapter_distribution` and `_build_precise_macro_prompt`
- [ ] 3.2 For quick mode (`structure_preference=None`), also pass genre to `_build_quick_macro_prompt` so it can use correct pacing_guide

## 4. Testing

- [ ] 4.1 Verify 玄幻 1000章/5部 → 100/200/250/200/150 章
- [ ] 4.2 Verify 历史 1000章/3部 → 250/500/250 章
- [ ] 4.3 Verify 都市 1000章/4部 → 150/250/300/300 章
- [ ] 4.4 Verify unknown genre falls back to default黄金分割
- [ ] 4.5 Visual verify pacing_guide output for each genre type
