import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterAll, beforeEach, describe, expect, it, vi } from 'vitest'
import ChapterContentPanel from '@/components/workbench/ChapterContentPanel.vue'

const mocks = vi.hoisted(() => ({
  message: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  },
  planningGetStructure: vi.fn(),
  knowledgeGetKnowledge: vi.fn(),
  bibleGetBible: vi.fn(),
  getBeatSheet: vi.fn(),
  generateBeatSheet: vi.fn(),
  getCurrentStateLocks: vi.fn(),
  generateStateLocks: vi.fn(),
  updateStateLocks: vi.fn(),
  createFusionJob: vi.fn(),
  getLatestFusionJob: vi.fn(),
  getFusionJob: vi.fn(),
  startValidation: vi.fn(),
  getValidationReport: vi.fn(),
  getLatestValidationReport: vi.fn(),
  listValidationIssues: vi.fn(),
  updateValidationIssue: vi.fn(),
  buildRepairPatch: vi.fn(),
  routerPush: vi.fn(),
}))

const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

vi.mock('naive-ui', async () => {
  return {
    useMessage: () => mocks.message,
  }
})

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: mocks.routerPush,
  }),
}))

vi.mock('@/stores/workbenchRefreshStore', () => ({
  useWorkbenchRefreshStore: () => ({}),
}))

vi.mock('pinia', async () => {
  const { ref } = await import('vue')
  return {
    storeToRefs: () => ({
      deskTick: ref(0),
    }),
  }
})

vi.mock('@/api/planning', () => ({
  planningApi: {
    getStructure: mocks.planningGetStructure,
  },
}))

vi.mock('@/api/knowledge', () => ({
  knowledgeApi: {
    getKnowledge: mocks.knowledgeGetKnowledge,
  },
}))

vi.mock('@/api/bible', () => ({
  bibleApi: {
    getBible: mocks.bibleGetBible,
  },
}))

vi.mock('@/api/beatSheet', () => ({
  beatSheetApi: {
    getBeatSheet: mocks.getBeatSheet,
    generateBeatSheet: mocks.generateBeatSheet,
    deleteBeatSheet: vi.fn(),
  },
}))

vi.mock('@/api/chapterFusion', () => ({
  chapterFusionApi: {
    createFusionJob: mocks.createFusionJob,
    getLatestFusionJob: mocks.getLatestFusionJob,
    getFusionJob: mocks.getFusionJob,
  },
}))

vi.mock('@/api/stateLocks', () => ({
  stateLocksApi: {
    getCurrentStateLocks: mocks.getCurrentStateLocks,
    generateStateLocks: mocks.generateStateLocks,
    updateStateLocks: mocks.updateStateLocks,
  },
}))

vi.mock('@/api/validationReports', () => ({
  validationReportsApi: {
    startValidation: mocks.startValidation,
    getValidationReport: mocks.getValidationReport,
    getLatestValidationReport: mocks.getLatestValidationReport,
    listValidationIssues: mocks.listValidationIssues,
    updateValidationIssue: mocks.updateValidationIssue,
    buildRepairPatch: mocks.buildRepairPatch,
  },
}))

const baseStructure = {
  success: true,
  data: {
    novel_id: 'novel-1',
    nodes: [
      {
        id: 'chapter-1',
        node_type: 'chapter',
        title: '第 1 章',
        number: 1,
        outline: '重复句\n重复句\n收束',
        pov_character_id: 'char-1',
        timeline_end: '夜幕',
        metadata: {
          mood: '紧张',
          version: 3,
          state_lock_version: 5,
        },
      },
    ],
  },
}

const baseBeatSheet = {
  id: 'beat-sheet-1',
  chapter_id: 'chapter-1',
  scenes: [
    {
      title: '重复句',
      goal: '重复句',
      pov_character: '主角',
      location: '庭院',
      tone: '紧张',
      estimated_words: 800,
      order_index: 0,
    },
    {
      title: '重复句',
      goal: '重复句',
      pov_character: '主角',
      location: '庭院',
      tone: '紧张',
      estimated_words: 800,
      order_index: 1,
    },
    {
      title: '收束',
      goal: '收束',
      pov_character: '主角',
      location: '内室',
      tone: '平静',
      estimated_words: 700,
      order_index: 2,
    },
  ],
  total_scenes: 3,
  total_estimated_words: 2300,
}

