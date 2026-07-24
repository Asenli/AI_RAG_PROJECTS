<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { knowledgeApi } from '@/api/knowledge'
import { ROLES } from '@/stores/user'

const activeTab = ref<'upload' | 'split' | 'search' | 'list'>('upload')

// ── Upload tab ──
const uploadFile = ref<File | null>(null)
const uploadModule = ref('')
const uploadSubModule = ref('')
const uploadKtype = ref('faq')
const uploadRole = ref('school')
const uploading = ref(false)

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  uploadFile.value = input.files?.[0] || null
}

async function doUpload() {
  if (!uploadFile.value) {
    alert('请选择文件')
    return
  }
  uploading.value = true
  try {
    const form = new FormData()
    form.append('file', uploadFile.value)
    form.append('module', uploadModule.value)
    form.append('sub_module', uploadSubModule.value)
    form.append('knowledge_type', uploadKtype.value)
    form.append('role', uploadRole.value)
    await knowledgeApi.upload(form)
    alert('上传成功!')
    await loadDocs()
    activeTab.value = 'list'
    // Reset
    uploadFile.value = null
    const fileInput = document.getElementById('upload-file-input') as HTMLInputElement
    if (fileInput) fileInput.value = ''
  } catch (e: any) {
    alert('上传失败: ' + (e.userMessage || e.response?.data?.detail || e.message))
  } finally {
    uploading.value = false
  }
}

// ── Split preview tab ──
const previewContent = ref('')
const previewKtype = ref('faq')
const previewLoading = ref(false)
const previewChunks = ref<any[]>([])

async function doPreview() {
  if (!previewContent.value.trim()) {
    alert('请输入内容')
    return
  }
  previewLoading.value = true
  previewChunks.value = []
  try {
    const res = await knowledgeApi.previewSplit({
      content: previewContent.value,
      knowledge_type: previewKtype.value,
      module: 'preview',
      sub_module: '',
    })
    previewChunks.value = res.data.chunks || []
  } catch (e: any) {
    alert('预览失败: ' + (e.userMessage || e.response?.data?.detail || e.message))
  } finally {
    previewLoading.value = false
  }
}

// ── Search test tab ──
const searchQuery = ref('')
const searchRole = ref('school')
const searchTopK = ref(5)
const searchLoading = ref(false)
const searchResults = ref<any[]>([])
const searchReport = ref<any | null>(null)

const searchStages = [
  {
    key: 'dense',
    title: '向量检索',
    desc: '语义相似度召回，适合表达不同但意思相近的问题',
    scoreKey: 'dense_score',
  },
  {
    key: 'bm25',
    title: 'BM25 检索',
    desc: '关键词匹配召回，适合专有名词、菜单名、功能名精确命中',
    scoreKey: 'bm25_score',
  },
  {
    key: 'hybrid',
    title: 'RRF 融合结果',
    desc: 'Qdrant 将向量检索和 BM25 结果融合后的候选排序',
    scoreKey: 'hybrid_score',
  },
  {
    key: 'rerank',
    title: 'Rerank 最终排序',
    desc: '重排序模型对融合候选再次判断后的最终相关性',
    scoreKey: 'rerank_score',
  },
]

async function doSearch() {
  if (!searchQuery.value.trim()) {
    alert('请输入查询')
    return
  }
  searchLoading.value = true
  searchResults.value = []
  searchReport.value = null
  try {
    const res = await knowledgeApi.searchTest({
      q: searchQuery.value,
      role: searchRole.value,
      top_k: searchTopK.value,
    })
    searchReport.value = res.data
    searchResults.value = res.data.results || res.data.stages?.rerank || []
  } catch (e: any) {
    alert('搜索失败: ' + (e.userMessage || e.response?.data?.detail || e.message))
  } finally {
    searchLoading.value = false
  }
}

// ── Document list tab ──
const docs = ref<any[]>([])
const docLoading = ref(false)
const totalDocuments = ref(0)
const totalChunks = ref(0)
const selectedDoc = ref<any | null>(null)
const docDetail = ref<any | null>(null)
const detailLoading = ref(false)

