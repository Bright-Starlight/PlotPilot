## 1. Core Distribution Logic

- [x] 1.1 Add `_get_distribution_for_genre(genre)` method to route to xuanhuan/historical/default
- [x] 1.2 Add `_xuanhuan_distribution(total_chapters, parts)` — 倒V形比例 (10/20/25/20/15...)
- [x] 1.3 Add `_historical_distribution(total_chapters, parts)` — 幂函数比例 (25/50/25 或 20/30/30/20)
- [x] 1.4 Modify `_calculate_chapter_distribution(genre)` accept optional genre str parameter, delegate to genre-specific method
- [x] 1.5 Keep backward compatibility: if genre is empty/None, fall back to default黄金分割

## 2. Pacing Guide Enhancement

- [x] 2.1 Add `_get_genre_part_label(genre, part_index, total_parts)` — returns genre-specific part label (e.g. "起源卷" for xuanhuan, "崛起篇" for historical)
- [x] 2.2 Modify `_build_precise_macro_prompt` to use genre-specific part labels in pacing_guide
- [x] 2.3 Enhance pacing_guide with genre-specific narrative focus description per part (not just "起源/深渊/决战")

## 3. End-to-End Wiring

- [x] 3.1 Ensure `generate_macro_plan` passes `novel.genre` to `_calculate_chapter_distribution` and `_build_precise_macro_prompt`
- [x] 3.2 For quick mode (`structure_preference=None`), also pass genre to `_build_quick_macro_prompt` so it can use correct pacing_guide

## 4. Testing

- [x] 4.1 Verify 玄幻 1000章/5部 → 100/200/250/200/150 章
- [x] 4.2 Verify 历史 1000章/3部 → 250/500/250 章
- [x] 4.3 Verify unknown genre falls back to default黄金分割
- [ ] 4.4 Visual verify pacing_guide output for each genre type (需要实际运行并查看输出)
