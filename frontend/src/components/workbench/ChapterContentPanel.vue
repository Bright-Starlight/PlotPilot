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

        <n-card size="small" :bordered="true" class="state-lock-card">
          <template #header>
            <span class="card-title">🔒 State Locks</span>
          </template>
          <template #header-extra>
            <n-space :size="6">
              <n-button size="tiny" secondary :loading="stateLocksLoading" @click="generateStateLocks">
                {{ stateLocks ? '重建锁版本' : '生成状态锁' }}
              </n-button>
              <n-button size="tiny" tertiary :disabled="!stateLocks" @click="openStateLockEditor">
                编辑
              </n-button>
            </n-space>
          </template>

          <n-space vertical :size="8">
            <n-alert v-if="!stateLocks" type="warning" :show-icon="true" size="small">
              当前章节还没有冻结事实边界。先生成状态锁，再启动融合或后续校验。
            </n-alert>
            <template v-else>
              <n-space :size="8" wrap>
                <n-tag size="small" round>版本 v{{ stateLocks.version }}</n-tag>
                <n-tag size="small" round>{{ stateLocks.source }}</n-tag>
                <n-tag v-if="stateLocks.change_reason" size="small" type="warning" round>最近修改：{{ stateLocks.change_reason }}</n-tag>
                <n-tag v-if="fusionUsesOutdatedStateLock" size="small" type="error" round>融合稿需重新生成</n-tag>
              </n-space>
              <n-alert v-if="fusionUsesOutdatedStateLock" type="warning" :show-icon="true" size="small">
                当前融合稿绑定的是旧的状态锁版本，新的锁边界可能已经让它失效。
              </n-alert>
              <n-alert v-if="stateLocks.inference_notes.length" type="info" :show-icon="false" size="small">
                {{ stateLocks.inference_notes[0] }}
              </n-alert>
              <div
                v-for="item in stateLockGroups"
                :id="`state-lock-group-${item.key}`"
                :key="item.key"
                class="state-lock-group"
                :class="{ 'state-lock-group-active': activeLockGroup === item.key }"
              >
                <n-text strong class="diff-col-title">{{ item.label }}</n-text>
                <n-empty v-if="!item.group?.entries?.length" description="无锁定条目" size="small" />
                <n-list v-else hoverable bordered>
                  <n-list-item v-for="entry in item.group.entries" :key="entry.key">
                    <n-space vertical :size="4" style="width: 100%">
                      <n-space align="center" justify="space-between">
                        <n-text strong>{{ entry.label }}</n-text>
                        <n-tag size="tiny" round :type="lockStatusTagType(entry.status)">{{ entry.status }}</n-tag>
                      </n-space>
                      <n-text depth="3" style="font-size: 12px; white-space: pre-wrap">{{ formatLockValue(entry.value) }}</n-text>
                    </n-space>
                  </n-list-item>
                </n-list>
              </div>
            </template>
          </n-space>
        </n-card>

        <n-card size="small" :bordered="true" class="validation-card">
          <template #header>
            <span class="card-title">🛡 Validation</span>
          </template>
          <template #header-extra>
            <n-space :size="6">
              <n-button size="tiny" tertiary @click="openValidationCenter">
                验证中心
              </n-button>
              <n-button size="tiny" tertiary :loading="validationLoading" :disabled="!fusionDraft" @click="startValidation">
                重新校验
              </n-button>
            </n-space>
          </template>
          <n-space vertical :size="8">
            <n-alert v-if="!fusionDraft" type="info" :show-icon="true" size="small">
              生成融合稿后会自动触发一次校验，这里展示最新报告。
            </n-alert>
            <template v-else-if="validationReport">
              <n-space :size="8" wrap>
                <n-tag size="small" round :type="validationReport.passed ? 'success' : 'error'">
                  {{ validationReport.passed ? '校验通过' : '存在阻断问题' }}
                </n-tag>
                <n-tag size="small" round>报告 {{ validationReport.report_id }}</n-tag>
                <n-tag size="small" round>P0 {{ validationReport.p0_count }}</n-tag>
                <n-tag size="small" round>P1 {{ validationReport.p1_count }}</n-tag>
                <n-tag size="small" round>P2 {{ validationReport.p2_count }}</n-tag>
                <n-tag size="small" round>Token {{ validationReport.token_usage.total_tokens }}</n-tag>
              </n-space>
              <n-alert
                v-if="validationReport.state_lock_version < (currentStateLockVersion || 0)"
                type="warning"
                :show-icon="true"
                size="small"
              >
                当前报告绑定的是旧的状态锁版本，建议重新运行校验。
              </n-alert>
              <n-space v-for="group in validationIssueGroups" :key="group.severity" vertical :size="8">
                <n-text strong class="diff-col-title">{{ group.severity }} 问题（{{ group.issues.length }}）</n-text>
                <n-empty v-if="!group.issues.length" description="无问题" size="small" />
                <n-list v-else hoverable bordered>
                  <n-list-item v-for="issue in group.issues" :key="issue.issue_id">
                    <n-space vertical :size="6" style="width: 100%">
                      <n-space align="center" justify="space-between">
                        <n-space :size="8" align="center">
                          <n-tag size="tiny" :type="issue.blocking ? 'error' : 'warning'" round>
                            {{ issue.blocking ? 'blocking' : 'advisory' }}
                          </n-tag>
                          <n-text strong>{{ issue.title }}</n-text>
                        </n-space>
                        <n-button
                          v-if="issue.metadata.group"
                          size="tiny"
                          tertiary
                          @click="jumpToLockGroup(String(issue.metadata.group || ''))"
                        >
                          定位锁项
                        </n-button>
                      </n-space>
                      <n-text depth="3" style="font-size: 12px; white-space: pre-wrap">{{ issue.message }}</n-text>
                      <n-text v-if="issue.spans.length" depth="3" style="font-size: 12px; white-space: pre-wrap">
                        段落 {{ issue.spans[0].paragraph_index + 1 }}：{{ issue.spans[0].excerpt }}
                      </n-text>
                      <n-space :size="6" wrap>
                        <n-button
                          v-if="issue.suggest_patch"
                          size="tiny"
                          secondary
                          :loading="issueActionLoading"
                          @click="requestRepairPatch(issue)"
                        >
                          修复建议
                        </n-button>
                        <n-button
                          size="tiny"
                          tertiary
                          :loading="issueActionLoading"
                          @click="updateIssueStatus(issue, 'resolved')"
                        >
                          标记已解决
                        </n-button>
                        <n-button
                          v-if="issue.severity !== 'P0'"
                          size="tiny"
                          tertiary
                          :loading="issueActionLoading"
                          @click="updateIssueStatus(issue, 'ignored')"
                        >
                          忽略
                        </n-button>
                        <n-button
                          v-if="issue.status !== 'unresolved'"
                          size="tiny"
                          tertiary
                          :loading="issueActionLoading"
                          @click="updateIssueStatus(issue, 'unresolved')"
                        >
                          设为未处理
                        </n-button>
                      </n-space>
                      <n-alert
                        v-if="repairPatchByIssueId[issue.issue_id]"
                        type="info"
                        :show-icon="false"
                        size="small"
                      >
                        {{ repairPatchByIssueId[issue.issue_id] }}
                      </n-alert>
                    </n-space>
                  </n-list-item>
                </n-list>
              </n-space>
            </template>
            <n-alert v-else type="warning" :show-icon="true" size="small">
              还没有校验报告。可手动触发一次校验，或重新生成融合稿后自动刷新。
            </n-alert>
          </n-space>
        </n-card>

        <!-- 融合确认 -->
        <n-card size="small" :bordered="true" class="fusion-card">
          <template #header>
            <span class="card-title">🧩 融合草稿</span>
          </template>
          <template #header-extra>
            <n-space :size="6">
              <n-button size="tiny" secondary @click="fusionModalVisible = true">
                融合设置
              </n-button>
              <n-button size="tiny" type="primary" :loading="fusionLoading" @click="createFusionJob">
                整章融合
              </n-button>
            </n-space>
          </template>

          <n-tabs type="segment" size="small" animated>
            <n-tab-pane name="beats" tab="节拍草稿">
              <n-space vertical :size="8">
                <n-alert v-if="!beatSheet && chapterPlan" type="info" :show-icon="true" size="small">
                  当前章节尚未生成真实节拍表，开始融合时会先自动生成。
                </n-alert>
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
              <n-space vertical :size="8">
                <n-space :size="8" wrap>
                  <n-tag v-if="fusionJob" size="small" :type="fusionState === 'failed' ? 'error' : fusionState === 'warning' ? 'warning' : 'success'" round>
                    {{ fusionState }}
                  </n-tag>
                  <n-tag v-if="fusionJob" size="small" round>任务 {{ fusionJob.fusion_job_id }}</n-tag>
                  <n-tag size="small" round>重复率 {{ Math.round((fusionDraft?.estimated_repeat_ratio || 0) * 100) }}%</n-tag>
                </n-space>
                <n-empty v-if="!fusionDraft" description="尚未生成融合稿" size="small" />
                <n-alert v-else-if="fusionDraft.warnings.length" type="warning" :show-icon="true" size="small">
                  {{ fusionDraft.warnings[0] }}
                </n-alert>
                <n-input v-if="fusionDraft" :value="fusionDraft.text" type="textarea" :autosize="{ minRows: 8, maxRows: 20 }" readonly />
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

        <n-modal v-model:show="fusionModalVisible" preset="card" title="融合设置" style="width: min(760px, 96vw);">
          <n-space vertical :size="14">
            <n-alert type="info" :show-icon="true">
              这里展示的是本次融合会提交的真实输入，不再显示前端估算值。正式融合会写入融合任务记录。
            </n-alert>
            <n-descriptions :column="2" bordered size="small" label-placement="left">
              <n-descriptions-item label="章节 ID">{{ fusionChapterId || '—' }}</n-descriptions-item>
              <n-descriptions-item label="节拍数">{{ fusionBeatDrafts.length }}</n-descriptions-item>
              <n-descriptions-item label="目标字数">{{ fusionRequest.target_words }}</n-descriptions-item>
              <n-descriptions-item label="悬念预算">
                主 {{ fusionRequest.suspense_budget.primary }} / 支 {{ fusionRequest.suspense_budget.secondary }}
              </n-descriptions-item>
              <n-descriptions-item label="终态线索" :span="2">
                {{ fusionConstraintState }}
              </n-descriptions-item>
            </n-descriptions>
            <n-space v-if="fusionInputWarnings.length" vertical :size="8">
              <n-alert v-for="(warn, index) in fusionInputWarnings" :key="index" type="warning" :show-icon="true" size="small">
                {{ warn }}
              </n-alert>
            </n-space>
            <n-space justify="end">
              <n-button @click="fusionModalVisible = false">关闭</n-button>
              <n-button type="primary" :loading="fusionLoading" @click="createFusionJob">开始融合</n-button>
            </n-space>
          </n-space>
        </n-modal>

        <n-modal v-model:show="stateLockEditorVisible" preset="card" title="编辑状态锁" style="width: min(780px, 96vw);">
          <n-space vertical :size="12">
            <n-alert type="warning" :show-icon="true" size="small">
              保存会创建一个新的完整锁版本，并要求填写修改原因。
            </n-alert>
            <n-input
              v-model:value="stateLockChangeReason"
              type="text"
              placeholder="修改原因，例如：终态地点改为钱府正厅"
            />
            <n-input
              v-model:value="stateLockEditorJson"
              type="textarea"
              :autosize="{ minRows: 16, maxRows: 24 }"
            />
            <n-space justify="end">
              <n-button @click="stateLockEditorVisible = false">取消</n-button>
              <n-button type="primary" :loading="stateLocksLoading" @click="saveStateLockEdit">保存新版本</n-button>
            </n-space>
          </n-space>
        </n-modal>
      </n-space>
    </n-scrollbar>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useMessage } from 'naive-ui'
