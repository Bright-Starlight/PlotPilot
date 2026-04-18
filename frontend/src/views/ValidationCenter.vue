<template>
  <div class="validation-center">
    <header class="validation-header">
      <n-space align="center" :wrap="false">
        <n-button quaternary round @click="goBack">← 工作台</n-button>
        <n-divider vertical />
        <h2 class="validation-title">Validation Center</h2>
      </n-space>
      <n-space :size="8">
        <n-select
          v-model:value="chapterFilter"
          clearable
          filterable
          placeholder="全部章节"
          :options="chapterOptions"
          style="width: 180px"
        />
        <n-select
          v-model:value="severityFilter"
          clearable
          placeholder="全部严重级别"
          :options="severityOptions"
          style="width: 150px"
        />
        <n-select
          v-model:value="statusFilter"
          clearable
          placeholder="全部处理状态"
          :options="statusOptions"
          style="width: 160px"
        />
        <n-button secondary :loading="loading" @click="loadIssues">刷新</n-button>
      </n-space>
    </header>

    <div class="validation-body">
      <n-alert v-if="errorMessage" type="warning" :show-icon="true" class="validation-alert">
        {{ errorMessage }}
      </n-alert>

      <n-card v-if="latestReport" size="small" :bordered="true">
        <template #header>
          <n-space align="center" justify="space-between" style="width: 100%">
            <span>最新校验报告</span>
            <n-text depth="3">{{ chapterLabel(latestReport.chapter_id) }}</n-text>
          </n-space>
        </template>
        <n-space :size="8" wrap>
          <n-tag size="small" round :type="latestReport.passed ? 'success' : 'error'">
            {{ latestReport.passed ? '校验通过' : '存在阻断问题' }}
          </n-tag>
          <n-tag size="small" round>报告 {{ latestReport.report_id }}</n-tag>
          <n-tag size="small" round>草稿 {{ latestReport.draft_id }}</n-tag>
          <n-tag size="small" round>类型 {{ latestReport.draft_type }}</n-tag>
          <n-tag size="small" round>State Lock v{{ latestReport.state_lock_version }}</n-tag>
          <n-tag size="small" round>P0 {{ latestReport.p0_count }}</n-tag>
          <n-tag size="small" round>P1 {{ latestReport.p1_count }}</n-tag>
          <n-tag size="small" round>P2 {{ latestReport.p2_count }}</n-tag>
          <n-tag size="small" round>Token {{ latestReport.token_usage.total_tokens }}</n-tag>
        </n-space>
      </n-card>

      <n-card size="small" :bordered="true">
        <template #header>
          <n-space align="center" justify="space-between" style="width: 100%">
            <span>问题列表</span>
            <n-text depth="3">{{ issues.length }} 条</n-text>
          </n-space>
        </template>

        <n-empty v-if="!loading && !issues.length" description="没有匹配的问题" />

        <n-list v-else hoverable bordered>
          <n-list-item v-for="issue in issues" :key="issue.issue_id">
            <n-space vertical :size="8" style="width: 100%">
              <n-space align="center" justify="space-between">
                <n-space :size="8" align="center">
                  <n-tag size="small" :type="issue.severity === 'P0' ? 'error' : issue.severity === 'P1' ? 'warning' : 'default'" round>
                    {{ issue.severity }}
                  </n-tag>
                  <n-tag size="small" :type="issue.blocking ? 'error' : 'info'" round>
                    {{ issue.blocking ? 'blocking' : 'advisory' }}
                  </n-tag>
                  <n-text strong>{{ issue.title }}</n-text>
                </n-space>
                <n-space :size="6">
                  <n-tag size="small" round>{{ chapterLabel(issue.chapter_id) }}</n-tag>
                  <n-tag size="small" round>{{ issue.status }}</n-tag>
                </n-space>
              </n-space>

              <n-text depth="3" style="white-space: pre-wrap; font-size: 12px">{{ issue.message }}</n-text>
              <n-text v-if="issue.spans.length" depth="3" style="font-size: 12px">
                段落 {{ issue.spans[0].paragraph_index + 1 }}：{{ issue.spans[0].excerpt }}
              </n-text>

              <n-space :size="6" wrap>
                <n-button
                  size="tiny"
                  tertiary
                  @click="openChapter(issue.chapter_id)"
                >
                  打开章节
                </n-button>
                <n-button
                  v-if="issue.suggest_patch"
                  size="tiny"
                  secondary
                  :loading="actionLoading"
                  @click="generatePatch(issue.issue_id)"
                >
                  修复建议
                </n-button>
                <n-button
                  size="tiny"
                  tertiary
                  :loading="actionLoading"
                  @click="changeStatus(issue.issue_id, 'resolved')"
                >
                  标记已解决
                </n-button>
                <n-button
                  v-if="issue.severity !== 'P0'"
                  size="tiny"
                  tertiary
                  :loading="actionLoading"
                  @click="changeStatus(issue.issue_id, 'ignored')"
                >
                  忽略
                </n-button>
                <n-button
                  v-if="issue.status !== 'unresolved'"
                  size="tiny"
                  tertiary
                  :loading="actionLoading"
                  @click="changeStatus(issue.issue_id, 'unresolved')"
                >
                  设为未处理
                </n-button>
              </n-space>

              <n-alert v-if="repairPatchByIssueId[issue.issue_id]" type="info" :show-icon="false" size="small">
                {{ repairPatchByIssueId[issue.issue_id] }}
              </n-alert>
            </n-space>
          </n-list-item>
        </n-list>
      </n-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { chapterApi } from '../api/chapter'
