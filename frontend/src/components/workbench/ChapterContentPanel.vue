<template>
  <div class="cc-panel">
    <n-empty v-if="!currentChapterNumber" description="请先从左侧选择一个章节" style="margin-top: 40px" />

    <n-scrollbar v-else class="cc-scroll">
      <n-space vertical :size="12" style="padding: 8px 4px 16px">
        <n-alert v-if="readOnly" type="warning" :show-icon="true" size="small">
          托管运行中：仅可查看
        </n-alert>

        <!-- 本章规划 -->
        <n-card v-if="chapterPlan" size="small" :bordered="true" class="cc-card-plan">
          <template #header>
            <span class="card-title">📋 本章规划</span>
          </template>
          <n-descriptions :column="1" label-placement="left" size="small" label-style="white-space: nowrap">
            <n-descriptions-item label="标题">{{ chapterPlan.title || '—' }}</n-descriptions-item>
            <n-descriptions-item v-if="chapterPlan.outline" label="大纲">
              <n-text style="font-size: 12px; white-space: pre-wrap">{{ chapterPlan.outline }}</n-text>
            </n-descriptions-item>
            <n-descriptions-item v-if="chapterPlan.pov_character_id" label="视角">
              {{ getCharacterName(chapterPlan.pov_character_id) }}
            </n-descriptions-item>
            <n-descriptions-item v-if="chapterPlan.timeline_start || chapterPlan.timeline_end" label="时间线">
              {{ chapterPlan.timeline_start || '—' }} → {{ chapterPlan.timeline_end || '—' }}
            </n-descriptions-item>
            <n-descriptions-item v-if="planMoodLine" label="基调">
              {{ planMoodLine }}
            </n-descriptions-item>
          </n-descriptions>
        </n-card>

        <!-- 节拍规划 -->
        <n-card v-if="showBeatsCard" size="small" :bordered="true">
          <template #header>
            <span class="card-title">🎬 节拍规划</span>
          </template>
          <n-tabs type="segment" size="small" animated>
            <n-tab-pane name="macro" tab="宏观">
              <n-text depth="3" style="font-size: 11px; display: block; margin-bottom: 8px">
                来自章节大纲，用于叙事摘要和向量检索
              </n-text>
              <ol v-if="beatLines.length" class="cc-beat-list">
                <li v-for="(line, bi) in beatLines" :key="bi">{{ line }}</li>
              </ol>
              <n-empty v-else description="暂无宏观节拍" size="small" />
            </n-tab-pane>
            
            <n-tab-pane name="micro" tab="微观">
              <n-text depth="3" style="font-size: 11px; display: block; margin-bottom: 8px">
                写作时智能拆分，控制节奏和感官细节
              </n-text>
              <n-space v-if="microBeats.length" vertical :size="8" style="margin-top: 12px">
                <div v-for="(beat, i) in microBeats" :key="i" class="micro-beat-item">
                  <div class="micro-beat-header">
                    <n-tag :type="getBeatTypeColor(beat.focus)" size="small" round>
                      {{ beat.focus }}
                    </n-tag>
                    <n-text strong style="margin-left: 8px">节拍 {{ i + 1 }}</n-text>
                    <n-text depth="3" style="margin-left: 8px; font-size: 12px">
                      ({{ beat.target_words }}字)
                    </n-text>
                  </div>
                  <div class="micro-beat-desc">{{ beat.description }}</div>
                </div>
              </n-space>
              <n-empty v-else description="章节生成时自动创建微观节拍" size="small" />
            </n-tab-pane>
          </n-tabs>
        </n-card>

        <!-- 融合预览 -->
        <n-card size="small" :bordered="true" class="fusion-card">
          <template #header>
            <span class="card-title">🧩 融合草稿</span>
          </template>
          <template #header-extra>
            <n-space :size="6">
              <n-button size="tiny" secondary @click="fusionModalVisible = true">
                预览
              </n-button>
              <n-button size="tiny" type="primary" :loading="fusionLoading" @click="createFusionJob">
                整章融合
              </n-button>
            </n-space>
          </template>

          <n-tabs type="segment" size="small" animated>
            <n-tab-pane name="beats" tab="节拍草稿">
              <n-space vertical :size="8">
                <n-alert v-if="fusionWarningLines.length" type="warning" :show-icon="true" size="small">
                  {{ fusionWarningLines[0] }}
                </n-alert>
                <n-empty v-if="!fusionBeatDrafts.length" description="暂无节拍草稿" size="small" />
                <n-list v-else hoverable bordered>
                  <n-list-item v-for="beat in fusionBeatDrafts" :key="beat.id">
                    <n-space vertical :size="4" style="width: 100%">
                      <n-space align="center" :size="8" justify="space-between">
                        <n-text strong>{{ beat.title }}</n-text>
                        <n-tag size="tiny" round>{{ beat.id }}</n-tag>
                      </n-space>
                      <n-text depth="3" style="font-size: 12px; white-space: pre-wrap">{{ beat.text }}</n-text>
                    </n-space>
                  </n-list-item>
                </n-list>
              </n-space>
            </n-tab-pane>

            <n-tab-pane name="fusion" tab="融合草稿">
              <n-empty v-if="!fusionDraft" description="尚未生成融合稿" size="small" />
              <n-space v-else vertical :size="8">
                <n-space :size="8" wrap>
                  <n-tag size="small" type="success" round>{{ fusionState }}</n-tag>
                  <n-tag size="small" round>重复率 {{ Math.round((fusionDraft.estimated_repeat_ratio || 0) * 100) }}%</n-tag>
                </n-space>
                <n-alert v-if="fusionDraft.warnings.length" type="warning" :show-icon="true" size="small">
                  {{ fusionDraft.warnings[0] }}
                </n-alert>
                <n-input :value="fusionDraft.text" type="textarea" :autosize="{ minRows: 8, maxRows: 20 }" readonly />
              </n-space>
            </n-tab-pane>

            <n-tab-pane name="diff" tab="差异对比">
              <n-space vertical :size="10">
                <n-alert type="info" :show-icon="false" size="small">
                  左侧是节拍草稿摘要，右侧是当前融合草稿。此处用来查看融合是否过度压缩或丢失桥接。
                </n-alert>
                <div class="fusion-diff-grid">
                  <div class="fusion-diff-col">
                    <n-text strong class="diff-col-title">节拍来源</n-text>
                    <n-scrollbar style="max-height: 280px">
                      <n-space vertical :size="8">
                        <n-text v-for="beat in fusionBeatDrafts" :key="beat.id" depth="3" style="font-size: 12px; white-space: pre-wrap">
                          • {{ beat.text }}
                        </n-text>
                      </n-space>
                    </n-scrollbar>
                  </div>
                  <div class="fusion-diff-col">
                    <n-text strong class="diff-col-title">融合输出</n-text>
                    <n-scrollbar style="max-height: 280px">
                      <n-text v-if="fusionDraft" style="font-size: 12px; white-space: pre-wrap">{{ fusionDraft.text }}</n-text>
                      <n-empty v-else description="尚未生成" size="small" />
                    </n-scrollbar>
                  </div>
                </div>
              </n-space>
            </n-tab-pane>
          </n-tabs>
        </n-card>

        <!-- 本章总结 -->
        <n-card v-if="hasSummaryBlock" size="small" :bordered="true">
          <template #header>
            <span class="card-title">📝 本章总结</span>
          </template>
          <n-descriptions
            v-if="knowledgeChapter && (knowledgeChapter.summary || knowledgeChapter.key_events || knowledgeChapter.consistency_note)"
            :column="1"
            label-placement="left"
            size="small"
          >
            <n-descriptions-item v-if="knowledgeChapter.summary" label="摘要">
              <n-text style="font-size: 12px; white-space: pre-wrap">{{ knowledgeChapter.summary }}</n-text>
            </n-descriptions-item>
            <n-descriptions-item v-if="knowledgeChapter.key_events" label="关键事件">
              <n-text style="font-size: 12px; white-space: pre-wrap">{{ knowledgeChapter.key_events }}</n-text>
            </n-descriptions-item>
            <n-descriptions-item v-if="knowledgeChapter.consistency_note" label="一致性">
              <n-text style="font-size: 12px; white-space: pre-wrap">{{ knowledgeChapter.consistency_note }}</n-text>
            </n-descriptions-item>
          </n-descriptions>
          <n-text v-else-if="chapterPlan?.description" style="font-size: 12px; white-space: pre-wrap">
            {{ chapterPlan.description }}
          </n-text>
        </n-card>

        <n-alert v-else-if="storyNodeNotFound" type="warning" :show-icon="true">
          未在结构树中找到第 {{ currentChapterNumber }} 章的规划节点
        </n-alert>

        <!-- 全托管管线摘要 -->
        <n-card
          v-if="autopilotChapterReview && currentChapterNumber === autopilotChapterReview.chapter_number"
          size="small"
          :bordered="true"
        >
          <template #header>
            <span class="card-title">🤖 自动审阅</span>
          </template>
          <n-space vertical :size="8">
            <div class="review-row">
              <n-text depth="3">张力</n-text>
              <div class="tension-bar">
                <div class="tension-fill" :style="{ width: `${autopilotChapterReview.tension * 10}%` }"></div>
                <n-text class="tension-value">{{ autopilotChapterReview.tension }}/10</n-text>
              </div>
            </div>
            <div class="review-row">
              <n-text depth="3">叙事同步</n-text>
              <n-tag
                :type="autopilotChapterReview.narrative_sync_ok ? 'success' : 'warning'"
                size="small"
                round
              >
                {{ autopilotChapterReview.narrative_sync_ok ? '已落库' : '异常' }}
              </n-tag>
            </div>
            <div class="review-row">
              <n-text depth="3">文风相似度</n-text>
              <n-text>
                {{
                  autopilotChapterReview.similarity_score != null
                    ? Number(autopilotChapterReview.similarity_score).toFixed(3)
                    : '—'
                }}
              </n-text>
            </div>
            <div class="review-row">
              <n-text depth="3">漂移告警</n-text>
              <n-tag :type="autopilotChapterReview.drift_alert ? 'error' : 'success'" size="small" round>
                {{ autopilotChapterReview.drift_alert ? '是' : '否' }}
              </n-tag>
            </div>
            <div v-if="autopilotChapterReview.at" class="review-row">
              <n-text depth="3">审阅时间</n-text>
              <n-text depth="3" style="font-size: 12px">{{ formatTime(autopilotChapterReview.at) }}</n-text>
            </div>
          </n-space>
        </n-card>

        <n-modal v-model:show="fusionModalVisible" preset="card" title="融合预览" style="width: min(760px, 96vw);">
          <n-space vertical :size="14">
            <n-alert type="info" :show-icon="true">
              预览基于当前章节规划、节拍线索与知识章末摘要推导。正式融合会写入融合任务记录。
            </n-alert>
            <n-descriptions :column="2" bordered size="small" label-placement="left">
              <n-descriptions-item label="预计字数">{{ fusionPreview.estimated_words }}</n-descriptions-item>
              <n-descriptions-item label="预计重复率">{{ Math.round(fusionPreview.estimated_repeat_ratio * 100) }}%</n-descriptions-item>
              <n-descriptions-item label="预计终态" :span="2">
                {{ formatPreviewState(fusionPreview.expected_end_state) }}
              </n-descriptions-item>
              <n-descriptions-item label="预计悬念数">{{ fusionPreview.expected_suspense_count }}</n-descriptions-item>
              <n-descriptions-item label="预警数">{{ fusionPreview.risk_warnings.length }}</n-descriptions-item>
            </n-descriptions>
            <n-space v-if="fusionPreview.risk_warnings.length" vertical :size="8">
              <n-alert v-for="(warn, index) in fusionPreview.risk_warnings" :key="index" type="warning" :show-icon="true" size="small">
                {{ warn }}
              </n-alert>
            </n-space>
            <n-space justify="end">
              <n-button @click="fusionModalVisible = false">关闭</n-button>
              <n-button type="primary" :loading="fusionLoading" @click="createFusionJob">开始融合</n-button>
            </n-space>
          </n-space>
        </n-modal>
      </n-space>
    </n-scrollbar>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useMessage } from 'naive-ui'