import { useWorkbenchRefreshStore } from '../../stores/workbenchRefreshStore'
import { planningApi } from '../../api/planning'
import type { StoryNode } from '../../api/planning'
import { knowledgeApi } from '../../api/knowledge'
import type { ChapterSummary } from '../../api/knowledge'
import { bibleApi, type CharacterDTO } from '../../api/bible'
import { chapterFusionApi, type FusionJobDTO } from '../../api/chapterFusion'
import { stateLocksApi, type StateLockSnapshotDTO, type StateLockGroupDTO } from '../../api/stateLocks'
import { validationReportsApi, type ValidationIssueDTO, type ValidationReportDetailDTO } from '../../api/validationReports'
import { beatSheetApi, type BeatSheetDTO } from '../../api/beatSheet'
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
const beatSheet = ref<BeatSheetDTO | null>(null)
const fusionJob = ref<FusionJobDTO | null>(null)
const stateLocks = ref<StateLockSnapshotDTO | null>(null)
const validationReport = ref<ValidationReportDetailDTO | null>(null)
const fusionLoading = ref(false)
const stateLocksLoading = ref(false)
const validationLoading = ref(false)
const issueActionLoading = ref(false)
const fusionModalVisible = ref(false)
const stateLockEditorVisible = ref(false)
const fusionPollTimer = ref<number | null>(null)
const stateLockEditorJson = ref('')
const stateLockChangeReason = ref('')
const activeLockGroup = ref('')
const repairPatchByIssueId = ref<Record<string, string>>({})
const router = useRouter()

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

