import { shallowMount } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { defineComponent } from 'vue'

import ChapterList from '../ChapterList.vue'

const mocks = vi.hoisted(() => ({
  routerPush: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: mocks.routerPush,
  }),
}))

describe('ChapterList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('opens chapter editor from the flat list edit button', async () => {
    const wrapper = shallowMount(ChapterList, {
      props: {
        slug: 'novel-1',
        chapters: [{ id: 22, number: 22, title: '第二十二章', word_count: 1200 }],
        currentChapterId: 22,
      },
      global: {
        stubs: {
          StoryStructureTree: true,
          MacroPlanModal: true,
          'n-scrollbar': defineComponent({ template: '<div><slot /></div>' }),
          'n-list': defineComponent({ template: '<div><slot /></div>' }),
          'n-list-item': defineComponent({ template: '<div><slot /></div>' }),
          'n-thing': defineComponent({ template: '<div><slot name="description" /></div>' }),
          'n-text': defineComponent({ template: '<span><slot /></span>' }),
          'n-tag': defineComponent({ template: '<span><slot /></span>' }),
          'n-select': defineComponent({ template: '<div />' }),
          'n-button': defineComponent({
            emits: ['click'],
            template: '<button @click="$emit(\'click\', $event)"><slot /></button>',
          }),
        },
      },
    })

    ;(wrapper.vm as unknown as { viewMode: string }).viewMode = 'flat'
    await wrapper.vm.$nextTick()

    const editButton = wrapper.findAll('button').find(node => node.text() === '编辑')
    expect(editButton).toBeTruthy()

    await editButton!.trigger('click')

    expect(mocks.routerPush).toHaveBeenCalledWith('/book/novel-1/chapter/22')
  })
})