async function loadDocs() {
  docLoading.value = true
  try {
    const res = await knowledgeApi.list()
    docs.value = res.data.documents || res.data || []
    totalDocuments.value = res.data.total_documents ?? docs.value.length
    totalChunks.value = res.data.total_chunks ?? 0
  } catch (e: any) {
    console.error('加载文档列表失败:', e)
  } finally {
    docLoading.value = false
  }
}

async function openDocDetail(doc: any) {
  const source = doc.source
  if (!source) return
  selectedDoc.value = doc
  docDetail.value = null
  detailLoading.value = true
  try {
    const res = await knowledgeApi.detail(source)
    docDetail.value = res.data
  } catch (e: any) {
    alert('加载文档详情失败: ' + (e.userMessage || e.response?.data?.detail || e.message))
    selectedDoc.value = null
  } finally {
    detailLoading.value = false
  }
}

function closeDocDetail() {
  selectedDoc.value = null
  docDetail.value = null
  detailLoading.value = false
}

async function deleteDoc(doc: any) {
  const source = doc.source
  if (!source) {
    alert('缺少文档 source，无法删除')
    return
  }
  if (!confirm('确定删除此文档?')) return
  try {
    await knowledgeApi.deleteDoc(source)
    await loadDocs()
  } catch (e: any) {
    alert('删除失败: ' + (e.userMessage || e.response?.data?.detail || e.message))
  }
}

async function reindexDoc(doc: any) {
  const source = doc.source
  if (!source) {
    alert('缺少文档 source，无法重建索引')
    return
  }
  try {
    const res = await knowledgeApi.reindex(source)
    alert(`重建索引完成，共 ${res.data.chunks || 0} 个知识块`)
    await loadDocs()
  } catch (e: any) {
    alert('重建索引失败: ' + (e.userMessage || e.response?.data?.detail || e.message))
  }
}

onMounted(() => {
  loadDocs()
})

function scoreBadgeClass(s: number): string {
  if (s >= 0.8) return 'bg-green-100 text-green-700'
  if (s >= 0.65) return 'bg-yellow-100 text-yellow-700'
  return 'bg-red-100 text-red-700'
}

function stageItems(key: string): any[] {
  return searchReport.value?.stages?.[key] || []
}

function formatScore(score: number | undefined | null): string {
  if (score === undefined || score === null) return '-'
  if (Math.abs(score) <= 1) return `${(score * 100).toFixed(1)}%`
  return Number(score).toFixed(4)
}

function scoreForStage(item: any, scoreKey: string): number | undefined {
  return item?.[scoreKey] ?? item?.score
}
</script>