interface FusionBeatDraftView {
  id: string
  title: string
  text: string
}

function buildFusionBeatDrafts(source: BeatSheetDTO | null): FusionBeatDraftView[] {
  if (source?.scenes?.length) {
    return source.scenes.map(scene => {
      const title = String(scene.title || '').trim() || `节拍 ${scene.order_index + 1}`
      const parts = [
        String(scene.goal || '').trim(),
        scene.location ? `地点：${scene.location}` : '',
        scene.tone ? `基调：${scene.tone}` : '',
      ].filter(Boolean)
      return {
        id: `beat-${props.currentChapterNumber ?? 0}-${scene.order_index + 1}`,
        title,
        text: parts.length ? `${title}：${parts.join('｜')}` : title,
      }
    })
  }

  const beats = beatLines.value.length > 0 ? beatLines.value : ['承接前情，推进主线', '制造转折与压力', '收束到章节终态']
  return beats.map((line, index) => ({
    id: `beat-${props.currentChapterNumber ?? 0}-${index + 1}`,
    title: line.slice(0, 24) || `节拍 ${index + 1}`,
    text: line,
  }))
}

const fusionBeatDrafts = computed(() => buildFusionBeatDrafts(beatSheet.value))

const fusionRequest = computed(() => {
  const drafts = fusionBeatDrafts.value
  return {
    beat_ids: drafts.map(item => item.id),
    target_words: Math.max(1800, drafts.length * 900),
    suspense_budget: {
      primary: 1,
      secondary: Math.max(1, Math.min(3, drafts.length - 1)),
    },
  }
})

