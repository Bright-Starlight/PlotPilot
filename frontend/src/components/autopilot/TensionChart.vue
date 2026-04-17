<template>
  <n-card title="📈 张力心电图" size="small" :bordered="true">
    <template #header-extra>
      <n-tag v-if="hasLowTension" type="warning" size="small">
        ⚠️ 检测到低张力章节
      </n-tag>
      <n-button v-if="tensionData.length > 0" size="tiny" quaternary @click="refreshChart">↻</n-button>
    </template>

    <!-- 空状态 -->
    <div v-if="!loading && !tensionData.length" class="chart-container chart-empty">
      <n-empty description="暂无张力数据" size="small">
        <template #icon><span style="font-size:36px">📈</span></template>
        <template #extra>
          <n-text depth="3" style="font-size:11px">写作章节后自动生成张力评分</n-text>
        </template>
      </n-empty>
    </div>

    <!-- 图表 -->
    <div v-else class="chart-shell">
      <div ref="chartRef" class="chart-container" />
      <div v-if="loading" class="chart-overlay chart-loading">
        <n-spin size="small" />
        <span class="chart-loading-text">加载张力曲线…</span>
      </div>
    </div>

    <!-- 低张力警告 -->
    <n-alert v-if="hasLowTension && !loading" type="warning" :show-icon="false" style="margin-top: 8px; font-size: 12px">
      第 {{ lowTensionChapters.join('、') }} 章张力偏低 · 建议插入缓冲章或调整剧情节奏
    </n-alert>

    <!-- 底部统计 -->
    <div v-if="tensionData.length > 0" class="chart-stats">
      <n-space :size="12" align="center">
        <n-text depth="3" style="font-size:10px">
          {{ tensionData.length }} 章 · 均值 {{ avgTension.toFixed(1) }} · 峰值 {{ maxTension.toFixed(1) }}
        </n-text>
        <n-divider vertical style="margin:0" />
        <n-text
          :style="{ fontSize: '10px', color: getTensionColor(avgTension) }"
        >
          {{ getTensionLabel(avgTension) }}
        </n-text>
      </n-space>
    </div>
  </n-card>
</template>

<script setup lang="ts">
import { ref, computed, watchEffect, onMounted, onUnmounted, nextTick } from 'vue'
import { init, use, type ECharts, type EChartsCoreOption } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, MarkLineComponent, MarkPointComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { monitorApi } from '../../api/monitor'

use([LineChart, GridComponent, TooltipComponent, MarkLineComponent, MarkPointComponent, CanvasRenderer])

interface TensionData {
  chapter_number: number
  tension_score: number
  title?: string
}

const props = defineProps<{
  novelId: string
  threshold?: number
}>()

const emit = defineEmits<{
  'chapter-click': [chapterNumber: number]
  'low-tension-alert': [chapters: number[]]
}>()