<template>
  <div>
    <!-- Tabs -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 mb-4">
      <div class="flex border-b border-gray-200">
        <button
          v-for="tab in [
            { key: 'upload' as const, label: '文档上传', icon: '📤' },
            { key: 'split' as const, label: '切分预览', icon: '✂️' },
            { key: 'search' as const, label: '检索测试', icon: '🔍' },
            { key: 'list' as const, label: '文档列表', icon: '📋' },
          ]"
          :key="tab.key"
          @click="activeTab = tab.key"
          :class="[
            'px-5 py-3 text-sm font-medium border-b-2 transition-colors',
            activeTab === tab.key
              ? 'border-blue-600 text-blue-600'
              : 'border-transparent text-gray-500 hover:text-gray-700',
          ]"
        >
          <span class="mr-1.5">{{ tab.icon }}</span>{{ tab.label }}
        </button>
      </div>
    </div>

    <!-- Tab: Upload -->
    <div v-if="activeTab === 'upload'" class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <h2 class="text-lg font-semibold text-gray-800 mb-5">上传知识文档</h2>
      <div class="space-y-4 max-w-lg">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">选择文件 (.md)</label>
          <input
            id="upload-file-input"
            type="file"
            accept=".md,.markdown"
            @change="onFileChange"
            class="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-medium file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
          />
        </div>
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">模块</label>
            <input
              v-model="uploadModule"
              type="text"
              class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
              placeholder="例如: 订单管理"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">子模块</label>
            <input
              v-model="uploadSubModule"
              type="text"
              class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
              placeholder="例如: 退餐流程"
            />
          </div>
        </div>
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">知识类型</label>
            <select
              v-model="uploadKtype"
              class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
            >
              <option value="faq">FAQ (常见问题)</option>
              <option value="manual">操作手册</option>
              <option value="system">系统文档</option>
              <option value="regulation">政策法规</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">角色</label>
            <select
              v-model="uploadRole"
              class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
            >
              <option v-for="r in ROLES" :key="r.value" :value="r.value">{{ r.icon }} {{ r.label }}</option>
            </select>
          </div>
        </div>
        <button
          @click="doUpload"
          :disabled="uploading"
          class="px-6 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {{ uploading ? '上传中...' : '上传文档' }}
        </button>
      </div>
    </div>

    <!-- Tab: Split Preview -->
    <div v-if="activeTab === 'split'" class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <h2 class="text-lg font-semibold text-gray-800 mb-5">切分预览</h2>
      <div class="space-y-4 max-w-2xl">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">粘贴内容</label>
          <textarea
            v-model="previewContent"
            rows="8"
            class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm font-mono focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none resize-y"
            placeholder="粘贴Markdown内容..."
          ></textarea>
        </div>
        <div class="flex items-center space-x-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">知识类型</label>
            <select
              v-model="previewKtype"
              class="border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
            >
              <option value="faq">FAQ (256字符)</option>
              <option value="manual">操作手册 (512字符)</option>
              <option value="system">系统文档 (384字符)</option>
              <option value="regulation">政策法规 (768字符)</option>
            </select>
          </div>
          <button
            @click="doPreview"
            :disabled="previewLoading"
            class="px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors self-end"
          >
            {{ previewLoading ? '处理中...' : '预览切分' }}
          </button>
        </div>

        <!-- Chunk cards -->
        <div v-if="previewChunks.length > 0" class="mt-4 space-y-3">
          <p class="text-sm text-gray-500">共 {{ previewChunks.length }} 个块</p>
          <div
            v-for="(chunk, ci) in previewChunks"
            :key="ci"
            class="border border-gray-200 rounded-lg p-4 bg-gray-50"
          >
            <div class="flex items-center justify-between mb-2">
              <span class="text-xs font-semibold text-blue-600">块 #{{ ci + 1 }}</span>
              <span class="text-xs text-gray-400">{{ chunk.char_count || chunk.content?.length || 0 }} 字符</span>
            </div>
            <p class="text-sm text-gray-700 whitespace-pre-wrap">{{ chunk.content || chunk.text || chunk.text_preview }}</p>
            <div v-if="chunk.metadata" class="mt-2 text-xs text-gray-400">
              元数据: {{ JSON.stringify(chunk.metadata) }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Tab: Search Test -->
    <div v-if="activeTab === 'search'" class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <h2 class="text-lg font-semibold text-gray-800 mb-5">检索测试</h2>
      <div class="space-y-3 max-w-2xl">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">查询</label>
          <input
            v-model="searchQuery"
            type="text"
            class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
            placeholder="输入查询文本..."
          />
        </div>
        <div class="flex items-center space-x-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">角色</label>
            <select
              v-model="searchRole"
              class="border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
            >
              <option v-for="r in ROLES" :key="r.value" :value="r.value">{{ r.icon }} {{ r.label }}</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Top-K: {{ searchTopK }}</label>
            <input
              v-model.number="searchTopK"
              type="range"
              min="1"
              max="20"
              class="w-40"
            />
          </div>
          <button
            @click="doSearch"
            :disabled="searchLoading"
            class="px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors self-end"
          >
            {{ searchLoading ? '搜索中...' : '搜索' }}
          </button>
        </div>

        <!-- Results -->
        <div v-if="searchReport" class="mt-5 space-y-4">
          <div class="rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-800">
            <div>查询：{{ searchReport.query }}</div>
            <div v-if="searchReport.rewritten_query && searchReport.rewritten_query !== searchReport.query" class="mt-1">
              改写后：{{ searchReport.rewritten_query }}
            </div>
            <div class="mt-1 text-xs text-blue-600">
              角色：{{ searchReport.role }} ｜ 过滤条件：{{ searchReport.filter_expr || '无' }}
            </div>
          </div>

          <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <section
              v-for="stage in searchStages"
              :key="stage.key"
              class="border border-gray-200 rounded-lg bg-white overflow-hidden"
            >
              <div class="px-4 py-3 border-b border-gray-100 bg-gray-50">
                <div class="flex items-center justify-between">
                  <h3 class="text-sm font-semibold text-gray-800">{{ stage.title }}</h3>
                  <span class="text-xs text-gray-400">{{ stageItems(stage.key).length }} 条</span>
                </div>
                <p class="mt-1 text-xs text-gray-500">{{ stage.desc }}</p>
              </div>

              <div v-if="stageItems(stage.key).length > 0" class="divide-y divide-gray-100">
                <div
                  v-for="(r, ri) in stageItems(stage.key)"
                  :key="`${stage.key}-${r.id || ri}`"
                  class="p-4"
                >
                  <div class="flex items-start justify-between gap-3 mb-2">
                    <div class="flex items-center space-x-2">
                      <span class="text-xs font-mono text-gray-400">#{{ ri + 1 }}</span>
                      <span
                        :class="scoreBadgeClass(scoreForStage(r, stage.scoreKey) || 0)"
                        class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-mono"
                      >
                        {{ formatScore(scoreForStage(r, stage.scoreKey)) }}
                      </span>
                      <span v-if="stage.key === 'rerank' && r.hybrid_rank" class="text-xs text-gray-400">
                        融合排名 #{{ r.hybrid_rank }}
                      </span>
                    </div>
                    <span class="text-xs text-gray-400 text-right break-all">{{ r.source || r.id }}</span>
                  </div>
                  <div class="text-xs text-gray-500 mb-2">
                    {{ r.module || '-' }}<span v-if="r.sub_module"> / {{ r.sub_module }}</span>
                    <span v-if="r.header_path"> ｜ {{ r.header_path }}</span>
                  </div>
                  <p class="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">{{ r.text || r.content }}</p>
                </div>
              </div>
              <div v-else class="p-6 text-center text-sm text-gray-400">
                无结果
              </div>
            </section>
          </div>
        </div>
        <div v-else-if="searchLoading" class="text-center text-gray-400 py-8">
          <svg class="animate-spin h-5 w-5 mx-auto mb-2" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          <p>搜索中...</p>
        </div>
      </div>
    </div>

    <!-- Tab: Document List -->
    <div v-if="activeTab === 'list'" class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <div class="flex items-center justify-between mb-5">
        <div>
          <h2 class="text-lg font-semibold text-gray-800">文档列表</h2>
          <div class="mt-2 flex items-center space-x-3 text-xs text-gray-500">
            <span class="inline-flex items-center px-2.5 py-1 rounded-md bg-gray-100 text-gray-700">
              文件总数：{{ totalDocuments }}
            </span>
            <span class="inline-flex items-center px-2.5 py-1 rounded-md bg-gray-100 text-gray-700">
              知识块：{{ totalChunks }}
            </span>
          </div>
        </div>
        <button
          @click="loadDocs"
          :disabled="docLoading"
          class="px-4 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 text-gray-600 rounded-md transition-colors"
        >
          {{ docLoading ? '加载中...' : '刷新' }}
        </button>
      </div>

      <div v-if="docs.length === 0 && !docLoading" class="text-center text-gray-400 py-8">
        <p class="text-lg">暂无文档</p>
        <p class="text-sm">请先上传知识文档</p>
      </div>

      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-gray-200 bg-gray-50">
              <th class="text-left py-3 px-4 font-semibold text-gray-600">文件名</th>
              <th class="text-left py-3 px-4 font-semibold text-gray-600">模块</th>
              <th class="text-left py-3 px-4 font-semibold text-gray-600">知识类型</th>
              <th class="text-left py-3 px-4 font-semibold text-gray-600">块数</th>
              <th class="text-left py-3 px-4 font-semibold text-gray-600">状态</th>
              <th class="text-left py-3 px-4 font-semibold text-gray-600">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="doc in docs"
              :key="doc.id || doc.doc_id"
              @click="openDocDetail(doc)"
              class="border-b border-gray-100 hover:bg-blue-50 transition-colors cursor-pointer"
            >
              <td class="py-3 px-4 font-mono text-xs text-gray-700">{{ doc.filename || doc.doc_id }}</td>
              <td class="py-3 px-4 text-gray-600">{{ doc.module || '-' }}<span v-if="doc.sub_module"> / {{ doc.sub_module }}</span></td>
              <td class="py-3 px-4">
                <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700">
                  {{ doc.knowledge_type || '-' }}
                </span>
              </td>
              <td class="py-3 px-4 text-gray-600">{{ doc.chunk_count || doc.chunks || '-' }}</td>
              <td class="py-3 px-4">
                <span :class="doc.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'"
                  class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium">
                  {{ doc.managed === false ? '已入库' : (doc.status || 'active') }}
                </span>
              </td>
              <td class="py-3 px-4">
                <div v-if="doc.managed !== false" class="flex items-center space-x-2">
                  <button
                    @click.stop="deleteDoc(doc)"
                    class="px-2.5 py-1 text-xs text-red-600 hover:bg-red-50 rounded transition-colors"
                  >
                    🗑️ 删除
                  </button>
                  <button
                    @click.stop="reindexDoc(doc)"
                    class="px-2.5 py-1 text-xs text-blue-600 hover:bg-blue-50 rounded transition-colors"
                  >
                    🔄 重建索引
                  </button>
                </div>
                <span v-else class="text-xs text-gray-400">批量导入文件</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div
      v-if="selectedDoc"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
      @click.self="closeDocDetail"
    >
      <div class="w-full max-w-4xl max-h-[86vh] bg-white rounded-lg shadow-xl border border-gray-200 flex flex-col">
        <div class="px-5 py-4 border-b border-gray-200 flex items-start justify-between">
          <div>
            <h3 class="text-lg font-semibold text-gray-800">{{ selectedDoc.filename }}</h3>
            <p class="mt-1 text-xs text-gray-500 font-mono">{{ selectedDoc.source }}</p>
          </div>
          <button
            @click="closeDocDetail"
            class="px-3 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-md transition-colors"
          >
            关闭
          </button>
        </div>

        <div v-if="detailLoading" class="p-10 text-center text-gray-400">
          加载中...
        </div>

        <div v-else-if="docDetail" class="overflow-y-auto p-5">
          <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5 text-sm">
            <div class="bg-gray-50 rounded-md p-3">
              <div class="text-xs text-gray-400 mb-1">模块</div>
              <div class="text-gray-700">{{ docDetail.module || '-' }}</div>
            </div>
            <div class="bg-gray-50 rounded-md p-3">
              <div class="text-xs text-gray-400 mb-1">子模块</div>
              <div class="text-gray-700">{{ docDetail.sub_module || '-' }}</div>
            </div>
            <div class="bg-gray-50 rounded-md p-3">
              <div class="text-xs text-gray-400 mb-1">类型</div>
              <div class="text-gray-700">{{ docDetail.knowledge_type || '-' }}</div>
            </div>
            <div class="bg-gray-50 rounded-md p-3">
              <div class="text-xs text-gray-400 mb-1">知识块</div>
              <div class="text-gray-700">{{ docDetail.chunk_count }}</div>
            </div>
          </div>

          <div class="space-y-4">
            <div
              v-for="chunk in docDetail.chunks"
              :key="chunk.id"
              class="border border-gray-200 rounded-lg p-4 bg-white"
            >
              <div class="flex items-center justify-between mb-3">
                <div class="text-xs font-medium text-blue-600">
                  #{{ Number(chunk.chunk_index ?? 0) + 1 }}
                  <span v-if="chunk.header_path" class="text-gray-500 ml-2">{{ chunk.header_path }}</span>
                </div>
                <span class="text-xs text-gray-400">{{ chunk.text?.length || 0 }} 字符</span>
              </div>
              <pre class="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed font-sans">{{ chunk.text }}</pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