const fusionDraft = computed(() => fusionJob.value?.fusion_draft ?? null)
const fusionState = computed(() => fusionJob.value?.status ?? 'idle')
const currentStateLockVersion = computed(() => stateLocks.value?.version ?? null)
const fusionUsesOutdatedStateLock = computed(() => {
  if (!fusionDraft.value || !currentStateLockVersion.value) return false
  return fusionDraft.value.state_lock_version < currentStateLockVersion.value
})
const validationIssueGroups = computed(() => {
  const levels: Array<'P0' | 'P1' | 'P2'> = ['P0', 'P1', 'P2']
  return levels.map(severity => ({
    severity,
    issues: (validationReport.value?.issues_by_severity?.[severity] ?? []) as ValidationIssueDTO[],
  }))
})
const stateLockGroups = computed(() => {
  if (!stateLocks.value) return []
  return [
    ['time_lock', '时间锁'],
    ['location_lock', '地点锁'],
    ['character_lock', '人物锁'],
    ['item_lock', '道具锁'],
    ['numeric_lock', '数值锁'],
    ['event_lock', '事件锁'],
    ['ending_lock', '终态锁'],
  ].map(([key, label]) => ({
    key,
    label,
    group: stateLocks.value?.[key as keyof StateLockSnapshotDTO] as StateLockGroupDTO,
  }))
})
const fusionConstraintState = computed(() => {
  const endingGroup = stateLocks.value?.ending_lock?.entries ?? []
  if (endingGroup.length) return String(endingGroup[0].value ?? '未提供')
  if (knowledgeChapter.value?.ending_state?.trim()) return knowledgeChapter.value.ending_state.trim()
  if (chapterPlan.value?.timeline_end?.trim()) return chapterPlan.value.timeline_end.trim()
  if (chapterPlan.value?.title?.trim()) return chapterPlan.value.title.trim()
  return '未提供'
})
const fusionInputWarnings = computed(() => {
  const warnings: string[] = []
  if (!beatSheet.value?.scenes?.length) warnings.push('当前尚未落库真实节拍表，提交前会先尝试自动生成。')
  if (!beatLines.value.length) warnings.push('未检出明确节拍文本，本次融合将主要依赖章节大纲与生成后的节拍表。')
  if (!stateLocks.value) warnings.push('当前章节尚未生成状态锁，融合前必须先生成。')
  return warnings
})
const fusionWarningLines = computed(() => fusionDraft.value?.warnings?.length ? fusionDraft.value.warnings : fusionInputWarnings.value)
const fusionChapterId = computed(() => {
  if (chapterPlan.value?.id) return chapterPlan.value.id
  if (props.slug && props.currentChapterNumber) {
    return `chapter-${props.slug}-chapter-${props.currentChapterNumber}`
  }
  return null
})

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
    await loadLatestValidationReport()
  } catch {
    fusionJob.value = null
    clearFusionPoll()
    validationReport.value = null
  } finally {
    fusionLoading.value = false
  }
}

