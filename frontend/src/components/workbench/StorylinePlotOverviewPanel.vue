<template>
  <div class="spo-panel">
    <n-alert type="info" :show-icon="true" class="spo-intro" title="故事线 · 情节弧（全书骨架）">
      <ul class="spo-bullets">
        <li><strong>写</strong>：宏观规划（MACRO_PLANNING）或重大转折后人工调整故事线起止章；情节弧关键张力点在此维护。</li>
        <li><strong>读</strong>：幕/章规划（ACT_PLANNING）与生成上下文组装时注入「当前处于哪条线、弧上张力位置」。</li>
      </ul>
    </n-alert>

    <n-radio-group v-model:value="spoView" size="small" class="spo-mode-switch">
      <n-radio-button value="charts">图表概览</n-radio-button>
      <n-radio-button value="storylines">故事线列表与编辑</n-radio-button>
      <n-radio-button value="plotArc">情节弧（剧情点）编辑</n-radio-button>
    </n-radio-group>

    <n-spin :show="loading" class="spo-spin">
      <div class="spo-view-body">
        <n-space v-show="spoView === 'charts'" vertical :size="14" class="spo-view-charts">
        <!-- 迷你甘特：故事线 -->
        <n-card title="故事线覆盖（章节轴示意）" size="small" :bordered="true">
          <template #header-extra>
            <n-text depth="3" class="spo-card-hint">横轴为章号，色条为线体跨度</n-text>
          </template>
          <n-empty
            v-if="storylines.length === 0"
            class="spo-empty-inline"
            size="small"
            description="暂无故事线"
          >
            <template #extra>
              <n-text depth="3" style="font-size: 12px; max-width: 260px; text-align: center">
                切换到「故事线列表与编辑」添加主线/支线后，此处会显示章节轴示意。
              </n-text>
            </template>
          </n-empty>
          <div v-else class="gantt-wrap">
            <div class="gantt-axis">
              <span>1</span>
              <span v-if="maxChapter > 1">{{ midChapterLabel }}</span>
              <span>{{ maxChapter }}</span>
            </div>
            <div
              v-for="sl in storylines"
              :key="sl.id"
              class="gantt-row"
            >
              <div class="gantt-label" :title="sl.name || sl.id">
                <n-tag :type="typeColor(sl.storyline_type)" size="tiny" round>
                  {{ typeLabel(sl.storyline_type) }}
                </n-tag>
                <span class="gantt-name">{{ shortName(sl) }}</span>
              </div>
              <div class="gantt-track">
                <div
                  class="gantt-bar"
                  :style="barStyle(sl.estimated_chapter_start, sl.estimated_chapter_end)"
                />
              </div>
            </div>
          </div>
        </n-card>

        <!-- 张力曲线（图形容器避免卡片 overflow 裁切网格线） -->
        <n-card title="情节弧 · 张力曲线" size="small" :bordered="true" class="spo-card--chart">
          <n-empty
            v-if="plotPoints.length === 0"
            class="spo-empty-inline"
            size="small"
            description="暂无剧情点"
          >
            <template #extra>
              <n-text depth="3" style="font-size: 12px; max-width: 260px; text-align: center">
                切换到「情节弧（剧情点）编辑」添加关键剧情点后，此处会显示张力曲线预览。
              </n-text>
            </template>
          </n-empty>
          <div v-else class="chart-wrap">
            <svg
              viewBox="0 0 800 200"
              class="tension-svg"
              preserveAspectRatio="xMidYMid meet"
              shape-rendering="geometricPrecision"
            >
              <line
                v-for="i in 4"
                :key="'g' + i"
                :x1="0"
                :y1="i * 50"
                :x2="800"
                :y2="i * 50"
                stroke="var(--n-border-color)"
                stroke-width="1"
                stroke-dasharray="4,4"
              />
              <polyline
                :points="tensionPolyline"
                fill="none"
                stroke="#18a058"
                stroke-width="3"
              />
              <g v-for="p in sortedPoints" :key="p.chapter_number">
                <circle
                  :cx="chapterX(p.chapter_number)"
                  :cy="tensionY(p.tension)"
                  r="6"
                  fill="#2080f0"
                  stroke="#fff"
                  stroke-width="2"
                />
                <text
                  :x="chapterX(p.chapter_number)"
                  :y="tensionY(p.tension) - 12"
                  text-anchor="middle"
                  font-size="11"
                  fill="var(--n-text-color-3)"
                >
                  Ch{{ p.chapter_number }}
                </text>
              </g>
            </svg>
          </div>
        </n-card>
        </n-space>

        <div v-show="spoView === 'storylines'" class="spo-view-embed">
          <StorylinePanel :slug="slug" />
        </div>
        <div v-show="spoView === 'plotArc'" class="spo-view-embed">
          <PlotArcPanel :slug="slug" />
        </div>
      </div>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useWorkbenchRefreshStore } from '../../stores/workbenchRefreshStore'
