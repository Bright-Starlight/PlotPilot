import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ValidationCenter from '@/views/ValidationCenter.vue'

const mocks = vi.hoisted(() => ({
  listChapters: vi.fn(),
  listValidationIssues: vi.fn(),
  getLatestValidationReport: vi.fn(),
  updateValidationIssue: vi.fn(),
  buildRepairPatch: vi.fn(),
  routerPush: vi.fn(),
  message: {
    success: vi.fn(),
    error: vi.fn(),
  },
  dialog: {
    warning: vi.fn(),
  },
}))

const routeState = vi.hoisted(() => ({
  query: {} as Record<string, string>,
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({
    params: { slug: 'novel-1' },
    query: routeState.query,
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
  },
}))

vi.mock('@/api/validationReports', () => ({
  validationReportsApi: {
    listValidationIssues: mocks.listValidationIssues,
    getLatestValidationReport: mocks.getLatestValidationReport,
    updateValidationIssue: mocks.updateValidationIssue,
    buildRepairPatch: mocks.buildRepairPatch,
  },
}))

function mountView() {
  return mount(ValidationCenter)
}

describe('ValidationCenter', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.listChapters.mockResolvedValue([
      { id: 'chapter-1', number: 1, title: '第一章' },
      { id: 'chapter-2', number: 2, title: '第二章' },
    ])
    mocks.listValidationIssues.mockResolvedValue([
      {
        issue_id: 'vi-1',
        report_id: 'vr-1',
        chapter_id: 'chapter-1',
        severity: 'P0',
        code: 'ending_lock_violation',
        title: '违反终态锁',
        message: '终态落点错误',
        spans: [{ paragraph_index: 0, start_offset: 0, end_offset: 4, excerpt: '终态落点错误' }],
        blocking: true,
        suggest_patch: true,
        status: 'unresolved',
        metadata: {},
      },
    ])
    mocks.getLatestValidationReport.mockResolvedValue({
      report_id: 'vr-latest',
      chapter_id: 'chapter-1',
      draft_type: 'fusion',
      draft_id: 'fd-latest',
      plan_version: 1,
      state_lock_version: 29,
      status: 'finished',
      passed: true,
      blocking_issue_count: 0,
      p0_count: 0,
      p1_count: 0,
      p2_count: 0,
      token_usage: { input_tokens: 10, output_tokens: 20, total_tokens: 30 },
      issues_by_severity: {},
    })
    mocks.updateValidationIssue.mockResolvedValue({
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
      status: 'resolved',
      metadata: {},
    })
    mocks.buildRepairPatch.mockResolvedValue({
      issue_id: 'vi-1',
      patch_text: '建议重写章末，使人物回到钱府。',
      source: 'heuristic',
    })
  })

  it('loads issues with route slug and applies filters', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(mocks.listValidationIssues).toHaveBeenCalledWith({
      novelId: 'novel-1',
      chapterId: undefined,
      severity: undefined,
      status: undefined,
    })

    ;(wrapper.vm as unknown as { chapterFilter: string | null }).chapterFilter = 'chapter-1'
    ;(wrapper.vm as unknown as { severityFilter: string | null }).severityFilter = 'P0'
    ;(wrapper.vm as unknown as { statusFilter: string | null }).statusFilter = 'unresolved'
    await flushPromises()

    expect(mocks.listValidationIssues).toHaveBeenLastCalledWith({
      novelId: 'novel-1',
      chapterId: 'chapter-1',
      severity: 'P0',
      status: 'unresolved',
    })
    expect(wrapper.text()).toContain('违反终态锁')
  })

  it('loads the latest report when chapter_id is present in the route', async () => {
    routeState.query.chapter_id = 'chapter-1'
    const wrapper = mountView()
    await flushPromises()
    routeState.query = {}

    expect(mocks.getLatestValidationReport).toHaveBeenCalledWith('chapter-1', { draftType: 'fusion' })
    expect(wrapper.text()).toContain('vr-latest')
    expect(wrapper.text()).toContain('草稿 fd-latest')
    expect(wrapper.text()).toContain('第 1 章')
  })

  it('supports issue actions and chapter navigation', async () => {
    routeState.query.chapter_id = 'chapter-1'
    const wrapper = mountView()
    await flushPromises()
    routeState.query = {}

    await (wrapper.vm as unknown as { openChapter: (chapterId: string) => void }).openChapter('chapter-1')
    expect(mocks.routerPush).toHaveBeenCalledWith('/book/novel-1/chapter/1')

    await (wrapper.vm as unknown as { changeStatus: (issueId: string, status: 'resolved') => Promise<void> }).changeStatus('vi-1', 'resolved')
    expect(mocks.updateValidationIssue).toHaveBeenCalledWith('vi-1', 'resolved')
    expect(mocks.getLatestValidationReport).toHaveBeenCalledWith('chapter-1', { draftType: 'fusion' })

    await (wrapper.vm as unknown as { generatePatch: (issueId: string) => Promise<void> }).generatePatch('vi-1')
    await flushPromises()
    expect(mocks.buildRepairPatch).toHaveBeenCalledWith('vi-1')
    expect(wrapper.text()).toContain('建议重写章末，使人物回到钱府。')
  })
})
