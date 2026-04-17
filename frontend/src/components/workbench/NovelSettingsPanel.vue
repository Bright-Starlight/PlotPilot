<template>
  <div class="novel-settings-panel">
    <n-spin :show="loading">
      <n-card :bordered="false" size="small" class="settings-card">
        <template #header>
          <div class="settings-header">
            <div>
              <h3 class="settings-title">小说设置</h3>
              <p class="settings-subtitle">统一维护书籍基础参数，手动生成与 Autopilot 共用同一套每章目标字数。</p>
            </div>
            <n-tag size="small" round type="info">Project Config</n-tag>
          </div>
        </template>

        <n-space vertical :size="16">
          <n-alert type="info" :show-icon="false">
            梗概锁定与文风公约继续在「作品设定」里维护；这里负责书名、章节目标和每章目标字数。
          </n-alert>

          <n-form label-placement="top">
            <n-grid :cols="2" :x-gap="12" :y-gap="8" responsive="screen">
              <n-gi>
                <n-form-item label="书名">
                  <n-input v-model:value="form.title" placeholder="小说标题" />
                </n-form-item>
              </n-gi>
              <n-gi>
                <n-form-item label="作者">
                  <n-input v-model:value="form.author" placeholder="作者名" />
                </n-form-item>
              </n-gi>
              <n-gi>
                <n-form-item label="目标章节数">
                  <n-input-number
                    v-model:value="form.target_chapters"
                    :min="1"
                    :max="9999"
                    :step="1"
                    style="width: 100%"
                  />
                </n-form-item>
              </n-gi>
              <n-gi>
                <n-form-item label="每章目标字数">
                  <n-input-number
                    v-model:value="form.target_words_per_chapter"
                    :min="100"
                    :max="20000"
                    :step="100"
                    style="width: 100%"
                  />
                </n-form-item>
              </n-gi>
            </n-grid>
          </n-form>

          <div class="settings-metrics">
            <div class="metric-item">
              <span class="metric-label">预计总字数</span>
              <strong class="metric-value">{{ estimatedTotalWords }}</strong>
            </div>
            <div class="metric-item">
              <span class="metric-label">当前章节目标区间</span>
              <strong class="metric-value">{{ targetRangeText }}</strong>
            </div>
          </div>

          <n-space justify="end">
            <n-button @click="loadNovel" :disabled="loading || saving">重载</n-button>
            <n-button type="primary" :loading="saving" :disabled="!isDirty" @click="saveSettings">
              保存设置
            </n-button>
          </n-space>
        </n-space>
      </n-card>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { novelApi } from '@/api/novel'

interface Props {
  slug: string
}

const props = defineProps<Props>()
const emit = defineEmits<{
  saved: []
}>()

const message = useMessage()
const loading = ref(false)
const saving = ref(false)
const snapshot = ref('')
const form = reactive({
  title: '',
  author: '',
  target_chapters: 100,
  target_words_per_chapter: 3500,
})

const estimatedTotalWords = computed(() => {
  const total = Number(form.target_chapters || 0) * Number(form.target_words_per_chapter || 0)
  return `${total.toLocaleString()} 字`
})

const targetRangeText = computed(() => {
  const target = Number(form.target_words_per_chapter || 0)
  return `${Math.round(target * 0.85).toLocaleString()} - ${Math.round(target * 1.15).toLocaleString()}`
})

const isDirty = computed(() => snapshot.value !== JSON.stringify(form))

async function loadNovel() {
  loading.value = true
  try {
    const novel = await novelApi.getNovel(props.slug)
    form.title = novel.title || ''
    form.author = novel.author || ''
    form.target_chapters = novel.target_chapters || 100
    form.target_words_per_chapter = novel.target_words_per_chapter || 3500
    snapshot.value = JSON.stringify(form)
  } catch (error) {
    console.error('load novel settings failed', error)
    message.error('加载小说设置失败')
  } finally {
    loading.value = false
  }
}

async function saveSettings() {
  saving.value = true
  try {
    await novelApi.updateNovel(props.slug, {
      title: form.title.trim(),
      author: form.author.trim(),
      target_chapters: Number(form.target_chapters || 0),
      target_words_per_chapter: Number(form.target_words_per_chapter || 0),
    })
    snapshot.value = JSON.stringify(form)
    message.success('小说设置已保存')
    emit('saved')
  } catch (error) {
    console.error('save novel settings failed', error)
    message.error('保存小说设置失败')
  } finally {
    saving.value = false
  }
}

watch(() => props.slug, () => {
  void loadNovel()
})

onMounted(() => {
  void loadNovel()
})
</script>

<style scoped>
.novel-settings-panel {
  height: 100%;
  overflow: auto;
  padding: 14px;
  background: var(--app-surface-subtle);
}

.settings-card {
  border-radius: 16px;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
}

.settings-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.settings-title {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
}

.settings-subtitle {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--app-text-secondary);
}

.settings-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.metric-item {
  padding: 14px;
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(14, 165, 233, 0.08), rgba(250, 204, 21, 0.12));
  border: 1px solid var(--app-border);
}

.metric-label {
  display: block;
  font-size: 12px;
  color: var(--app-text-secondary);
  margin-bottom: 6px;
}

.metric-value {
  font-size: 18px;
  font-weight: 700;
  color: var(--app-text-primary);
}

@media (max-width: 768px) {
  .settings-metrics {
    grid-template-columns: 1fr;
  }
}
</style>