const baseKnowledge = {
  version: 1,
  premise_lock: '',
  facts: [],
  chapters: [
    {
      chapter_id: 1,
      summary: '本章摘要',
      key_events: '关键事件',
      open_threads: '',
      consistency_note: '一致',
      ending_state: '门已开启',
      ending_emotion: '紧张',
      carry_over_question: '',
      next_opening_hint: '',
      beat_sections: ['重复句', '重复句', '收束'],
      micro_beats: [
        { description: '感知现场', target_words: 240, focus: 'sensory' },
      ],
      sync_status: 'ok',
    },
  ],
}

const baseBible = {
  id: 'bible-1',
  novel_id: 'novel-1',
  characters: [
    {
      id: 'char-1',
      name: '主角',
      description: '描述',
      relationships: [],
    },
  ],
  world_settings: [],
  locations: [],
  timeline_notes: [],
  style_notes: [],
}

const baseStateLocks = {
  state_lock_id: 'sl-1',
  chapter_id: 'chapter-1',
  version: 5,
  plan_version: 3,
  source: 'generated',
  change_reason: '',
  changed_fields: [],
  inference_notes: [],
  critical_change: {},
  time_lock: { entries: [] },
  location_lock: { entries: [] },
  character_lock: { entries: [] },
  item_lock: { entries: [] },
  numeric_lock: { entries: [] },
  event_lock: { entries: [] },
  ending_lock: {
    entries: [
      {
        key: 'ending_target',
        label: '目标终态',
        value: '门已开启',
        source: 'generated',
        kind: 'ending_target',
        status: 'normal',
        metadata: {},
      },
    ],
  },
}

const baseValidationReport = {
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
  issues_by_severity: {
    P0: [
      {
        issue_id: 'vi-1',
        report_id: 'vr-1',
        chapter_id: 'chapter-1',
        severity: 'P0',
        code: 'ending_lock_violation',
        title: '违反终态锁',
        message: '终态落点应为钱府，实际为客栈',
        spans: [{ paragraph_index: 0, start_offset: 0, end_offset: 4, excerpt: '融合后的章节正文' }],
        blocking: true,
        suggest_patch: true,
        status: 'unresolved',
        metadata: { group: 'ending_lock' },
      },
    ],
    P1: [],
    P2: [],
  },
}