async function loadLatestFusionJob() {
  const jobId = loadStoredFusionJobId()
  if (!jobId) {
    fusionJob.value = null
    validationReport.value = null
    clearFusionPoll()
    return
  }
  await loadFusionJob(jobId)
}

async function loadLatestValidationReport() {
  const chapterId = fusionChapterId.value
  const draft = fusionDraft.value
  if (!chapterId || !draft) {
    validationReport.value = null
    return
  }
  validationLoading.value = true
  try {
    if (draft.latest_validation_report_id) {
      validationReport.value = await validationReportsApi.getValidationReport(draft.latest_validation_report_id)
      return
    }
    validationReport.value = await validationReportsApi.getLatestValidationReport(chapterId, {
      draftType: 'fusion',
      draftId: draft.fusion_id,
    })
  } catch {
    validationReport.value = null
  } finally {
    validationLoading.value = false
  }
}

function getBeatSheetOutline(): string {
  const outline = chapterPlan.value?.outline?.trim()
  if (outline) return outline
  const fallback = beatLines.value.join('\n').trim()
  if (fallback) return fallback
  return ''
}

async function loadBeatSheet() {
  beatSheet.value = null
  const chapterId = fusionChapterId.value
  if (!chapterId) return
  try {
    const sheet = await beatSheetApi.getBeatSheet(chapterId)
    if (sheet?.scenes?.length) {
      beatSheet.value = sheet
      return
    }
  } catch {
    // 继续尝试生成兜底
  }

  const outline = getBeatSheetOutline()
  if (!outline) return

  try {
    const generated = await beatSheetApi.generateBeatSheet({
      chapter_id: chapterId,
      outline,
    })
    if (generated?.scenes?.length) {
      beatSheet.value = generated
    }
  } catch {
    beatSheet.value = null
  }
}

async function ensureBeatSheet(): Promise<BeatSheetDTO | null> {
  const chapterId = fusionChapterId.value
  if (!chapterId) return null
  if (beatSheet.value?.chapter_id === chapterId && beatSheet.value.scenes.length > 0) {
    return beatSheet.value
  }
  await loadBeatSheet()
  if (beatSheet.value?.chapter_id === chapterId && beatSheet.value.scenes.length > 0) {
    return beatSheet.value
  }
  throw new Error('当前章节缺少可用于生成节拍表的大纲')
}