import { workflowApi } from '../../api/workflow'
import type { StorylineDTO, PlotArcDTO, PlotPointDTO } from '../../api/workflow'
import StorylinePanel from './StorylinePanel.vue'
import PlotArcPanel from './PlotArcPanel.vue'

const props = defineProps<{ slug: string }>()

type SpoView = 'charts' | 'storylines' | 'plotArc'
const spoView = ref<SpoView>('charts')

const loading = ref(false)
const storylines = ref<StorylineDTO[]>([])
const plotPoints = ref<PlotPointDTO[]>([])

const maxChapter = computed(() => {
  let m = 1
  for (const sl of storylines.value) {
    m = Math.max(m, sl.estimated_chapter_end || 1, sl.estimated_chapter_start || 1)
  }
  for (const p of plotPoints.value) {
    m = Math.max(m, p.chapter_number || 1)
  }
  return Math.max(m, 12)
})

const midChapterLabel = computed(() => String(Math.round(maxChapter.value / 2)))

const sortedPoints = computed(() =>
  [...plotPoints.value].sort((a, b) => a.chapter_number - b.chapter_number)
)

function chapterX(ch: number): number {
  const max = maxChapter.value
  if (max <= 1) return 400
  return 40 + ((ch - 1) / (max - 1)) * 720
}

function tensionY(t: number): number {
  const clamped = Math.min(4, Math.max(1, t))
  return 200 - (clamped - 1) * 45 - 10
}

const tensionPolyline = computed(() =>
  sortedPoints.value.map(p => `${chapterX(p.chapter_number)},${tensionY(p.tension)}`).join(' ')
)

function barStyle(start: number, end: number) {
  const max = maxChapter.value
  const s = Math.max(1, start)
  const e = Math.max(s, end)
  const leftPct = ((s - 1) / max) * 100
  const widthPct = ((e - s + 1) / max) * 100
  return {
    left: `${leftPct}%`,
    width: `${Math.min(100 - leftPct, widthPct)}%`,
  }
}

function typeLabel(t: string) {
  const map: Record<string, string> = {
    main_plot: '主线',
    romance: '感情',
    mystery: '悬疑',
    subplot: '支线',
  }
  return map[t] || t
}

function typeColor(t: string): 'success' | 'warning' | 'error' | 'info' | 'default' {
  if (t === 'main_plot') return 'success'
  if (t === 'romance') return 'error'
  if (t === 'mystery') return 'warning'
  return 'info'
}

function shortName(sl: StorylineDTO) {
  const n = (sl.name || '').trim()
  if (n) return n.length > 10 ? `${n.slice(0, 10)}…` : n
  return sl.id.slice(0, 8)
}

async function load() {
  loading.value = true
  try {
    const [sl, arc] = await Promise.all([
      workflowApi.getStorylines(props.slug),
      workflowApi.getPlotArc(props.slug).catch(() => null as PlotArcDTO | null),
    ])
    storylines.value = sl || []
    plotPoints.value = arc?.key_points ?? []
  } catch {
    storylines.value = []
    plotPoints.value = []
  } finally {
    loading.value = false
  }
}

watch(() => props.slug, () => void load(), { immediate: true })

const refreshStore = useWorkbenchRefreshStore()
const { deskTick } = storeToRefs(refreshStore)
watch(deskTick, () => void load())
</script>

<style scoped>
.spo-panel {
  height: 100%;
  min-height: 0;
  overflow-y: auto;
  padding: 16px;
  background: linear-gradient(to bottom, var(--n-color-modal) 0%, rgba(99, 102, 241, 0.02) 100%);
}

