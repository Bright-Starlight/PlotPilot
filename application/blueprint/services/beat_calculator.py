"""节拍数量计算器

根据章节字数动态计算合理的节拍数量和字数分配。
"""
from typing import List


class BeatCalculator:
    """节拍数量计算器"""

    # 节拍字数范围配置
    MIN_WORDS_PER_BEAT = 600   # 每个节拍最少600字
    MAX_WORDS_PER_BEAT = 1200  # 每个节拍最多1200字
    IDEAL_WORDS_PER_BEAT = 800 # 理想每个节拍800字

    @staticmethod
    def calculate_beat_count(target_words_per_chapter: int) -> int:
        """根据章节字数计算合理的节拍数量

        Args:
            target_words_per_chapter: 目标章节字数

        Returns:
            建议的节拍数量（3-7个）

        Examples:
            1000字 -> 3个节拍
            2000字 -> 3个节拍
            3500字 -> 4个节拍
            5000字 -> 6个节拍
            8000字 -> 7个节拍（上限）
        """
        if target_words_per_chapter <= 0:
            return 3  # 默认最少3个节拍

        # 基于理想字数计算
        ideal_count = target_words_per_chapter / BeatCalculator.IDEAL_WORDS_PER_BEAT

        # 四舍五入并限制范围
        beat_count = round(ideal_count)
        beat_count = max(3, min(7, beat_count))  # 限制在 3-7 个节拍

        return beat_count

    @staticmethod
    def calculate_words_per_beat(
        target_words_per_chapter: int,
        beat_count: int
    ) -> List[int]:
        """计算每个节拍的目标字数

        Args:
            target_words_per_chapter: 目标章节字数
            beat_count: 节拍数量

        Returns:
            每个节拍的目标字数列表

        Example:
            calculate_words_per_beat(3500, 4) -> [875, 875, 875, 875]
            calculate_words_per_beat(3502, 4) -> [876, 876, 875, 875]
        """
        if beat_count <= 0:
            return []

        # 平均分配
        avg_words = target_words_per_chapter // beat_count
        remainder = target_words_per_chapter % beat_count

        # 前面的节拍多分配余数
        words_per_beat = [avg_words] * beat_count
        for i in range(remainder):
            words_per_beat[i] += 1

        return words_per_beat

    @staticmethod
    def validate_beat_count(
        target_words_per_chapter: int,
        beat_count: int
    ) -> tuple[bool, str]:
        """验证节拍数量是否合理

        Args:
            target_words_per_chapter: 目标章节字数
            beat_count: 节拍数量

        Returns:
            (是否合理, 原因说明)
        """
        if beat_count < 3:
            return False, "节拍数量不能少于3个"

        if beat_count > 7:
            return False, "节拍数量不能超过7个"

        avg_words = target_words_per_chapter / beat_count

        if avg_words < BeatCalculator.MIN_WORDS_PER_BEAT:
            return False, f"平均每个节拍仅{avg_words:.0f}字，低于最小值{BeatCalculator.MIN_WORDS_PER_BEAT}字"

        if avg_words > BeatCalculator.MAX_WORDS_PER_BEAT:
            return False, f"平均每个节拍{avg_words:.0f}字，超过最大值{BeatCalculator.MAX_WORDS_PER_BEAT}字"

        return True, "节拍数量合理"