async function createFusionJob() {
  const chapterNumber = props.currentChapterNumber
  const chapterId = fusionChapterId.value
  if (!props.slug || !chapterNumber || !chapterId) return
  if (!stateLocks.value) {
    message.error('请先生成状态锁，再启动融合')
    return
  }
  fusionLoading.value = true
  try {
    const ensuredBeatSheet = await ensureBeatSheet()
    const planVersion = Number((chapterPlan.value?.metadata as Record<string, unknown> | undefined)?.version ?? 1)
    const stateLockVersion = stateLocks.value.version
    const drafts = buildFusionBeatDrafts(ensuredBeatSheet ?? beatSheet.value)
    const targetWords = fusionRequest.value.target_words
    const beatIds = drafts.map(item => item.id)
    const suspenseBudget = fusionRequest.value.suspense_budget
    const job = await chapterFusionApi.createFusionJob(chapterId, {
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
  } catch (error) {
    const detail = getApiErrorMessage(error) || (error instanceof Error ? error.message : '')
    message.error(detail ? `创建融合任务失败：${detail}` : '创建融合任务失败')
  } finally {
    fusionLoading.value = false
  }
}

async function startValidation() {
  const chapterId = fusionChapterId.value
  const draft = fusionDraft.value
  if (!chapterId || !draft) {
    message.error('请先生成融合稿')
    return
  }
  validationLoading.value = true
  try {
    const summary = await validationReportsApi.startValidation(chapterId, {
      draft_type: 'fusion',
      draft_id: draft.fusion_id,
      plan_version: draft.plan_version,
      state_lock_version: draft.state_lock_version,
    })
    validationReport.value = await validationReportsApi.getValidationReport(summary.report_id)
    message.success(summary.passed ? '校验已通过' : '校验完成，存在阻断问题')
    await loadLatestFusionJob()
  } catch (error) {
    const detail = getApiErrorMessage(error) || (error instanceof Error ? error.message : '')
    message.error(detail ? `启动校验失败：${detail}` : '启动校验失败')
  } finally {
    validationLoading.value = false
  }
}

async function updateIssueStatus(issue: ValidationIssueDTO, status: 'unresolved' | 'resolved' | 'ignored') {
  issueActionLoading.value = true
  try {
    const updated = await validationReportsApi.updateValidationIssue(issue.issue_id, status)
    for (const group of Object.values(validationReport.value?.issues_by_severity ?? {})) {
      const items = group as ValidationIssueDTO[]
      const index = items.findIndex(item => item.issue_id === updated.issue_id)
      if (index >= 0) {
        items[index] = updated
      }
    }
    message.success('问题状态已更新')
    await loadLatestValidationReport()
  } catch (error) {
    const detail = getApiErrorMessage(error) || (error instanceof Error ? error.message : '')
    message.error(detail ? `更新问题状态失败：${detail}` : '更新问题状态失败')
  } finally {
    issueActionLoading.value = false
  }
}

async function requestRepairPatch(issue: ValidationIssueDTO) {
  issueActionLoading.value = true
  try {
    const patch = await validationReportsApi.buildRepairPatch(issue.issue_id)
    repairPatchByIssueId.value = {
      ...repairPatchByIssueId.value,
      [issue.issue_id]: patch.patch_text,
    }
    message.success(patch.source === 'llm' ? '已生成修复建议' : '已生成启发式修复建议')
  } catch (error) {
    const detail = getApiErrorMessage(error) || (error instanceof Error ? error.message : '')
    message.error(detail ? `生成修复建议失败：${detail}` : '生成修复建议失败')
  } finally {
    issueActionLoading.value = false
  }
}

function openValidationCenter() {
  router.push(`/book/${props.slug}/validation-center`)
}

function lockStatusTagType(status: string): 'success' | 'warning' | 'error' | 'info' | 'default' {
  if (status === 'violated') return 'error'
  if (status === 'manually_modified') return 'warning'
  return 'success'
}

function formatLockValue(value: unknown): string {
  if (Array.isArray(value)) return value.join('、')
  if (value && typeof value === 'object') return JSON.stringify(value)
  return String(value ?? '—')
}

function jumpToLockGroup(groupKey: string) {
  if (!groupKey) return
  activeLockGroup.value = groupKey
  document.getElementById(`state-lock-group-${groupKey}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  window.setTimeout(() => {
    if (activeLockGroup.value === groupKey) activeLockGroup.value = ''
  }, 2200)
}

async function loadStateLocks() {
  stateLocks.value = null
  const chapterId = fusionChapterId.value
  if (!chapterId) return
  try {
    stateLocks.value = await stateLocksApi.getCurrentStateLocks(chapterId)
  } catch {
    stateLocks.value = null
  }
}

async function generateStateLocks() {
  const chapterId = fusionChapterId.value
  if (!chapterId) return
  stateLocksLoading.value = true
  try {
    const planVersion = Number((chapterPlan.value?.metadata as Record<string, unknown> | undefined)?.version ?? 1)
    stateLocks.value = await stateLocksApi.generateStateLocks(chapterId, planVersion)
    message.success('状态锁已生成')
  } catch (error) {
    const detail = getApiErrorMessage(error) || (error instanceof Error ? error.message : '')
    message.error(detail ? `生成状态锁失败：${detail}` : '生成状态锁失败')
  } finally {
    stateLocksLoading.value = false
  }
}

function openStateLockEditor() {
  if (!stateLocks.value) return
  stateLockEditorJson.value = JSON.stringify({
    time_lock: stateLocks.value.time_lock,
    location_lock: stateLocks.value.location_lock,
    character_lock: stateLocks.value.character_lock,
    item_lock: stateLocks.value.item_lock,
    numeric_lock: stateLocks.value.numeric_lock,
    event_lock: stateLocks.value.event_lock,
    ending_lock: stateLocks.value.ending_lock,
  }, null, 2)
  stateLockChangeReason.value = ''
  stateLockEditorVisible.value = true
}

async function saveStateLockEdit() {
  if (!stateLocks.value) return
  let parsed: Omit<StateLockSnapshotDTO, 'state_lock_id' | 'chapter_id' | 'version' | 'plan_version' | 'source' | 'change_reason' | 'changed_fields' | 'inference_notes' | 'critical_change'> | null = null
  try {
    parsed = JSON.parse(stateLockEditorJson.value)
  } catch {
    message.error('状态锁 JSON 格式无效')
    return
  }
  if (!stateLockChangeReason.value.trim()) {
    message.error('请填写修改原因')
    return
  }
  stateLocksLoading.value = true
  try {
    stateLocks.value = await stateLocksApi.updateStateLocks(stateLocks.value.state_lock_id, {
      change_reason: stateLockChangeReason.value.trim(),
      time_lock: parsed?.time_lock ?? { entries: [] },
      location_lock: parsed?.location_lock ?? { entries: [] },
      character_lock: parsed?.character_lock ?? { entries: [] },
      item_lock: parsed?.item_lock ?? { entries: [] },
      numeric_lock: parsed?.numeric_lock ?? { entries: [] },
      event_lock: parsed?.event_lock ?? { entries: [] },
      ending_lock: parsed?.ending_lock ?? { entries: [] },
    })
    stateLockEditorVisible.value = false
    message.success('状态锁已保存为新版本')
  } catch (error) {
    const detail = getApiErrorMessage(error) || (error instanceof Error ? error.message : '')
    message.error(detail ? `保存状态锁失败：${detail}` : '保存状态锁失败')
  } finally {
    stateLocksLoading.value = false
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

function getApiErrorMessage(error: unknown): string {
  if (typeof error !== 'object' || error === null) return ''
  const response = (error as { response?: { data?: unknown } }).response
  const data = response?.data
  if (typeof data === 'string') return data
  if (typeof data === 'object' && data !== null) {
    const detail = (data as { detail?: unknown }).detail
    if (typeof detail === 'string' && detail.trim()) return detail
    const message = (data as { message?: unknown }).message
    if (typeof message === 'string' && message.trim()) return message
  }
  return ''
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

async function refreshChapterData() {
  await resolveStoryNode()
  await Promise.all([
    loadKnowledgeChapter(),
    loadBeatSheet(),
    loadStateLocks(),
  ])
  await loadLatestValidationReport()
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
    beatSheet.value = null
    await Promise.all([
      loadBible(),
      refreshChapterData()
    ])
  }
})

watch(() => props.currentChapterNumber, async () => {
  await refreshChapterData()
  await loadLatestFusionJob()
}, { immediate: false })

const refreshStore = useWorkbenchRefreshStore()
const { deskTick } = storeToRefs(refreshStore)
watch(deskTick, async () => {
  await refreshChapterData()
  await loadLatestFusionJob()
})

onMounted(async () => {
  await loadBible()
  await refreshChapterData()
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

.validation-card {
  border-color: rgba(239, 68, 68, 0.16);
  background: linear-gradient(180deg, rgba(239, 68, 68, 0.03) 0%, rgba(251, 191, 36, 0.02) 100%);
}

.state-lock-card {
  border-color: rgba(249, 115, 22, 0.18);
  background: linear-gradient(180deg, rgba(249, 115, 22, 0.035) 0%, rgba(245, 158, 11, 0.02) 100%);
}

.state-lock-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
  scroll-margin-top: 24px;
}

.state-lock-group-active {
  padding: 8px;
  border-radius: 12px;
  background: rgba(245, 158, 11, 0.08);
  box-shadow: 0 0 0 1px rgba(245, 158, 11, 0.24);
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
