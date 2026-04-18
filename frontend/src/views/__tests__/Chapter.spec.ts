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
  checkPublishable: vi.fn(),
  getChapterInferenceEvidence: vi.fn(),
  revokeInferredTriple: vi.fn(),
  revokeChapterInference: vi.fn(),
  message: {
    success: vi.fn(),
    error: vi.fn(),
  },
  warningOptions: null as Record<string, unknown> | null,
  errorOptions: null as Record<string, unknown> | null,
  dialog: {
    warning: vi.fn((options: Record<string, unknown>) => {
      mocks.warningOptions = options
      return {}
    }),
    error: vi.fn((options: Record<string, unknown>) => {
      mocks.errorOptions = options
      return {}
    }),
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
  validationReportsApi: {
    checkPublishable: mocks.checkPublishable,
  },
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

describe('Chapter publish gate', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.warningOptions = null
    mocks.errorOptions = null
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
    mocks.saveChapterReview.mockResolvedValue({
      status: 'approved',
      memo: '',
      created_at: '2026-04-18T00:00:00',
      updated_at: '2026-04-18T00:00:00',
    })
  })

  it('blocks publish and shows dialog when publish gate fails', async () => {
    mocks.checkPublishable.mockResolvedValue({
      publishable: false,
      report_id: 'vr-1',
      chapter_id: 'chapter-1',
      draft_type: 'fusion',
      draft_id: 'fusion-1',
      plan_version: 3,
      state_lock_version: 5,
      status: 'completed',
      passed: false,
      blocking_issue_count: 1,
      p0_count: 1,
      p1_count: 0,
      p2_count: 0,
      token_usage: { input_tokens: 0, output_tokens: 0, total_tokens: 0 },
      issues_by_severity: { P0: [], P1: [], P2: [] },
      blocking_issues: [
        {
          issue_id: 'vi-1',
          report_id: 'vr-1',
          chapter_id: 'chapter-1',
          severity: 'P0',
          code: 'ending_lock_violation',
          title: '违反终态锁',
          message: '终态落点错误',
          spans: [],
          blocking: true,
          suggest_patch: true,
          status: 'unresolved',
          metadata: {},
        },
      ],
    })

    const wrapper = mountView()
    await flushPromises()

    ;(wrapper.vm as unknown as { reviewStatus: string }).reviewStatus = 'ok'
    await (wrapper.vm as unknown as { saveReview: () => Promise<void> }).saveReview()

    expect(mocks.dialog.warning).toHaveBeenCalled()
    const result = await (mocks.warningOptions?.onPositiveClick as (() => Promise<boolean>) | undefined)?.()
    expect(result).toBe(false)
    expect(mocks.checkPublishable).toHaveBeenCalledWith('chapter-1')
    expect(mocks.saveChapterReview).not.toHaveBeenCalled()
    expect(mocks.dialog.error).toHaveBeenCalled()
    expect(String(mocks.errorOptions?.title || '')).toContain('发布已阻断')
  })
})