import { useWorkbenchRefreshStore } from '../../stores/workbenchRefreshStore'
import { planningApi } from '../../api/planning'
import type { StoryNode } from '../../api/planning'
import { knowledgeApi } from '../../api/knowledge'
import type { ChapterSummary } from '../../api/knowledge'
import { bibleApi, type CharacterDTO } from '../../api/bible'
import { chapterFusionApi, type FusionJobDTO, type FusionPreviewDTO } from '../../api/chapterFusion'
import type { AutopilotChapterAudit } from './ChapterStatusPanel.vue'

const props = withDefaults(
  defineProps<{
    slug: string
    currentChapterNumber?: number | null
    readOnly?: boolean
    autopilotChapterReview?: AutopilotChapterAudit | null
  }>(),
  {
    currentChapterNumber: null,
    readOnly: false,
    autopilotChapterReview: null,
  }
)

const storyNodeNotFound = ref(false)
const chapterPlan = ref<StoryNode | null>(null)
const knowledgeChapter = ref<ChapterSummary | null>(null)
const fusionJob = ref<FusionJobDTO | null>(null)
const fusionLoading = ref(false)
const fusionModalVisible = ref(false)
const fusionPollTimer = ref<ReturnType<typeof setInterval> | null>(null)

// Bible 数据用于 ID -> name 映射
const bibleCharacters = ref<CharacterDTO[]>([])

