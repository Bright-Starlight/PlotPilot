<template>
  <div class="story-structure">
    <div class="structure-body" v-if="treeData.length > 0">
      <n-tree
        :data="treeData"
        :node-props="nodeProps"
        :render-label="renderLabel"
        :render-suffix="renderSuffix"
        :selected-keys="selectedKeys"
        block-line
        expand-on-click
        selectable
        @update:selected-keys="handleSelect"
      />
    </div>

    <n-empty
      v-else-if="!loading"
      description="暂无叙事结构。请先查看右侧「文约设定」，确认无误后再执行「AI 初始规划」"
      class="structure-empty"
    />

    <n-spin v-if="loading" class="structure-loading" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, h, onMounted, watch } from 'vue'
import { NTree, NEmpty, NSpin, NTag, useMessage } from 'naive-ui'
import { structureApi, type StoryNode } from '@/api/structure'

const props = defineProps<{
  slug: string
  currentChapterId?: number | null
}>()

const emit = defineEmits<{
  selectChapter: [id: number]
}>()

const message = useMessage()

const loading = ref(false)
const treeData = ref<StoryNode[]>([])
const selectedKeys = ref<string[]>([])

// 监听当前章节变化，更新选中状态
watch(() => props.currentChapterId, (chapterId) => {
  if (chapterId) {
    const chapterKey = `chapter-${props.slug}-chapter-${chapterId}`
    selectedKeys.value = [chapterKey]
  } else {
    selectedKeys.value = []
  }
}, { immediate: true })

// 转换节点为 NTree 格式
const convertToTreeNode = (node: StoryNode): any => {
  // 根据节点类型设置图标
  const iconMap: Record<string, string> = {
    part: '📚',
    volume: '📖',
    act: '🎬',
    chapter: '📄'
  }

  return {
    key: node.id,
    label: node.title,
    ...node,
    icon: iconMap[node.node_type] || '📄',
    display_name: node.title,
    children: node.children?.map(convertToTreeNode) || []
  }
}

// 加载结构树
const loadTree = async () => {
  loading.value = true
  try {
    const res = await structureApi.getTree(props.slug)
    console.log('[StoryStructureTree] API response:', res)

    // 后端返回格式: { novel_id, tree: { novel_id, nodes: [...] } }
    // 提取 nodes 数组
    const nodes = res.tree?.nodes || []
    console.log('[StoryStructureTree] Extracted nodes:', nodes.length, nodes)

    // 如果有结构，显示树形视图
    if (nodes.length > 0) {
      treeData.value = nodes.map(convertToTreeNode)
      console.log('[StoryStructureTree] treeData set:', treeData.value.length)
    } else {
      // 没有结构时，显示空状态，不自动初始化
      treeData.value = []
      console.log('[StoryStructureTree] No nodes, showing empty state')
    }
  } catch (e: any) {
    console.error('[StoryStructureTree] Load error:', e)
    message.error(e?.response?.data?.detail || '加载结构失败')
  } finally {
    loading.value = false
    console.log('[StoryStructureTree] Loading finished, loading =', loading.value)
  }
}

// 初始化叙事结构（AI 生成第一幕）
const initializeStructure = async () => {
  // 防止重复点击
  if (loading.value) return

  try {
    message.info('正在生成第一幕...')
    const res = await structureApi.initializeStructure(props.slug)

    if (res.success) {
      message.success(res.message || '第一幕已创建')
      const treeRes = await structureApi.getTree(props.slug)
      const nodes = treeRes.tree?.nodes ?? (Array.isArray(treeRes.tree) ? treeRes.tree : [])
      treeData.value = nodes.map(convertToTreeNode)
    } else {
      message.warning(res.message || '结构已存在')
    }
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '初始化失败')
  } finally {
    loading.value = false
  }
}

// 选择节点
const handleSelect = (keys: string[]) => {
  if (keys.length > 0) {
    const findNode = (nodes: StoryNode[], id: string): StoryNode | null => {
      for (const node of nodes) {
        if (node.id === id) return node
        if (node.children) {
          const found = findNode(node.children, id)
          if (found) return found
        }
      }
      return null
    }

    const node = findNode(treeData.value, keys[0])
    if (node && node.node_type === 'chapter') {
      // 从 chapter-novel-xxx-chapter-123 中提取章节 ID
      const match = node.id.match(/chapter-(\d+)$/)
      if (match) {
        const chapterId = parseInt(match[1])
        emit('selectChapter', chapterId)
      }
    }
  }
}

// 渲染节点标签
const renderLabel = ({ option }: { option: StoryNode }) => {
  const elements: any[] = [
    h('span', { class: 'node-icon' }, option.icon),
    h('span', { class: 'node-title' }, option.display_name)
  ]

  // 章节节点显示状态标签
  if (option.node_type === 'chapter') {
    const hasContent = option.word_count && option.word_count > 0
    elements.push(
      h(NTag, {
        size: 'small',
        type: hasContent ? 'success' : 'default',
        round: true,
        style: { marginLeft: '8px' }
      }, () => hasContent ? '已收稿' : '未收稿')
    )
  }

  return h('span', { class: 'node-label' }, elements)
}

// 渲染节点后缀（章节范围/字数/描述）
const renderSuffix = ({ option }: { option: StoryNode }) => {
  const elements: any[] = []

  // 显示描述（部、卷、幕）
  if (option.description && ['part', 'volume', 'act'].includes(option.node_type)) {
    elements.push(
      h('span', {
        class: 'node-description',
        style: { color: '#999', fontSize: '12px', marginLeft: '8px' }
      }, option.description)
    )
  }

  // 显示章节字数
  if (option.node_type === 'chapter' && option.word_count) {
    elements.push(
      h('span', { class: 'node-range' }, `${option.word_count}字`)
    )
  }

  // 显示章节范围
  if (option.chapter_start && option.chapter_end) {
    elements.push(
      h('span', { class: 'node-range' },
        `${option.chapter_start}-${option.chapter_end}章 (${option.chapter_count})`
      )
    )
  }

  return elements.length > 0 ? h('span', {}, elements) : null
}

// 节点属性
const nodeProps = ({ option }: { option: StoryNode }) => {
  return {
    class: `node-level-${option.level}`,
    onContextmenu: (e: MouseEvent) => {
      handleContextMenu(e, option)
    }
  }
}

onMounted(() => {
  loadTree()
})
</script>

<style scoped>
.story-structure {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 8px 0;
}

.structure-body {
  flex: 1;
  overflow: auto;
}

.structure-empty {
  padding: 40px 0;
}

.structure-loading {
  display: flex;
  justify-content: center;
  padding: 40px 0;
}

.node-label {
  display: flex;
  align-items: center;
  gap: 8px;
}

.node-icon {
  font-size: 16px;
}

.node-title {
  font-size: 13px;
}

.node-range {
  font-size: 12px;
  color: #999;
  margin-left: 8px;
}

.node-level-1 {
  font-weight: 600;
}

.node-level-2 {
  font-weight: 500;
}

.node-level-3 {
  font-weight: normal;
}

.node-level-4 {
  font-weight: normal;
  font-size: 13px;
}
</style>
