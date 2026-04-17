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
  createFusionJob: vi.fn(),
  getFusionJob: vi.fn(),
}))

const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

vi.mock('naive-ui', async () => {
  return {
    useMessage: () => mocks.message,
  }
})

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
    getFusionJob: mocks.getFusionJob,
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
  mocks.createFusionJob.mockResolvedValue({
    fusion_job_id: 'job-1',
    chapter_id: 'chapter-1',
    status: 'queued',
    error_message: '',
    fusion_draft: null,
    preview: null,
  })
  mocks.getFusionJob.mockResolvedValue({
    fusion_job_id: 'job-1',
    chapter_id: 'chapter-1',
    status: 'completed',
    error_message: '',
    fusion_draft: {
      fusion_id: 'fusion-1',
      chapter_id: 'chapter-1',
      text: '融合后的章节正文',
      estimated_repeat_ratio: 0.24,
      facts_confirmed: ['线索 A'],
      open_questions: ['谜团 B'],
      end_state: { scene: '终态' },
      warnings: ['重复功能偏高，建议检查开场桥接'],
    },
    preview: {
      estimated_words: 1800,
      estimated_repeat_ratio: 0.24,
      expected_end_state: { scene: '终态' },
      expected_suspense_count: 2,
      risk_warnings: ['重复功能偏高，建议检查开场桥接'],
    },
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

    expect(panel.findAll('n-tab-pane')).toHaveLength(5)
    expect(panel.text()).toContain('来自章节大纲，用于叙事摘要和向量检索')
    expect(panel.text()).toContain('左侧是节拍草稿摘要，右侧是当前融合草稿。此处用来查看融合是否过度压缩或丢失桥接。')
    expect(panel.text()).toContain('这里展示的是本次融合会提交的真实输入，不再显示前端估算值。正式融合会写入融合任务记录。')
    expect(panel.text()).toContain('chapter-1')
    expect(panel.text()).toContain('2700')
    expect(panel.text()).toContain('主 1 / 支 2')
    expect(panel.text()).toContain('门已开启')

    await (panel.vm as unknown as { createFusionJob: () => Promise<void> }).createFusionJob()
    await flushPromises()

    expect(mocks.createFusionJob).toHaveBeenCalledWith('chapter-1', expect.any(Object))
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

    panel.unmount()
  })
})