// 获取人物名称
const getCharacterName = (charId: string): string => {
  const char = bibleCharacters.value.find(c => c.id === charId)
  return char ? char.name : charId
}

const planMoodLine = computed(() => {
  const m = chapterPlan.value?.metadata
  if (!m || typeof m !== 'object') return ''
  const mood = m.mood ?? m.emotion ?? m.tone
  if (typeof mood === 'string' && mood.trim()) return mood
  if (Array.isArray(m.moods) && m.moods.length) return m.moods.join('、')
  return ''
})

const beatLines = computed(() => {
  const k = knowledgeChapter.value
  if (k?.beat_sections?.length) {
    return k.beat_sections.map(s => String(s || '').trim()).filter(Boolean)
  }
  const ol = chapterPlan.value?.outline?.trim()
  if (!ol) return []
  return ol.split(/\n+/).map(s => s.trim()).filter(s => s.length > 0)
})

const fusionBeatDrafts = computed(() => {
  const beats = beatLines.value.length > 0 ? beatLines.value : ['承接前情，推进主线', '制造转折与压力', '收束到章节终态']
  return beats.map((line, index) => ({
    id: `beat-${props.currentChapterNumber ?? 0}-${index + 1}`,
    title: line.slice(0, 24) || `Beat ${index + 1}`,
    text: line,
  }))
})