function mountPanel() {
  return mount(ChapterContentPanel, {
    props: {
      slug: 'novel-1',
      currentChapterNumber: 1,
    },
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
  mocks.planningGetStructure.mockResolvedValue(baseStructure)
  mocks.knowledgeGetKnowledge.mockResolvedValue(baseKnowledge)
  mocks.bibleGetBible.mockResolvedValue(baseBible)
  mocks.getBeatSheet.mockResolvedValue(baseBeatSheet)
  mocks.generateBeatSheet.mockResolvedValue(baseBeatSheet)
  mocks.getCurrentStateLocks.mockResolvedValue(baseStateLocks)
  mocks.generateStateLocks.mockResolvedValue(baseStateLocks)
  mocks.updateStateLocks.mockResolvedValue(baseStateLocks)
  mocks.createFusionJob.mockResolvedValue({
    fusion_job_id: 'job-1',
    chapter_id: 'chapter-1',
    status: 'queued',
    error_message: '',
    fusion_draft: null,
    preview: null,
  })
  mocks.getLatestFusionJob.mockResolvedValue({
    fusion_job_id: 'job-1',
    chapter_id: 'chapter-1',
    status: 'completed',
    error_message: '',
    fusion_draft: {
      fusion_id: 'fusion-1',
      chapter_id: 'chapter-1',
      plan_version: 3,
      state_lock_version: 5,
      status: 'completed',
      text: '融合后的章节正文',
      estimated_repeat_ratio: 0.24,
      facts_confirmed: ['线索 A'],
      open_questions: ['谜团 B'],
      end_state: { scene: '终态' },
      warnings: ['重复功能偏高，建议检查开场桥接'],
      state_lock_violations: [],
      latest_validation_report_id: 'vr-1',
    },
    preview: {
      estimated_words: 1800,
      estimated_repeat_ratio: 0.24,
      expected_end_state: { scene: '终态' },
      expected_suspense_count: 2,
      risk_warnings: ['重复功能偏高，建议检查开场桥接'],
    },
  })
  mocks.getFusionJob.mockResolvedValue({
    fusion_job_id: 'job-1',
    chapter_id: 'chapter-1',
    status: 'completed',
    error_message: '',
    fusion_draft: {
      fusion_id: 'fusion-1',
      chapter_id: 'chapter-1',
      plan_version: 3,
      state_lock_version: 5,
      status: 'completed',
      text: '融合后的章节正文',
      estimated_repeat_ratio: 0.24,
      facts_confirmed: ['线索 A'],
      open_questions: ['谜团 B'],
      end_state: { scene: '终态' },
      warnings: ['重复功能偏高，建议检查开场桥接'],
      state_lock_violations: [],
      latest_validation_report_id: 'vr-1',
    },
    preview: {
      estimated_words: 1800,
      estimated_repeat_ratio: 0.24,
      expected_end_state: { scene: '终态' },
      expected_suspense_count: 2,
      risk_warnings: ['重复功能偏高，建议检查开场桥接'],
    },
  })
  mocks.startValidation.mockResolvedValue({
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
  })
  mocks.getValidationReport.mockResolvedValue({
    ...baseValidationReport,
  })
  mocks.getLatestValidationReport.mockResolvedValue({
    ...baseValidationReport,
  })
  mocks.updateValidationIssue.mockImplementation(async (_issueId: string, status: string) => ({
    ...baseValidationReport.issues_by_severity.P0[0],
    report_id: 'vr-1',
    chapter_id: 'chapter-1',
    status,
  }))
  mocks.buildRepairPatch.mockResolvedValue({
    issue_id: 'vi-1',
    patch_text: '建议将章末改写为人物抵达钱府并确认门已开启。',
    source: 'heuristic',
  })
})

afterAll(() => {
  warnSpy.mockRestore()
  errorSpy.mockRestore()
})

describe('ChapterContentPanel', () => {
  it('shows fusion confirmation inputs and workspace tabs', async () => {
    const panel = mountPanel()
    await flushPromises()

    expect(mocks.getLatestFusionJob).toHaveBeenCalledWith('chapter-1')
    expect(panel.findAll('n-tab-pane')).toHaveLength(5)
    expect(panel.text()).toContain('来自章节大纲，用于叙事摘要和向量检索')
    expect(panel.text()).toContain('左侧是节拍草稿摘要，右侧是当前融合草稿。此处用来查看融合是否过度压缩或丢失桥接。')
    expect(panel.text()).toContain('这里展示的是本次融合会提交的真实输入，不再显示前端估算值。正式融合会写入融合任务记录。')
    expect(panel.text()).toContain('chapter-1')
    expect(panel.text()).toContain('2700')
    expect(panel.text()).toContain('主 1 / 支 2')
    expect(panel.text()).toContain('版本 v5')
    expect(panel.text()).toContain('目标终态')

    await (panel.vm as unknown as { createFusionJob: () => Promise<void> }).createFusionJob()
    await flushPromises()

    expect(mocks.createFusionJob).toHaveBeenCalledWith('chapter-1', expect.objectContaining({
      state_lock_version: 5,
    }))
    expect(mocks.getCurrentStateLocks).toHaveBeenCalledWith('chapter-1')
    expect(mocks.getBeatSheet).toHaveBeenCalledWith('chapter-1')
    expect(panel.text()).toContain('queued')
    expect(panel.text()).toContain('任务 job-1')

    panel.unmount()
  })

  it('generates beat sheet before fusion when missing', async () => {
    mocks.getBeatSheet.mockRejectedValue({
      response: {
        status: 404,
        data: { detail: 'Beat sheet not found' },
      },
    })
    const generatedBeatSheet = {
      ...baseBeatSheet,
      id: 'beat-sheet-generated',
    }
    mocks.generateBeatSheet.mockResolvedValueOnce(generatedBeatSheet)

    const panel = mountPanel()
    await flushPromises()
    await nextTick()
    await flushPromises()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(mocks.generateBeatSheet).toHaveBeenCalledWith({
      chapter_id: 'chapter-1',
      outline: '重复句\n重复句\n收束',
      state_lock_version: 5,
    })

    await (panel.vm as unknown as { createFusionJob: () => Promise<void> }).createFusionJob()
    await flushPromises()

    expect(mocks.createFusionJob).toHaveBeenCalledWith(
      'chapter-1',
      expect.objectContaining({
        beat_ids: ['beat-1-1', 'beat-1-2', 'beat-1-3'],
      })
    )

    panel.unmount()
  })

  it('renders fusion warning states from a loaded fusion draft', async () => {
    window.localStorage.setItem('plotpilot:fusion-job:novel-1:1', 'job-1')

    const panel = mountPanel()
    await flushPromises()

    expect(panel.text()).toContain('重复率 24%')
    expect(panel.text()).toContain('融合后的章节正文')
    expect(panel.text()).toContain('重复功能偏高，建议检查开场桥接')
    expect(panel.text()).toContain('存在阻断问题')
    expect(panel.text()).toContain('定位锁项')

    panel.unmount()
  })

  it('shows the latest validation report even when the newest fusion job has no draft yet', async () => {
    mocks.getLatestFusionJob.mockResolvedValueOnce({
      fusion_job_id: 'job-running',
      chapter_id: 'chapter-1',
      status: 'running',
      error_message: '',
      fusion_draft: null,
      preview: null,
    })
    mocks.getLatestValidationReport.mockResolvedValueOnce({
      ...baseValidationReport,
    })

    const panel = mountPanel()
    await flushPromises()

    expect(mocks.getLatestValidationReport).toHaveBeenCalledWith('chapter-1', { draftType: 'fusion' })
    expect(panel.text()).toContain('报告 vr-1')
    expect(panel.text()).toContain('违反终态锁')

    panel.unmount()
  })

  it('loads latest fusion job for the current chapter before local cache', async () => {
    window.localStorage.setItem('plotpilot:fusion-job:novel-1:1', 'stale-job')

    const panel = mountPanel()
    await flushPromises()

    expect(mocks.getLatestFusionJob).toHaveBeenCalledWith('chapter-1')
    expect(mocks.getFusionJob).not.toHaveBeenCalled()
    expect(panel.text()).toContain('任务 job-1')
    expect(panel.text()).toContain('融合后的章节正文')

    panel.unmount()
  })

  it('supports validation issue actions and validation center navigation', async () => {
    window.localStorage.setItem('plotpilot:fusion-job:novel-1:1', 'job-1')
    const panel = mountPanel()
    await flushPromises()

    await (panel.vm as unknown as { openValidationCenter: () => void }).openValidationCenter()
    expect(mocks.routerPush).toHaveBeenCalledWith({
      path: '/book/novel-1/validation-center',
      query: { chapter_id: 'chapter-1' },
    })

    await (panel.vm as unknown as { requestRepairPatch: (issue: typeof baseValidationReport.issues_by_severity.P0[0]) => Promise<void> }).requestRepairPatch(baseValidationReport.issues_by_severity.P0[0] as never)
    await flushPromises()
    expect(mocks.buildRepairPatch).toHaveBeenCalledWith('vi-1')
    expect(panel.text()).toContain('建议将章末改写为人物抵达钱府并确认门已开启。')

    await (panel.vm as unknown as { updateIssueStatus: (issue: typeof baseValidationReport.issues_by_severity.P0[0], status: 'resolved') => Promise<void> }).updateIssueStatus(baseValidationReport.issues_by_severity.P0[0] as never, 'resolved')
    await flushPromises()
    expect(mocks.updateValidationIssue).toHaveBeenCalledWith('vi-1', 'resolved')

    panel.unmount()
  })
})