import { validationReportsApi, type ValidationIssueDTO, type ValidationReportDetailDTO } from '../api/validationReports'

const route = useRoute()
const router = useRouter()
const message = useMessage()

const slug = route.params.slug as string
const loading = ref(false)
const actionLoading = ref(false)
const errorMessage = ref('')
const latestReport = ref<ValidationReportDetailDTO | null>(null)
const issues = ref<ValidationIssueDTO[]>([])
const chapters = ref<Array<{ id: string; number: number; title: string }>>([])
const chapterFilter = ref<string | null>(null)
const severityFilter = ref<string | null>(null)
const statusFilter = ref<string | null>(null)
const repairPatchByIssueId = ref<Record<string, string>>({})

const severityOptions = [
  { label: 'P0', value: 'P0' },
  { label: 'P1', value: 'P1' },
  { label: 'P2', value: 'P2' },
]
const statusOptions = [
  { label: '未处理', value: 'unresolved' },
  { label: '已解决', value: 'resolved' },
  { label: '已忽略', value: 'ignored' },
]

const chapterOptions = computed(() =>
  chapters.value.map(ch => ({
    label: `第 ${ch.number} 章${ch.title ? ` · ${ch.title}` : ''}`,
    value: ch.id,
  }))
)

function chapterLabel(chapterId: string): string {
  const chapter = chapters.value.find(item => item.id === chapterId)
  return chapter ? `第 ${chapter.number} 章` : chapterId
}

function goBack() {
  router.push(`/book/${slug}/workbench`)
}

function parseQueryValue(value: unknown): string | null {
  if (value == null || value === '') return null
  const raw = Array.isArray(value) ? value[0] : value
  return typeof raw === 'string' && raw.trim() ? raw.trim() : null
}

function openChapter(chapterId: string) {
  const chapter = chapters.value.find(item => item.id === chapterId)
  if (!chapter) return
  router.push(`/book/${slug}/chapter/${chapter.number}`)
}

async function loadChapters() {
  const rows = await chapterApi.listChapters(slug)
  chapters.value = rows.map(item => ({
    id: item.id,
    number: item.number,
    title: item.title,
  }))
}

async function loadIssues() {
  loading.value = true
  errorMessage.value = ''
  try {
    issues.value = await validationReportsApi.listValidationIssues({
      novelId: slug,
      chapterId: chapterFilter.value || undefined,
      severity: severityFilter.value || undefined,
      status: statusFilter.value || undefined,
    })
  } catch (error) {
    const detail = getApiErrorMessage(error) || (error instanceof Error ? error.message : '')
    errorMessage.value = detail || '加载校验问题失败'
    issues.value = []
  } finally {
    loading.value = false
  }
}

async function loadLatestReport(chapterId: string | null) {
  if (!chapterId) {
    latestReport.value = null
    return
  }

  try {
    latestReport.value = await validationReportsApi.getLatestValidationReport(chapterId, { draftType: 'fusion' })
  } catch {
    latestReport.value = null
  }
}

async function syncChapterFromRoute() {
  const chapterId = parseQueryValue(route.query.chapter_id)
  if (chapterId) {
    chapterFilter.value = chapterId
    await loadLatestReport(chapterId)
    return
  }
  latestReport.value = null
}

async function changeStatus(issueId: string, status: 'unresolved' | 'resolved' | 'ignored') {
  actionLoading.value = true
  try {
    await validationReportsApi.updateValidationIssue(issueId, status)
    message.success('问题状态已更新')
    await loadIssues()
  } catch (error) {
    const detail = getApiErrorMessage(error) || (error instanceof Error ? error.message : '')
    message.error(detail || '更新问题状态失败')
  } finally {
    actionLoading.value = false
  }
}

async function generatePatch(issueId: string) {
  actionLoading.value = true
  try {
    const patch = await validationReportsApi.buildRepairPatch(issueId)
    repairPatchByIssueId.value = {
      ...repairPatchByIssueId.value,
      [issueId]: patch.patch_text,
    }
    message.success('已生成修复建议')
  } catch (error) {
    const detail = getApiErrorMessage(error) || (error instanceof Error ? error.message : '')
    message.error(detail || '生成修复建议失败')
  } finally {
    actionLoading.value = false
  }
}

function getApiErrorMessage(error: unknown): string {
  if (typeof error !== 'object' || error === null) return ''
  const response = (error as { response?: { data?: unknown } }).response
  const data = response?.data
  if (typeof data === 'string') return data
  if (typeof data === 'object' && data !== null) {
    const detail = (data as { detail?: unknown }).detail
    if (typeof detail === 'string') return detail
    const message = (data as { message?: unknown }).message
    if (typeof message === 'string') return message
  }
  return ''
}

watch([chapterFilter, severityFilter, statusFilter], () => {
  void loadIssues()
})

watch(
  () => route.query.chapter_id,
  () => {
    void syncChapterFromRoute()
  }
)

onMounted(async () => {
  await loadChapters()
  await syncChapterFromRoute()
  await loadIssues()
})
</script>

<style scoped>
.validation-center {
  min-height: 100vh;
  background: var(--app-page-bg, #f0f2f8);
  padding: 16px 18px 24px;
}

.validation-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.validation-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.validation-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.validation-alert {
  max-width: 720px;
}
</style>