const fusionPreview = computed<FusionPreviewDTO>(() => {
  const drafts = fusionBeatDrafts.value
  const normalized = drafts.map(item => item.text.replace(/\s+/g, '').toLowerCase())
  const unique = new Set(normalized.filter(Boolean))
  const duplicateCount = Math.max(0, normalized.length - unique.size)
  const repeatRatio = normalized.length > 0 ? duplicateCount / normalized.length : 0
  const estimatedWords = Math.max(1200, drafts.reduce((sum, item) => sum + Math.max(180, item.text.length * 2), 0))
  const endState = knowledgeChapter.value?.ending_state
    ? { ending_state: knowledgeChapter.value.ending_state }
    : { chapter_end: chapterPlan.value?.timeline_end || chapterPlan.value?.title || '章节终态' }
  const warnings: string[] = []
  if (repeatRatio > 0.15) warnings.push('重复功能偏高，建议先回到节拍层去重')
  if (!beatLines.value.length) warnings.push('未检出明确节拍文本，融合预览基于章节摘要推导')
  return {
    estimated_words: estimatedWords,
    estimated_repeat_ratio: Number(repeatRatio.toFixed(2)),
    expected_end_state: endState,
    expected_suspense_count: Math.max(1, Math.min(5, drafts.length + 1)),
    risk_warnings: warnings,
  }
})

const fusionDraft = computed(() => fusionJob.value?.fusion_draft ?? null)
const fusionState = computed(() => fusionJob.value?.status ?? 'idle')
const fusionWarningLines = computed(() => fusionDraft.value?.warnings?.length ? fusionDraft.value.warnings : fusionPreview.value.risk_warnings)

const fusionStorageKey = computed(() => `plotpilot:fusion-job:${props.slug}:${props.currentChapterNumber ?? 'none'}`)

function loadStoredFusionJobId(): string | null {
  try {
    return window.localStorage.getItem(fusionStorageKey.value)
  } catch {
    return null
  }
}

function persistFusionJobId(jobId: string) {
  try {
    window.localStorage.setItem(fusionStorageKey.value, jobId)
  } catch {
    /* ignore */
  }
}

function clearFusionPoll() {
  if (fusionPollTimer.value) {
    clearInterval(fusionPollTimer.value)
    fusionPollTimer.value = null
  }
}