.spo-intro {
  margin-bottom: 12px;
  border-radius: 10px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.spo-mode-switch {
  width: 100%;
  margin-bottom: 14px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.spo-mode-switch :deep(.n-radio-group) {
  display: flex;
  flex-wrap: wrap;
  width: 100%;
  gap: 4px;
}

.spo-mode-switch :deep(.n-radio-button) {
  flex: 1 1 auto;
  min-width: 0;
}

.spo-mode-switch :deep(.n-radio-button__state-border) {
  white-space: normal;
  text-align: center;
  line-height: 1.25;
  padding: 6px 8px;
}

.spo-view-body {
  width: 100%;
  min-height: 0;
}

.spo-view-charts {
  width: 100%;
}

.spo-view-embed {
  width: 100%;
  min-height: 360px;
  height: min(65vh, 640px);
  max-height: 720px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.spo-view-embed :deep(.storyline-panel),
.spo-view-embed :deep(.plot-arc-panel) {
  flex: 1;
  min-height: 0;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.spo-bullets {
  margin: 0;
  padding-left: 1.2rem;
  font-size: 12px;
  line-height: 1.65;
}

.spo-spin {
  width: 100%;
}

.gantt-wrap {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 0;
  margin: 0;
}

.gantt-axis {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  font-weight: 600;
  color: var(--n-text-color-3);
  padding: 0 6px 8px;
  letter-spacing: 0.02em;
}

.gantt-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 32px;
  padding: 4px 0;
  transition: transform 0.2s ease;
}

.gantt-row:hover {
  transform: translateX(2px);
}

.gantt-label {
  width: 130px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow: hidden;
}

.gantt-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--n-text-color-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.gantt-track {
  flex: 1;
  height: 16px;
  background: linear-gradient(to right, rgba(24, 160, 88, 0.08), rgba(24, 160, 88, 0.12));
  border-radius: 8px;
  position: relative;
  min-width: 0;
  box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.05);
}

.gantt-bar {
  position: absolute;
  top: 2px;
  height: 12px;
  border-radius: 6px;
  background: linear-gradient(135deg, #36ad6a 0%, #18a058 100%);
  min-width: 6px;
  box-shadow: 0 2px 6px rgba(24, 160, 88, 0.3);
  transition: box-shadow 0.2s ease;
}

.gantt-bar:hover {
  box-shadow: 0 3px 10px rgba(24, 160, 88, 0.45);
}

.chart-wrap {
  width: 100%;
  overflow-x: auto;
  padding: 4px 0 0;
  margin: 0;
  box-sizing: border-box;
}

/* 曲线卡片：内容区顶对齐，避免出现「未通栏」的视错觉 */
.spo-panel :deep(.spo-card--chart .n-card__content) {
  padding-top: 8px !important;
}

.tension-svg {
  width: 100%;
  max-width: 800px;
  height: auto;
  min-height: 140px;
  display: block;
  filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.06));
  margin: 0 auto;
}

.spo-card-hint {
  font-size: 11px;
  white-space: nowrap;
}

.spo-panel :deep(.n-card) {
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  transition: box-shadow 0.3s ease;
  /* 不用 overflow:hidden，避免裁切 SVG 网格线与圆角内阴影断线 */
  overflow: visible;
}

.spo-panel :deep(.n-card:hover) {
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
}

.spo-panel :deep(.n-card-header) {
  padding: 12px 16px !important;
  font-weight: 600;
  border-bottom: 1px solid var(--n-border-color);
  background: rgba(99, 102, 241, 0.02);
}

.spo-panel :deep(.n-card-header__main) {
  display: flex;
  align-items: center;
  gap: 8px;
}

.spo-panel :deep(.n-card-header__extra) {
  display: flex;
  align-items: center;
  gap: 8px;
}

.spo-panel :deep(.n-card__content) {
  padding: 12px 16px !important;
}

.spo-panel :deep(.spo-empty-inline.n-empty) {
  padding: 16px 12px !important;
  min-height: auto !important;
}

.spo-panel :deep(.n-empty:not(.spo-empty-inline)) {
  padding: 24px 16px;
  min-height: 88px;
}

.spo-panel :deep(.n-empty__description) {
  font-size: 13px;
  color: var(--n-text-color-3);
}

.spo-panel :deep(.n-button) {
  height: 28px;
  min-height: 28px;
  padding: 0 12px;
  font-size: 13px;
}

</style>