const chartRef = ref<HTMLElement | null>(null)
const tensionData = ref<TensionData[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

let chartInstance: ECharts | null = null
let resizeObserver: ResizeObserver | null = null

// 张力警戒线
const tensionThreshold = computed(() => props.threshold ?? 5.0)

// 是否有低张力章节
const hasLowTension = computed(() =>
  tensionData.value.some(d => d.tension_score < tensionThreshold.value)
)

// 低张力章节列表
const lowTensionChapters = computed(() =>
  tensionData.value
    .filter(d => d.tension_score < tensionThreshold.value)
    .map(d => d.chapter_number)
)

// 统计
const avgTension = computed(() => {
  if (!tensionData.value.length) return 0
  const sum = tensionData.value.reduce((s, d) => s + d.tension_score, 0)
  return sum / tensionData.value.length
})

const maxTension = computed(() => {
  if (!tensionData.value.length) return 0
  return Math.max(...tensionData.value.map(d => d.tension_score))
})

// ==================== 加载 ====================
async function loadTensionData() {
  loading.value = true
  error.value = null
  try {
    // 使用 apiClient（走 Vite proxy）而非裸 fetch
    const data = await monitorApi.getTensionCurve(props.novelId)
    tensionData.value = (data.points || []).map((p) => ({
      chapter_number: p.chapter,
      tension_score: p.tension,
      title: p.title,
    }))

    if (lowTensionChapters.value.length > 0) {
      emit('low-tension-alert', lowTensionChapters.value)
    }

    // 等 DOM 更新后再渲染图表（解决第五章后不显示的关键）
    await nextTick()
  } catch (err: any) {
    console.error('[TensionChart] Failed to load:', err)
    error.value = err?.message || String(err)
    tensionData.value = []
  } finally {
    loading.value = false
    void tryRenderChart()
  }
}

async function tryRenderChart() {
  await nextTick()
  if (loading.value || tensionData.value.length === 0 || !chartRef.value) {
    return
  }
  requestAnimationFrame(() => {
    if (!loading.value && tensionData.value.length > 0 && chartRef.value) {
      renderChart()
    }
  })
}

// ==================== 渲染 ====================
function renderChart() {
  if (!chartRef.value || tensionData.value.length === 0) return

  // 确保 DOM 可见且有尺寸
  const rect = chartRef.value.getBoundingClientRect()
  if (rect.width < 10 || rect.height < 10) {
    // 容器不可见，延迟重试
    setTimeout(() => renderChart(), 200)
    return
  }

  if (chartInstance) {
    const disposed = typeof chartInstance.isDisposed === 'function' && chartInstance.isDisposed()
    const domMismatch = chartInstance.getDom() !== chartRef.value
    if (disposed || domMismatch) {
      chartInstance.dispose()
      chartInstance = null
    }
  }

  if (!chartInstance) {
    chartInstance = init(chartRef.value)
    // 在 chartRef 确保存在后才初始化 ResizeObserver（解决 onMounted 时 chartRef 为 null 的问题）
    if (!resizeObserver && chartRef.value) {
      resizeObserver = new ResizeObserver(() => {
        chartInstance?.resize()
      })
      resizeObserver.observe(chartRef.value)
    }
  }

  const chapterNumbers = tensionData.value.map((d) => d.chapter_number)
  const tensionScores = tensionData.value.map((d) => d.tension_score)

  const option: EChartsCoreOption = {
    grid: {
      left: 36,
      right: 16,
      top: 24,
      bottom: 28,
      containLabel: false,
    },
    xAxis: {
      type: 'category',
      data: chapterNumbers,
      name: '章节',
      nameLocation: 'middle',
      nameGap: 22,
      nameTextStyle: { color: '#888', fontSize: 10 },
      axisLine: { lineStyle: { color: '#444' } },
      axisTick: { show: true, lineStyle: { color: '#555' } },
      axisLabel: {
        color: '#999',
        fontSize: 10,
        interval: chapterNumbers.length > 15 ? 'auto' : 0,
        rotate: chapterNumbers.length > 20 ? 45 : 0,
      },
      boundaryGap: false,
    },
    yAxis: {
      type: 'value',
      name: '张力',
      min: 0,
      max: 10,
      interval: 2,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#888', fontSize: 10 },
      splitLine: { lineStyle: { color: '#333', type: 'dashed' } },
    },
    series: [
      {
        type: 'line',
        data: tensionScores,
        smooth: 0.4,
        symbol: 'circle',
        symbolSize: (value: number[], params: any) => {
          // 当前点高亮
          return params.dataIndex === tensionScores.length - 1 ? 8 : 5
        },
        lineStyle: { width: 2.5, color: '#18a058' },
        itemStyle: {
          color: '#18a058',
          borderWidth: 2,
          borderColor: '#fff',
        },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(24, 160, 88, 0.25)' },
              { offset: 1, color: 'rgba(24, 160, 88, 0.02)' },
            ],
          },
        },
        markLine: {
          silent: true,
          symbol: 'none',
          label: {
            formatter: '警戒线',
            position: 'end',
            color: '#f0a020',
            fontSize: 10,
          },
          lineStyle: { color: '#f0a020', type: 'dashed', width: 1.5 },
          data: [{ yAxis: tensionThreshold.value }],
        },
        markPoint: {
          symbol: 'pin',
          symbolSize: 36,
          label: { fontSize: 9, color: '#fff' },
          data: [
            { type: 'max', name: '最高', itemStyle: { color: '#d03050' } },
            { type: 'min', name: '最低', itemStyle: { color: '#666' } },
          ],
        },
      },
    ],
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(0, 0, 0, 0.85)',
      borderColor: '#444',
      textStyle: { color: '#fff', fontSize: 12 },
      confine: true, // 防止 tooltip 超出画布
      formatter: (params: any) => {
        const pt = params[0]
        const chNum = pt.name
        const tension = pt.value as number
        const ch = tensionData.value.find((d) => d.chapter_number === Number(chNum))

        let html = `<div style="padding:4px 8px"><b>第 ${chNum} 章</b>`
        if (ch?.title) html += `<br/><span style="color:#aaa;font-size:11px">${ch.title}</span>`
        html += `<br/><span style="color:${getTensionColor(tension)}">▲ ${tension.toFixed(1)}</span>`
        html += ` <span style="color:#666">${getTensionLabel(tension)}</span>`
        if (tension < tensionThreshold.value) html += `<br/><span style="color:#f0a020">⚠️ 低于警戒</span>`
        html += `</div>`
        return html
      },
    },
    animationDuration: 600,
    animationEasing: 'cubicOut',
  }

  chartInstance.setOption(option, true)

  // 点击事件
  chartInstance.off('click')
  chartInstance.on('click', (params: any) => {
    if (params.componentType === 'series') {
      emit('chapter-click', Number(params.name))
    }
  })
}

function getTensionColor(t: number): string {
  if (t >= 8) return '#d03050'
  if (t >= 5) return '#f0a020'
  return '#18a058'
}

function getTensionLabel(t: number): string {
  if (t >= 8) return '🔥 高潮'
  if (t >= 5) return '⚡ 冲突'
  return '🌊 平缓'
}

function handleResize() {
  chartInstance?.resize()
}

// 刷新图表：重新加载数据并渲染
async function refreshChart() {
  // 先清空数据触发重新加载
  tensionData.value = []
  // 销毁旧实例确保重新初始化
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
  await nextTick()
  await loadTensionData()
}

// ==================== 监听 ====================
watchEffect(() => {
  const novelId = props.novelId
  if (!novelId) return
  void loadTensionData()
})

// ==================== 生命周期 ====================
onMounted(() => {
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  chartInstance?.dispose()
  chartInstance = null
})
</script>

<style scoped>
.chart-shell {
  position: relative;
}

.chart-container {
  width: 100%;
  height: 200px;
  min-height: 200px;
  position: relative;
}

.chart-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: rgba(0, 0, 0, 0.02);
  border-radius: 6px;
}

.chart-overlay {
  position: absolute;
  inset: 0;
  z-index: 2;
  backdrop-filter: blur(1px);
}

.chart-loading-text {
  font-size: 11px;
  color: var(--text-color-3);
}

.chart-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px 0;
}

.chart-stats {
  margin-top: 6px;
  padding-top: 8px;
  border-top: 1px solid var(--n-border-color, rgba(0,0,0,0.08));
}

/* 确保卡片高度填满容器 */
:deep(.n-card) {
  height: 100%;
  display: flex;
  flex-direction: column;
}

:deep(.n-card__content) {
  flex: 1;
  min-height: 0;
}
</style>