async function loadFusionJob(fusionJobId: string) {
  fusionLoading.value = true
  try {
    const job = await chapterFusionApi.getFusionJob(fusionJobId)
    fusionJob.value = job
    if (job.status === 'queued' || job.status === 'running') {
      clearFusionPoll()
      fusionPollTimer.value = window.setInterval(() => {
        void loadFusionJob(fusionJobId)
      }, 1600)
    } else {
      clearFusionPoll()
    }
  } catch {
    fusionJob.value = null
    clearFusionPoll()
  } finally {
    fusionLoading.value = false
  }
}

async function loadLatestFusionJob() {
  const jobId = loadStoredFusionJobId()
  if (!jobId) {
    fusionJob.value = null
    clearFusionPoll()
    return
  }
  await loadFusionJob(jobId)
}

async function createFusionJob() {
  const chapterNumber = props.currentChapterNumber
  if (!props.slug || !chapterNumber || fusionLoading.value) return
  fusionLoading.value = true
  try {
    const planVersion = Number((chapterPlan.value?.metadata as Record<string, unknown> | undefined)?.version ?? 1)
    const stateLockVersion = Number((chapterPlan.value?.metadata as Record<string, unknown> | undefined)?.state_lock_version ?? 1)
    const targetWords = Math.max(1800, fusionBeatDrafts.value.length * 900)
    const beatIds = fusionBeatDrafts.value.map(item => item.id)
    const suspenseBudget = {
      primary: 1,
      secondary: Math.max(1, Math.min(3, fusionBeatDrafts.value.length - 1)),
    }
    const job = await chapterFusionApi.createFusionJob(props.slug, {
      plan_version: planVersion,
      state_lock_version: stateLockVersion,
      beat_ids: beatIds,
      target_words: targetWords,
      suspense_budget: suspenseBudget,
    })
    persistFusionJobId(job.fusion_job_id)
    fusionJob.value = job
    clearFusionPoll()
    fusionPollTimer.value = window.setInterval(() => {
      void loadFusionJob(job.fusion_job_id)
    }, 1600)
    fusionModalVisible.value = false
    message.success('融合任务已创建')
  } catch {
    message.error('创建融合任务失败')
  } finally {
    fusionLoading.value = false
  }
}

const showBeatsCard = computed(() => {
  if (!props.currentChapterNumber) return false
  if (beatLines.value.length > 0) return true
  return !!(chapterPlan.value?.outline?.trim() || knowledgeChapter.value)
})

interface MicroBeat {
  description: string
  target_words: number
  focus: string
}

// TODO: 微观节拍需要从后端 API 获取（章节生成时由守护进程创建）
// 当前暂时从 knowledgeChapter 中读取
const microBeats = computed<MicroBeat[]>(() => {
  const k = knowledgeChapter.value
  if (k?.micro_beats && Array.isArray(k.micro_beats)) {
    return k.micro_beats as MicroBeat[]
  }
  return []
})

const getBeatTypeColor = (focus: string): 'success' | 'warning' | 'error' | 'info' | 'default' => {
  const colorMap: Record<string, 'success' | 'warning' | 'error' | 'info' | 'default'> = {
    sensory: 'info',
    dialogue: 'success',
    action: 'warning',
    emotion: 'error',
  }
  return colorMap[focus] || 'default'
}

const hasSummaryBlock = computed(() => {
  if (!props.currentChapterNumber) return false
  const k = knowledgeChapter.value
  if (k && (k.summary?.trim() || k.key_events?.trim() || k.consistency_note?.trim())) return true
  return !!chapterPlan.value?.description?.trim()
})

