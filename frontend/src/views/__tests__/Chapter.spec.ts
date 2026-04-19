import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Chapter from '@/views/Chapter.vue'

const mocks = vi.hoisted(() => ({
  listChapters: vi.fn(),
  getChapter: vi.fn(),
  getChapterReview: vi.fn(),
  getChapterStructure: vi.fn(),
  saveChapterReview: vi.fn(),
  reviewChapterAi: vi.fn(),
  updateChapter: vi.fn(),
  getChapterInferenceEvidence: vi.fn(),
  revokeInferredTriple: vi.fn(),
  revokeChapterInference: vi.fn(),
  message: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
  dialog: {
    warning: vi.fn(),
    error: vi.fn(),
  },
  routerPush: vi.fn(),
  statsOnChapterSaved: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({
    params: { slug: 'novel-1', id: '1' },
    name: 'Chapter',
  }),
  useRouter: () => ({
    push: mocks.routerPush,
  }),
}))

vi.mock('naive-ui', async () => ({
  useMessage: () => mocks.message,
  useDialog: () => mocks.dialog,
}))

vi.mock('@/api/chapter', () => ({
  chapterApi: {
    listChapters: mocks.listChapters,
    getChapter: mocks.getChapter,
    getChapterReview: mocks.getChapterReview,
    getChapterStructure: mocks.getChapterStructure,
    saveChapterReview: mocks.saveChapterReview,
    reviewChapterAi: mocks.reviewChapterAi,
    updateChapter: mocks.updateChapter,
  },
}))

vi.mock('@/api/validationReports', () => ({
  validationReportsApi: {},
}))

vi.mock('@/api/knowledgeGraph', () => ({
  knowledgeGraphApi: {
    getChapterInferenceEvidence: mocks.getChapterInferenceEvidence,
    revokeInferredTriple: mocks.revokeInferredTriple,
    revokeChapterInference: mocks.revokeChapterInference,
  },
}))

vi.mock('@/stores/statsStore', () => ({
  useStatsStore: () => ({
    onChapterSaved: mocks.statsOnChapterSaved,
  }),
}))

vi.mock('marked', () => ({
  marked: {
    parse: vi.fn((value: string) => `<p>${value}</p>`),
  },
}))

vi.mock('dompurify', () => ({
  default: {
    sanitize: vi.fn((value: string) => value),
  },
}))

function mountView() {
  return mount(Chapter)
}

describe('Chapter review and save actions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.listChapters.mockResolvedValue([{ id: 'chapter-1', number: 1, title: '第一章' }])
    mocks.getChapter.mockResolvedValue({
      id: 'chapter-1',
      novel_id: 'novel-1',
      number: 1,
      title: '第一章',
      content: '正文',
      word_count: 2,
      status: 'draft',
      created_at: '2026-04-18T00:00:00',
      updated_at: '2026-04-18T00:00:00',
    })
    mocks.getChapterReview.mockResolvedValue({
      status: 'draft',
      memo: '',
      created_at: '2026-04-18T00:00:00',
      updated_at: '2026-04-18T00:00:00',
    })
    mocks.getChapterStructure.mockResolvedValue({
      word_count: 2,
      paragraph_count: 1,
      dialogue_ratio: 0,
      scene_count: 1,
      pacing: 'medium',
    })
    mocks.getChapterInferenceEvidence.mockResolvedValue({
      data: {
        story_node_id: null,
        facts: [],
        hint: '',
      },
    })
    mocks.updateChapter.mockResolvedValue({
      id: 'chapter-1',
      novel_id: 'novel-1',
      number: 1,
      title: '第一章',
      content: '正文',
      word_count: 2,
      status: 'draft',
      aftermath: {
        narrative_sync_ok: true,
        voice_sync_ok: true,
        kg_sync_ok: true,
        local_sync_ok: true,
        local_sync_errors: [],
        drift_alert: false,
        similarity_score: null,
      },
    })
    mocks.saveChapterReview.mockResolvedValue({
      status: 'approved',
      memo: '',
      created_at: '2026-04-18T00:00:00',
      updated_at: '2026-04-18T00:00:00',
    })
  })

  it('saves approved review without triggering publish gate logic', async () => {
    const wrapper = mountView()
    await flushPromises()

    ;(wrapper.vm as unknown as { reviewStatus: string }).reviewStatus = 'ok'
    await (wrapper.vm as unknown as { saveReview: () => Promise<void> }).saveReview()

    expect(mocks.saveChapterReview).toHaveBeenCalledWith('novel-1', 1, 'approved', '')
    expect(mocks.dialog.warning).not.toHaveBeenCalled()
  })

  it('shows a hint when saving content without any正文改动', async () => {
    const wrapper = mountView()
    await flushPromises()

    await (wrapper.vm as unknown as { saveContent: () => Promise<void> }).saveContent()

    expect(mocks.message.info).toHaveBeenCalledWith('正文没有改动')
    expect(mocks.updateChapter).not.toHaveBeenCalled()
  })

  it('saves content directly and reports local sync status', async () => {
    const wrapper = mountView()
    await flushPromises()
    ;(wrapper.vm as unknown as { content: string }).content = '融合稿正文'
    ;(wrapper.vm as unknown as { saveStatus: string }).saveStatus = 'unsaved'

    await (wrapper.vm as unknown as { saveContent: () => Promise<void> }).saveContent()

    expect(mocks.updateChapter).toHaveBeenCalledWith('novel-1', 1, { content: '融合稿正文' })
    expect(mocks.message.success).toHaveBeenCalledWith('正文已保存，本地同步完成')
  })
})
