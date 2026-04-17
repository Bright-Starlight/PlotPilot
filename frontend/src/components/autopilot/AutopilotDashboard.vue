<template>
  <div class="autopilot-dashboard">
    <!-- 监控网格 -->
    <div class="monitor-grid">
      <!-- 第一行：张力图表 + 实时日志 -->
      <div class="grid-cell span-2">
        <TensionChart :novel-id="novelId" />
      </div>
      <div class="grid-cell span-1">
        <RealtimeLogStream :novel-id="novelId" />
      </div>

      <!-- 第二行：文风警报 + 伏笔账本 + 熔断器 -->
      <div class="grid-cell">
        <VoiceDriftIndicator
          :novel-id="novelId"
          @drift-alert="handleDriftAlert"
        />
      </div>
      <div class="grid-cell">
        <ForeshadowLedger :novel-id="novelId" />
      </div>
      <div class="grid-cell">
        <CircuitBreakerStatus
          :novel-id="novelId"
          @breaker-open="handleBreakerOpen"
          @breaker-reset="handleBreakerReset"
        />
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useMessage } from 'naive-ui'
import TensionChart from './TensionChart.vue'
import RealtimeLogStream from './RealtimeLogStream.vue'
import VoiceDriftIndicator from './VoiceDriftIndicator.vue'
import ForeshadowLedger from './ForeshadowLedger.vue'
import CircuitBreakerStatus from './CircuitBreakerStatus.vue'

const props = defineProps<{
  novelId: string
}>()

const message = useMessage()

// 文风偏移警报
function handleDriftAlert(score: number, status: string) {
  if (status === 'danger') {
    message.error(`⚠️ 文风严重偏离 (${score.toFixed(1)})，建议立即处理`)
  } else if (status === 'warning') {
    message.warning(`⚡ 文风轻微偏离 (${score.toFixed(1)})，请注意观察`)
  }
}

// 熔断器打开
function handleBreakerOpen() {
  message.error('🔌 熔断器已触发，连续错误过多，Autopilot 已自动停止')
}

// 熔断器重置
function handleBreakerReset() {
  message.success('🔄 熔断器已重置，可以重新启动 Autopilot')
}
</script>

<style scoped>
.autopilot-dashboard {
  /* 高度由内容自然撑开，配合 WorkArea 整体滚动 */
}

.monitor-copy-hint {
  margin: 0 4px 12px;
  padding: 8px 12px;
}

.monitor-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  grid-auto-rows: minmax(200px, auto); /* 第一行最小200px，自动拉伸 */
  align-items: stretch; /* 单元格垂直拉伸对齐 */
  gap: 16px;
  padding: 8px;
}

.grid-cell {
  min-height: auto;
  display: flex;
  flex-direction: column;
}

.grid-cell > * {
  flex: 1 1 auto; /* 允许子元素拉伸填充 */
  min-height: 0;
}

/* 第一行单元格高度一致 */
.grid-cell.span-1,
.grid-cell.span-2 {
  height: 100%;
}

.grid-cell.span-1 {
  grid-column: span 1;
}

.grid-cell.span-2 {
  grid-column: span 2;
}

/* 响应式布局 */
@media (max-width: 1400px) {
  .monitor-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .grid-cell.span-2 {
    grid-column: span 2;
  }
}

@media (max-width: 900px) {
  .monitor-grid {
    grid-template-columns: 1fr;
  }

  .grid-cell.span-1,
  .grid-cell.span-2 {
    grid-column: span 1;
  }
}
</style>