function formatTime(t: string) {
  try {
    return new Date(t).toLocaleString('zh-CN', {
      month: 'numeric',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  } catch {
    return t
  }
}

function formatPreviewState(state: Record<string, unknown>): string {
  const entries = Object.entries(state || {})
  if (!entries.length) return '—'
  return entries.map(([k, v]) => `${k}: ${String(v)}`).join(' / ')
}

function findChapterNode(nodes: StoryNode[], num: number): StoryNode | null {
  for (const node of nodes) {
    if (node.node_type === 'chapter' && node.number === num) return node
    if (node.children?.length) {
      const found = findChapterNode(node.children, num)
      if (found) return found
    }
  }
  return null
}

const resolveStoryNode = async () => {
  chapterPlan.value = null
  storyNodeNotFound.value = false
  if (!props.currentChapterNumber) return
  try {
    const res = await planningApi.getStructure(props.slug)
    const roots = res.data?.nodes ?? []
    const node = findChapterNode(roots, props.currentChapterNumber)
    if (node) {
      chapterPlan.value = node
    } else {
      storyNodeNotFound.value = true
    }
  } catch {
    storyNodeNotFound.value = true
  }
}

async function loadKnowledgeChapter() {
  knowledgeChapter.value = null
  if (!props.slug || !props.currentChapterNumber) return
  try {
    const k = await knowledgeApi.getKnowledge(props.slug)
    const row = k.chapters?.find(c => c.chapter_id === props.currentChapterNumber)
    knowledgeChapter.value = row ?? null
  } catch {
    knowledgeChapter.value = null
  }
}

// 加载 Bible 数据用于名称映射
async function loadBible() {
  try {
    const bible = await bibleApi.getBible(props.slug)
    bibleCharacters.value = bible.characters || []
  } catch {
    bibleCharacters.value = []
  }
}

watch(() => props.slug, async (slug) => {
  if (slug) {
    chapterPlan.value = null
    storyNodeNotFound.value = false
    await Promise.all([
      loadBible(),
      resolveStoryNode(),
      loadKnowledgeChapter()
    ])
  }
})

watch(() => props.currentChapterNumber, async () => {
  await resolveStoryNode()
  await loadKnowledgeChapter()
  await loadLatestFusionJob()
}, { immediate: false })

const refreshStore = useWorkbenchRefreshStore()
const { deskTick } = storeToRefs(refreshStore)
watch(deskTick, async () => {
  await resolveStoryNode()
  await loadKnowledgeChapter()
  await loadLatestFusionJob()
})

onMounted(async () => {
  await loadBible()
  await resolveStoryNode()
  await loadKnowledgeChapter()
  await loadLatestFusionJob()
})

watch(
  () => [props.slug, props.currentChapterNumber] as const,
  async () => {
    await loadLatestFusionJob()
  }
)

const message = useMessage()

onUnmounted(() => clearFusionPoll())
</script>

<style scoped>
.cc-panel {
  padding: 0;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.cc-scroll {
  flex: 1;
  min-height: 0;
}

.card-title {
  font-size: 13px;
  font-weight: 600;
}

/* 节拍列表 */
.cc-beat-list {
  margin: 8px 0 0;
  padding-left: 1.2em;
  font-size: 12px;
  line-height: 1.8;
}

/* 微观节拍 */
.micro-beat-item {
  padding: 12px 14px;
  border-radius: 10px;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.04) 0%, rgba(139, 92, 246, 0.02) 100%);
  border: 1px solid rgba(99, 102, 241, 0.1);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.micro-beat-item:hover {
  border-color: rgba(99, 102, 241, 0.2);
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.06) 0%, rgba(139, 92, 246, 0.04) 100%);
}

.micro-beat-header {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
}

.micro-beat-desc {
  margin-top: 6px;
  padding-left: 12px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--n-text-color-2);
  border-left: 2px solid var(--n-border-color);
}

.micro-beat-item:hover .micro-beat-desc {
  border-left-color: var(--n-primary-color);
}

.fusion-card {
  border-color: rgba(14, 165, 233, 0.16);
  background: linear-gradient(180deg, rgba(14, 165, 233, 0.03) 0%, rgba(99, 102, 241, 0.02) 100%);
}

.fusion-diff-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.fusion-diff-col {
  padding: 12px;
  border-radius: 10px;
  border: 1px solid var(--n-border-color);
  background: var(--n-color-modal);
  min-height: 220px;
}

.diff-col-title {
  display: block;
  margin-bottom: 8px;
  font-size: 12px;
}

/* 审阅行 */
.review-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

/* 张力进度条 */
.tension-bar {
  position: relative;
  width: 100px;
  height: 20px;
  background: var(--n-color-modal);
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid var(--n-border-color);
}

.tension-fill {
  height: 100%;
  background: linear-gradient(90deg, #10b981, #f59e0b, #ef4444);
  border-radius: 10px;
  transition: width 0.3s ease;
}

.tension-value {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 11px;
  font-weight: 600;
  color: var(--n-text-color-1);
}
</style>
