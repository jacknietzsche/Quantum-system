<template>
  <div class="database-container">
    <div class="space-y-4 max-w-6xl">

      <!-- ═══ 标题栏 ═══ -->
      <div class="flex justify-between items-center">
        <h1 class="text-2xl font-bold flex items-center gap-2">
          <el-icon><Folder /></el-icon>
          数据库管理
        </h1>
        <div class="flex gap-2 flex-wrap">
          <el-button :loading="refreshingHot" @click="handleRefresh('hot')">
            <el-icon><Refresh /></el-icon>
            刷新热榜
          </el-button>
          <el-button :loading="refreshingFull" @click="handleRefresh('full')">
            <el-icon><Refresh /></el-icon>
            全市场刷新
          </el-button>
          <el-button type="primary" @click="adding = true">
            <el-icon><Plus /></el-icon>
            添加股票
          </el-button>
          <el-button :loading="repairing" type="warning" @click="handleBatchRepair">
            <el-icon><DataAnalysis /></el-icon>
            批量修复
          </el-button>
          <el-button :loading="cleaning" type="danger" plain @click="handleCleanStale">
            <el-icon><Delete /></el-icon>
            清理空壳
          </el-button>
        </div>
      </div>

      <!-- ═══ 数据管道状态 ═══ -->
      <div class="card p-3">
        <div class="text-sm mb-3 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <el-icon :size="14"><Connection /></el-icon>
            <span style="color: var(--text-secondary)">数据管道状态</span>
          </div>
          <span v-if="stats" class="text-xs mono" :style="{ color: pipelineScore.color }">
            健康度 {{ pipelineScore.pct }}%
          </span>
        </div>
        <div class="grid grid-cols-3 sm:grid-cols-6 gap-2">
          <div v-for="p in pipelineStages" :key="p.key"
            class="p-3 rounded text-center"
            :style="{ background: p.active ? 'rgba(0,168,90,0.06)' : 'rgba(227,53,69,0.04)', border: `1px solid ${p.active ? 'rgba(0,168,90,0.15)' : 'rgba(227,53,69,0.10)'}` }">
            <div class="text-lg font-bold mono" :style="{ color: p.active ? 'var(--accent-green)' : 'var(--text-muted)' }">
              {{ p.count }}
            </div>
            <div class="text-xs mt-1" style="color: var(--text-secondary)">{{ p.label }}</div>
          </div>
        </div>
        <div v-if="needsRefresh" class="mt-3 flex items-center gap-2">
          <el-icon :size="14" style="color: var(--accent-amber)"><WarningFilled /></el-icon>
          <span class="text-xs" style="color: var(--accent-amber)">{{ refreshHint }}</span>
        </div>
      </div>

      <!-- ═══ 空库引导 ═══ -->
      <div v-if="stats && stats.stock_count === 0" class="card p-6 text-center">
        <el-icon :size="48" style="color: var(--text-muted)"><FolderOpened /></el-icon>
        <h2 class="text-lg font-bold mt-3" style="color: var(--text-secondary)">数据库为空</h2>
        <p class="text-sm mt-2" style="color: var(--text-muted); max-width: 400px; margin: 8px auto;">
          尚未载入股票数据。点击下方按钮从数据源获取热门股票数据，或手动添加个股。
        </p>
        <div class="flex gap-3 justify-center mt-4">
          <el-button type="primary" :loading="refreshingHot" @click="handleRefresh('hot')">
            <el-icon><Refresh /></el-icon> 刷新热榜 (约100只)
          </el-button>
          <el-button :loading="refreshingFull" @click="handleRefresh('full')">
            <el-icon><Refresh /></el-icon> 全市场刷新 (约5000只)
          </el-button>
          <el-button @click="adding = true">
            <el-icon><Plus /></el-icon> 手动添加
          </el-button>
        </div>
      </div>

      <!-- ═══ 统计卡片 + 缓存管理 ═══ -->
      <div v-if="stats && stats.stock_count > 0" class="grid grid-cols-4 gap-3">
        <div class="card p-3">
          <div class="text-xl font-bold" style="color: var(--accent-blue)">{{ stats.stock_count }}</div>
          <div class="text-xs mt-1" style="color: var(--text-muted)">股票总数</div>
        </div>
        <div class="card p-3">
          <div class="text-xl font-bold" style="color: var(--accent-green)">{{ stats.kline_count }}</div>
          <div class="text-xs mt-1" style="color: var(--text-muted)">K线记录</div>
        </div>
        <div class="card p-3">
          <div class="text-xl font-bold" style="color: var(--accent-amber)">{{ stats.snapshot_count }}</div>
          <div class="text-xs mt-1" style="color: var(--text-muted)">快照缓存</div>
        </div>
        <div class="card p-3">
          <div class="flex items-center gap-2">
            <span class="text-xl font-bold" style="color: var(--text-secondary)">
              {{ dbSize }}
            </span>
          </div>
          <div class="text-xs mt-1" style="color: var(--text-muted)">数据库大小</div>
        </div>
      </div>

      <!-- ECharts渲染容器: 必须始终可见(非display:none)才能获取尺寸 -->
      <!-- 数据质量面板 -->
      <div class="quality-panel" v-show="qualityData?.fields">
        <div class="quality-header">
          <div class="flex items-center gap-2">
            <el-icon :size="16" style="color: var(--accent-cyan)"><DataAnalysis /></el-icon>
            <span class="quality-title">数据质量仪表盘</span>
          </div>
          <span v-if="stats?.last_kline_date" class="quality-date">
            最新K线: {{ stats.last_kline_date }}
          </span>
        </div>
        <div class="quality-body">
          <!-- 左侧: 数据新鲜度 -->
          <div class="quality-gauge">
            <div class="gauge-label">
              <span>数据新鲜度</span>
              <span class="gauge-value">{{ freshnessHours }}h前更新</span>
            </div>
            <div ref="freshnessChartRef" style="height:240px;width:100%"></div>
            <div class="gauge-footer">
              <span :style="{ color: freshnessHours <= 4 ? 'var(--accent-green)' : freshnessHours <= 24 ? 'var(--accent-amber)' : 'var(--accent-red)' }">
                {{ freshnessHours <= 4 ? '✓ 实时' : freshnessHours <= 24 ? '⚡ 今日' : '✗ 过期' }}
              </span>
              <span>{{ stats?.stock_count || 0 }} 只股票</span>
            </div>
          </div>
          <!-- 右侧: 字段完整度 -->
          <div class="quality-details">
            <div class="quality-detail-header">字段填充率</div>
            <div v-if="qualityData?.fields" class="quality-field-list">
              <div v-for="(f, name) in qualityData.fields" :key="name" class="quality-field-row">
                <div class="qf-label">{{ fieldLabel(name) }}</div>
                <div class="qf-track"><div class="qf-fill" :style="{ width: f.pct+'%', background: f.pct>=80?'var(--accent-green)':f.pct>=50?'var(--accent-amber)':'var(--accent-red)' }"></div></div>
                <div class="qf-pct" :style="{ color: f.pct>=80?'var(--accent-green)':f.pct>=50?'var(--accent-amber)':'var(--accent-red)' }">{{ f.pct }}%</div>
                <div class="qf-nums">{{ f.filled }}/{{ f.total }}</div>
              </div>
            </div>
            <div v-else class="quality-empty"><span style="color:var(--text-muted)">加载完整度数据...</span></div>
          </div>
        </div>
      </div>

      <!-- 完整度玫瑰图 -->
      <div class="card p-4" v-show="qualityData?.fields">
        <div class="flex items-center justify-between mb-2">
          <span class="text-xs font-mono uppercase tracking-wider" style="color:var(--text-muted)">完整度玫瑰图</span>
          <span class="text-xs" style="color:var(--text-muted)">{{ qualityData?.total||0 }} stocks</span>
        </div>
        <div ref="coverageChartRef" style="height:260px;width:100%"></div>
      </div>

      <!-- ═══ 缓存管理 ═══ -->
      <div v-if="snapshots.length > 0" class="card p-3">
        <div class="flex items-center justify-between mb-2">
          <div class="flex items-center gap-2">
            <el-icon :size="14"><Clock /></el-icon>
            <span class="text-sm" style="color: var(--text-secondary)">缓存快照</span>
          </div>
          <el-button size="small" text :loading="clearingCache" @click="handleClearCache">
            <el-icon><Delete /></el-icon> 清空缓存
          </el-button>
        </div>
        <div v-for="(s, i) in snapshots" :key="i"
          class="flex justify-between py-1.5 text-sm"
          :style="{ borderBottom: i < snapshots.length - 1 ? '1px solid var(--border)' : 'none' }">
          <span class="mono">{{ s.type }}</span>
          <span style="color: var(--text-muted)">{{ s.updated }}</span>
        </div>
      </div>

      <!-- ═══ 数据源连接测试 ═══ -->
      <div class="card p-3">
        <div class="text-sm mb-2 flex items-center justify-between" style="color: var(--text-secondary)">
          <div class="flex items-center gap-2">
            <el-icon :size="14"><Connection /></el-icon>
            <span>数据源连接</span>
            <span v-if="sourceTest.loading" class="text-xs" style="color: var(--accent-blue)">测试中...</span>
            <span v-else class="text-xs">({{ sourceTest.ok }}/{{ sourceTest.total }} 可用)</span>
          </div>
          <el-button text size="small" :loading="sourceTest.loading" @click="runSourceTest">
            {{ sourceTest.loading ? '...' : '重新测试' }}
          </el-button>
        </div>
        <div class="flex gap-2 flex-wrap">
          <div
            v-for="(s, name) in sourceTest.sources"
            :key="name"
            class="px-3 py-1.5 rounded text-xs mono flex items-center gap-2"
            :class="s.ok ? 'bg-green-900/30 border border-green-700/50' : 'bg-red-900/30 border border-red-700/50'"
          >
            <span class="w-2 h-2 rounded-full" :class="s.ok ? 'bg-green-400' : 'bg-red-400'" />
            <span :class="s.ok ? 'text-green-300' : 'text-red-300'">{{ name }}</span>
            <span style="color: var(--text-muted)">{{ s.latency_ms }}ms</span>
            <span v-if="s.error" class="text-xs max-w-30 truncate" :title="s.error" style="color: var(--accent-red)">
              {{ s.error }}
            </span>
          </div>
        </div>
      </div>

      <!-- ═══ 标签页 ═══ -->
      <el-tabs v-model="tab" @tab-change="handleTabChange">
        <el-tab-pane label="StockInfo" name="stockinfo" />
        <el-tab-pane label="热榜TOP100" name="hotstocks" />
        <el-tab-pane label="龙虎榜" name="lhb" />
        <el-tab-pane label="行业分布" name="industry" />
        <el-tab-pane label="快照" name="snapshots" />
        <el-tab-pane label="Data Browser" name="data-browser" />
      </el-tabs>

      <!--  StockInfo 表 -->
      <div v-if="tab === 'stockinfo'">
        <div v-if="stocks.length === 0 && !loading" class="card p-8 text-center">
          <el-icon :size="36" style="color: var(--text-muted)"><Search /></el-icon>
          <p class="mt-2 text-sm" style="color: var(--text-muted)">暂无股票数据，请先刷新数据源</p>
        </div>
        <template v-else>
          <div class="flex gap-3 items-center mb-4">
            <el-input v-model="search" placeholder="搜索代码/名称..." clearable @input="handleSearch">
              <template #prefix><el-icon><Search /></el-icon></template>
            </el-input>
            <span class="text-sm" style="color: var(--text-muted)">{{ total }} 条记录</span>
          </div>
          <el-table :data="stocks" style="width: 100%" @sort-change="handleSortChange">
            <el-table-column prop="stock_code" label="代码" width="100" sortable="custom">
              <template #default="{ row }"><span class="mono">{{ row.stock_code }}</span></template>
            </el-table-column>
            <el-table-column prop="stock_name" label="名称" width="120" />
            <el-table-column prop="category" label="类型" width="80">
              <template #default="{ row }">
                <span class="px-2 py-0.5 rounded text-xs font-medium"
                  :class="{
                    'bg-blue-900/50 text-blue-300': row.category === '股票' || !row.category,
                    'bg-purple-900/50 text-purple-300': row.category === 'ETF',
                    'bg-green-900/50 text-green-300': row.category === 'LOF',
                  }">
                  {{ row.category || '股票' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="latest_price" label="价格" width="100" sortable="custom">
              <template #default="{ row }">
                <span :style="{ color: !row.latest_price ? 'var(--accent-amber)' : undefined }">
                  {{ (row.latest_price || 0).toFixed(2) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="pe_ratio" label="PE" width="80" sortable="custom">
              <template #default="{ row }">
                <span :style="{ color: !row.pe_ratio ? 'var(--accent-amber)' : undefined }">
                  {{ (row.pe_ratio || 0).toFixed(1) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="turnover_rate" label="换手%" width="80" sortable="custom">
              <template #default="{ row }">
                <span :style="{ color: !row.turnover_rate ? 'var(--accent-amber)' : undefined }">
                  {{ (row.turnover_rate || 0).toFixed(1) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="trend" label="趋势" width="80" />
            <el-table-column prop="industry" label="行业" width="100" />
            <el-table-column label="操作" width="120">
              <template #default="{ row }">
                <div class="flex gap-1">
                  <el-button text size="small" @click="openEdit(row)"><el-icon><Edit /></el-icon></el-button>
                  <el-button text size="small" @click="handleRefresh('hot', [row.stock_code])"><el-icon><Refresh /></el-icon></el-button>
                  <el-button text size="small" type="danger" @click="handleDelete(row.stock_code)"><el-icon><Delete /></el-icon></el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="total > 50" class="flex justify-center mt-4">
            <el-pagination v-model:current-page="page" :page-size="50" :total="total"
              layout="prev, pager, next" @current-change="fetchData" />
          </div>
        </template>
      </div>

      <!-- 热榜 -->
      <div v-if="tab === 'hotstocks'">
        <div v-if="hotStocks.length === 0" class="card p-8 text-center">
          <p class="text-sm" style="color: var(--text-muted)">暂无热榜数据，请点击"刷新热榜"</p>
        </div>
        <el-table v-else :data="hotStocks" style="width: 100%">
          <el-table-column label="#" width="60">
            <template #default="{ $index }">{{ $index + 1 }}</template>
          </el-table-column>
          <el-table-column prop="code" label="代码" width="100">
            <template #default="{ row }"><span class="mono">{{ row.code }}</span></template>
          </el-table-column>
          <el-table-column prop="name" label="名称" width="120" />
          <el-table-column label="最新价" width="100">
            <template #default="{ row }">{{ (row.price || 0).toFixed(2) }}</template>
          </el-table-column>
          <el-table-column label="涨跌幅" width="100">
            <template #default="{ row }">
              <span :class="(row.change_pct || 0) >= 0 ? 'num-up' : 'num-down'">
                {{ (row.change_pct || 0).toFixed(2) }}%
              </span>
            </template>
          </el-table-column>
          <el-table-column label="市值(亿)" width="100">
            <template #default="{ row }">
              <span style="color: var(--text-secondary)">
                {{ (row.market_cap || 0).toFixed(0) }}
              </span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 龙虎榜 -->
      <div v-if="tab === 'lhb'">
        <div class="card p-3" style="border-bottom: 1px solid var(--border)">
          <span class="mono text-xs" style="color: var(--text-secondary)">
            龙虎榜数据 (前一交易日) | 来源: DB缓存 → AkShare
          </span>
        </div>
        <div v-if="lhbList" class="card mt-2">
          <el-table :data="[lhbList]" style="width: 100%">
            <el-table-column prop="date" label="日期" width="120" />
            <el-table-column label="涨停数" width="100">
              <template #default="{ row }"><span class="num-up">{{ row.total || 0 }}</span></template>
            </el-table-column>
            <el-table-column label="市场情绪" width="100">
              <template #default="{ row }">
                <span class="badge" :class="{
                  'badge-up': row.sentiment === '热' || row.sentiment === '极热',
                  'badge-down': row.sentiment === '冷',
                  'badge-warn': row.sentiment !== '热' && row.sentiment !== '极热' && row.sentiment !== '冷',
                }">{{ row.sentiment || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="热门股票">
              <template #default="{ row }">
                <div class="flex gap-1 flex-wrap">
                  <span v-for="(s, i) in (row.top_stocks || []).slice(0, 10)" :key="i"
                    class="mono text-xs px-2 py-0.5 rounded"
                    style="background: var(--bg-root); border: 1px solid var(--border)">
                    {{ s.name }}({{ s.code }}) {{ s.boards > 0 ? `${s.boards}板` : '' }}
                  </span>
                </div>
              </template>
            </el-table-column>
          </el-table>
        </div>
        <div v-else class="text-center py-16 mono text-sm" style="color: var(--text-muted)">加载中...</div>
      </div>

      <!-- 行业分布 -->
      <div v-if="tab === 'industry'" class="space-y-4">
        <div v-if="qualityData?.fields" class="card p-4">
          <div class="mono text-xs tracking-wider uppercase mb-3" style="color: var(--text-muted)">
            数据质量 ({{ qualityData.total }} stocks)
          </div>
          <div class="grid grid-cols-5 gap-3">
            <div v-for="(f, name) in qualityData.fields" :key="name" class="text-center">
              <div class="relative w-12 h-12 mx-auto mb-1">
                <svg viewBox="0 0 36 36" class="w-12 h-12 -rotate-90">
                  <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                    fill="none" stroke="var(--border)" stroke-width="3" />
                  <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                    fill="none" stroke-width="3"
                    :stroke="f.pct >= 80 ? 'var(--accent-green)' : f.pct >= 50 ? 'var(--accent-amber)' : 'var(--accent-red)'"
                    :stroke-dasharray="`${f.pct}, 100`" />
                </svg>
                <span class="absolute inset-0 flex items-center justify-center mono text-xs font-bold"
                  :style="{ color: f.pct >= 80 ? 'var(--accent-green)' : f.pct >= 50 ? 'var(--accent-amber)' : 'var(--accent-red)' }">
                  {{ f.pct }}%
                </span>
              </div>
              <div class="mono text-xs truncate" style="color: var(--text-secondary)">{{ name }}</div>
            </div>
          </div>
        </div>

        <div v-if="industryData?.industries?.length > 0" class="card p-4">
          <div class="flex items-center justify-between mb-3">
            <div class="flex items-center gap-2">
              <el-icon :size="14" style="color: var(--accent-blue)"><DataAnalysis /></el-icon>
              <span class="mono text-xs tracking-wider uppercase" style="color: var(--text-muted)">
                行业分布
              </span>
            </div>
            <span class="mono text-xs" style="color: var(--text-muted)">
              {{ industryData.total_with_industry }} covered / {{ industryData.total_no_industry }} missing
            </span>
          </div>
          <div v-for="(ind, i) in industryData.industries" :key="i"
            class="flex items-center gap-3 py-2"
            :style="{ borderBottom: i < industryData.industries.length - 1 ? '1px solid var(--border)' : 'none' }">
            <span class="mono text-xs w-20 truncate text-right" style="color: var(--text-secondary)">{{ ind.name }}</span>
            <div class="flex-1 h-4 rounded overflow-hidden" style="background: var(--bg-root)">
              <div class="h-full rounded flex items-center pl-2"
                :style="{
                  width: `${Math.max((ind.count / (industryData.industries[0]?.count || 1)) * 100, 8)}%`,
                  background: 'linear-gradient(90deg, var(--accent-blue), var(--accent-cyan))',
                  opacity: 0.8,
                }">
                <span class="mono text-xs font-bold text-white">{{ ind.count }}</span>
              </div>
            </div>
            <div class="flex gap-3 mono text-xs" style="color: var(--text-muted)">
              <span>PE {{ ind.avg_pe }}</span>
              <span>ROE {{ ind.avg_roe }}%</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 快照 -->
      <div v-if="tab === 'snapshots'" class="card p-4">
        <div v-for="(s, i) in snapshots" :key="i"
          class="flex justify-between py-2"
          :style="{ borderBottom: i < snapshots.length - 1 ? '1px solid var(--border)' : 'none' }">
          <span class="mono text-sm">{{ s.type }}</span>
          <span class="text-sm" style="color: var(--text-muted)">{{ s.updated }}</span>
        </div>
        <div v-if="snapshots.length === 0" class="text-center py-8" style="color: var(--text-muted)">暂无快照</div>
      </div>

      <!-- ═══ Data Browser ═══ -->
      <div v-if="tab === 'data-browser'" class="space-y-4">
        <!-- Filters -->
        <div class="card p-4">
          <el-form :inline="true" size="small" label-width="60px">
            <el-form-item label="Table">
              <el-select v-model="browser.table" style="width:160px" @change="onTableChange">
                <el-option v-for="t in TABLE_OPTIONS" :key="t.value" :label="t.label" :value="t.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="Date">
              <el-date-picker v-model="browser.exactDate" type="date" placeholder="Exact date"
                format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:150px" />
            </el-form-item>
            <el-form-item label="From">
              <el-date-picker v-model="browser.dateFrom" type="date" placeholder="From"
                format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:150px" />
            </el-form-item>
            <el-form-item label="To">
              <el-date-picker v-model="browser.dateTo" type="date" placeholder="To"
                format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:150px" />
            </el-form-item>
            <el-form-item label="Code">
              <el-input v-model="browser.code" placeholder="Filter code" style="width:120px" clearable />
            </el-form-item>
            <el-form-item label="Limit">
              <el-input-number v-model="browser.limit" :min="10" :max="1000" :step="50" style="width:100px" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="queryData" :loading="browser.loading">Query</el-button>
              <el-button @click="resetBrowser">Reset</el-button>
            </el-form-item>
          </el-form>
        </div>

        <!-- Results -->
        <div class="card p-4">
          <div class="flex justify-between items-center mb-3">
            <span class="text-sm">
              Results: <strong>{{ browser.total }}</strong> rows
              <span v-if="browser.columns.length > 0" class="text-xs text-gray-400">
                ({{ browser.columns.length }} columns)
              </span>
            </span>
            <span v-if="browser.lastQuery" class="text-xs text-gray-400">
              Last: {{ browser.lastQuery }}
            </span>
          </div>

          <!-- Loading -->
          <div v-if="browser.loading" class="text-center py-12">
            <el-icon class="is-loading" :size="24"><Loading /></el-icon>
            <div class="text-xs mt-2 text-gray-400">Querying...</div>
          </div>

          <!-- Error -->
          <div v-else-if="browser.error" class="text-center py-12">
            <el-icon :size="24" color="var(--accent-red)"><WarningFilled /></el-icon>
            <div class="text-xs mt-2" style="color: var(--accent-red)">{{ browser.error }}</div>
            <el-button size="small" class="mt-2" @click="queryData">Retry</el-button>
          </div>

          <!-- Empty -->
          <div v-else-if="browser.rows.length === 0" class="text-center py-12 text-gray-400">
            <el-icon :size="24"><Search /></el-icon>
            <div class="text-xs mt-2">No data for this query. Adjust filters and try again.</div>
          </div>

          <!-- Table -->
          <div v-else class="table-wrap">
            <el-table :data="browser.rows" border stripe size="small" max-height="500"
              style="width:100%" @row-click="handleRowClick">
              <el-table-column v-for="col in browser.columns" :key="col"
                :prop="col" :label="col" :min-width="120" show-overflow-tooltip>
                <template #default="{ row }">
                  <span class="mono text-xs">{{ formatCell(row[col]) }}</span>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <!-- Pagination -->
          <div v-if="browser.total > browser.limit" class="flex justify-center mt-3">
            <el-pagination
              v-model:current-page="browser.page"
              :page-size="browser.limit"
              :total="browser.total"
              layout="prev, pager, next"
              small
              @current-change="onPageChange"
            />
          </div>
        </div>
      </div>

      <!-- 添加弹窗 -->
      <el-dialog v-model="adding" title="添加股票" width="480px">
        <el-form @submit.prevent="handleAdd">
          <el-form-item label="股票代码" required>
            <el-input v-model="newStock.code" placeholder="如 600519" />
          </el-form-item>
          <el-form-item label="股票名称">
            <el-input v-model="newStock.name" placeholder="如 贵州茅台" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="adding = false">取消</el-button>
          <el-button type="primary" @click="handleAdd">添加并填充数据</el-button>
        </template>
      </el-dialog>

      <!-- 编辑弹窗 -->
      <el-dialog v-model="showEditDialog" :title="`编辑 ${editing?.stock_code}`" width="480px" @close="editing = null">
        <el-form v-if="editing" @submit.prevent="handleEdit">
          <el-form-item label="名称"><el-input v-model="editForm.stock_name" /></el-form-item>
          <el-form-item label="最新价"><el-input-number v-model="editForm.latest_price" :precision="2" /></el-form-item>
          <el-form-item label="PE"><el-input-number v-model="editForm.pe_ratio" :precision="1" /></el-form-item>
          <el-form-item label="PB"><el-input-number v-model="editForm.pb_ratio" :precision="1" /></el-form-item>
          <el-form-item label="换手率%"><el-input-number v-model="editForm.turnover_rate" :precision="1" /></el-form-item>
          <el-form-item label="行业"><el-input v-model="editForm.industry" /></el-form-item>
          <el-form-item label="趋势"><el-input v-model="editForm.trend" /></el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="editing = null">取消</el-button>
          <el-button type="primary" @click="handleEdit">保存</el-button>
        </template>
      </el-dialog>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, nextTick, onBeforeUnmount, onMounted, watch } from 'vue'
import { get, post, put, del } from '@/api/request'
import { dbApi } from '@/api/legacy'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Folder, Refresh, Plus, Search, Edit, Delete, DataAnalysis,
  Connection, Clock, WarningFilled, FolderOpened, Loading,
} from '@element-plus/icons-vue'
import * as echarts from 'echarts'

const stats = ref<any>(null)
const stocks = ref<any[]>([])
const total = ref(0)
const loading = ref(false)
const search = ref('')
const sort = ref('stock_code')
const order = ref('asc')
const page = ref(1)
const tab = ref('stockinfo')
const hotStocks = ref<any[]>([])
const snapshots = ref<any[]>([])
const lhbList = ref<any>(null)
const industryData = ref<any>(null)
const qualityData = ref<any>(null)
const sourceTest = ref<any>({ loading: true })
const adding = ref(false)
const editing = ref<any>(null)
const refreshingHot = ref(false)
const refreshingFull = ref(false)
const showEditDialog = ref(false)
const repairing = ref(false)
const cleaning = ref(false)
const clearingCache = ref(false)

const newStock = reactive({ code: '', name: '' })
const editForm = reactive({
  stock_name: '', latest_price: 0, pe_ratio: 0, pb_ratio: 0,
  turnover_rate: 0, industry: '', trend: '',
})

// ── 图表 ──
const freshnessChartRef = ref<HTMLElement>()
const coverageChartRef = ref<HTMLElement>()
let freshnessChart: echarts.ECharts | null = null
let coverageChart: echarts.ECharts | null = null
let resizeHandler: (() => void) | null = null

const freshnessHours = computed(() => {
  if (!stats.value?.latest_update) return 999
  const diff = Date.now() - new Date(stats.value.latest_update).getTime()
  return Math.round(diff / 3600000)
})

const fieldLabel = (name: string) => {
  const labels: Record<string, string> = {
    'stock_name': '名称', 'latest_price': '最新价', 'pe_ratio': 'PE',
    'roe': 'ROE', 'industry': '行业', 'total_market_cap': '总市值',
    'eps': 'EPS', 'bvps': 'BVPS', 'gross_margin': '毛利率',
    'debt_to_equity': '负债率', 'free_cash_flow': '自由现金流',
    'dividend_yield': '股息率', 'ma5': 'MA5', 'rsi_14': 'RSI', 'trend': '趋势',
  }
  return labels[name] || name
}

function safeDispose(chart: echarts.ECharts | null) {
  try { chart?.dispose() } catch {}
}

function initCharts() {
  // Gauge chart
  if (freshnessChartRef.value) {
    safeDispose(freshnessChart)
    try {
      const hours = freshnessHours.value
      freshnessChart = echarts.init(freshnessChartRef.value, undefined, { width: 'auto', height: 'auto' })
      freshnessChart.setOption({
        series: [{
          type: 'gauge', min: 0, max: 72,
          center: ['50%', '55%'], radius: '90%',
          axisLine: { lineStyle: { width: 18, color: [[0.083, '#10b981'], [0.333, '#f59e0b'], [1, '#ef4444']] }},
          axisTick: { show: false },
          splitLine: { length: 12, lineStyle: { width: 2, color: '#2a3a5a' }},
          axisLabel: { fontSize: 9, color: '#5a6a8a', distance: 8, formatter: (v: number) => v + 'h' },
          pointer: { width: 4, length: '60%' },
          detail: { formatter: (p: any) => p.value.toFixed(0) + 'h', fontSize: 22, fontWeight: 700, color: hours <= 6 ? '#10b981' : hours <= 24 ? '#f59e0b' : '#ef4444', offsetCenter: [0, '30%'] },
          title: { offsetCenter: [0, '55%'], fontSize: 11, color: '#5a6a8a' },
          data: [{ value: Math.min(hours, 72), name: '距上次更新' }]
        }]
      })
    } catch (e) { console.error('Gauge chart init failed:', e) }
  }

  // Rose chart
  if (coverageChartRef.value && qualityData.value?.fields) {
    safeDispose(coverageChart)
    try {
      coverageChart = echarts.init(coverageChartRef.value, undefined, { width: 'auto', height: 'auto' })
      const data = Object.entries(qualityData.value.fields)
        .filter(([_, f]: any) => f.pct > 0)
        .map(([name, f]: any) => ({
          name: fieldLabel(name),
          value: f.pct,
          itemStyle: { color: f.pct >= 80 ? '#10b981' : f.pct >= 50 ? '#f59e0b' : '#ef4444' }
        }))
      coverageChart.setOption({
        tooltip: { trigger: 'item', formatter: '{b}: {c}% ({d}%)' },
        series: [{
          type: 'pie', radius: ['25%', '75%'], roseType: 'area',
          itemStyle: { borderRadius: 4 },
          label: { formatter: '{b}: {c}%', fontSize: 11, color: '#8892b0' },
          labelLine: { lineStyle: { color: '#1e2d4a' }},
          data,
        }]
      })
    } catch (e) { console.error('Rose chart init failed:', e) }
  }
}

// ── 管道状态 ──
const pipelineStages = computed(() => [
  { key: 'stocks', label: '股票', count: stats.value?.stock_count || 0, active: (stats.value?.stock_count || 0) > 0 },
  { key: 'klines', label: 'K线', count: stats.value?.kline_count || 0, active: (stats.value?.kline_count || 0) > 0 },
  { key: 'snapshots', label: '快照', count: stats.value?.snapshot_count || 0, active: (stats.value?.snapshot_count || 0) > 0 },
  { key: 'hot', label: '热榜', count: hotStocks.value?.length || 0, active: (hotStocks.value?.length || 0) > 0 },
  { key: 'industry', label: '行业', count: industryData.value?.industries?.length || 0, active: (industryData.value?.industries?.length || 0) > 0 },
  { key: 'lhb', label: '龙虎榜', count: lhbList.value?.total || 0, active: !!lhbList.value },
])

const pipelineScore = computed(() => {
  const s = stats.value
  if (!s) return { pct: 0, color: 'var(--text-muted)' }
  const total = 3
  let score = 0
  if (s.stock_count > 0) score++
  if (s.kline_count > 0) score++
  if (s.snapshot_count > 0) score++
  const pct = Math.round((score / total) * 100)
  return {
    pct,
    color: pct >= 66 ? 'var(--accent-green)' : pct >= 33 ? 'var(--accent-amber)' : 'var(--accent-red)',
  }
})

const needsRefresh = computed(() => stats.value?.needs_refresh)
const refreshHint = computed(() => stats.value?.refresh_hint || '')

const dbSize = computed(() => {
  const mb = stats.value?.db_size_mb
  if (mb === undefined || mb === null) return '--'
  return mb < 1 ? `${Math.round(mb * 1024)}KB` : `${mb.toFixed(1)}MB`
})

// ── 数据加载 ──
const runSourceTest = async () => {
  sourceTest.value = { loading: true }
  try {
    const data = await get('/api/db/source-test')
    sourceTest.value = data
  } catch (error: any) {
    sourceTest.value = { error: error.message, sources: null }
  }
}

const fetchData = async () => {
  loading.value = true
  try {
    // 1. 总是加载 stats (快速, 仅DB查询)
    stats.value = await get('/api/db/stats')
  } catch (error) {
    console.error('Stats failed:', error)
  }

  // 2. 总是加载 qualityData (供顶部质量面板使用)
  try {
    qualityData.value = await get('/api/db/data-quality')
  } catch (error) {
    console.error('Quality data failed:', error)
  }

  // 3. 按当前tab加载特定数据 (每个独立catch, 互不影响)
  if (tab.value === 'stockinfo') {
    try {
      const d = await get(`/api/db/stockinfo?search=${search.value}&sort=${sort.value}&order=${order.value}&page=${page.value}&limit=50`)
      stocks.value = d.stocks || []
      total.value = d.total || 0
    } catch (error) {
      console.error('Stockinfo failed:', error)
    }
  }

  if (tab.value === 'snapshots') {
    try {
      const d = await get('/api/db/snapshots')
      snapshots.value = d.snapshots || []
    } catch (error) {
      console.error('Snapshots failed:', error)
    }
  }

  if (tab.value === 'hotstocks') {
    try {
      const d = await get('/api/db/hot-stocks?limit=100')
      hotStocks.value = d.stocks || []
    } catch (error) {
      console.error('Hot stocks failed:', error)
    }
  }

  if (tab.value === 'lhb') {
    try {
      lhbList.value = await get('/api/db/lhb')
    } catch (error) {
      console.error('LHB failed:', error)
    }
  }

  if (tab.value === 'industry') {
    try {
      industryData.value = await get('/api/db/industry-distribution?limit=30')
    } catch (error) {
      console.error('Industry distribution failed:', error)
    }
  }

  loading.value = false
  // 确保数据加载后图表初始化
  safeInitCharts()
}

const handleRefresh = async (mode: string, codes?: string[]) => {
  const setter = mode === 'full' ? refreshingFull : refreshingHot
  setter.value = true
  try {
    await post('/api/db/refresh', { mode: mode || 'hot', codes: codes || [] })
    await fetchData()
    ElMessage.success(mode === 'full' ? '全市场刷新完成' : '热榜刷新完成')
  } catch (e: any) {
    ElMessage.error('刷新失败: ' + (e.message || ''))
  } finally {
    setter.value = false
  }
}

const handleClearCache = async () => {
  clearingCache.value = true
  try {
    await post('/api/db/refresh', { mode: 'clean-stale' })
    await fetchData()
    ElMessage.success('缓存已刷新')
  } catch {
    ElMessage.error('缓存刷新失败')
  } finally {
    clearingCache.value = false
  }
}

const handleAdd = async () => {
  if (!newStock.code.trim()) return
  try {
    const r = await post('/api/db/stockinfo', {
      stock_code: newStock.code.trim(),
      stock_name: newStock.name.trim() || newStock.code.trim(),
    })
    if (r.ok) {
      adding.value = false
      await post('/api/db/refresh', { mode: 'hot', codes: [newStock.code.trim()] })
      await fetchData()
      ElMessage.success('添加成功')
    } else {
      ElMessage.warning(r.error || '添加失败')
    }
  } catch (error) {
    ElMessage.error('添加失败')
  }
}

const handleEdit = async () => {
  if (!editing.value) return
  try {
    const r = await put(`/api/db/stockinfo/${editing.value.stock_code}`, editForm)
    if (r.ok) {
      editing.value = null
      showEditDialog.value = false
      await fetchData()
      ElMessage.success('保存成功')
    }
  } catch (error) {
    ElMessage.error('保存失败')
  }
}

const handleDelete = async (code: string) => {
  try {
    await ElMessageBox.confirm(`确定删除 ${code}?`, '确认删除', { type: 'warning' })
    const r = await del(`/api/db/stockinfo/${code}`)
    if (r.ok) {
      await fetchData()
      ElMessage.success('删除成功')
    }
  } catch {
    // 用户取消
  }
}

const handleBatchRepair = async () => {
  repairing.value = true
  try {
    const r = await post('/api/db/batch-repair')
    ElMessage.success(`修复完成: ${r.repaired || 0} 条已修复, ${r.still_broken || 0} 条仍异常`)
  } catch {
    ElMessage.error('批量修复失败')
  } finally {
    repairing.value = false
    fetchData()
  }
}

const handleCleanStale = async () => {
  cleaning.value = true
  try {
    const r = await post('/api/db/clean-stale')
    ElMessage.success(`清理完成: 删除 ${r.deleted || 0} 条空壳数据`)
  } catch {
    ElMessage.error('清理失败')
  } finally {
    cleaning.value = false
    fetchData()
  }
}

const handleSearch = () => { page.value = 1; fetchData() }
const handleSortChange = ({ prop, order: o }: any) => {
  sort.value = prop
  order.value = o === 'ascending' ? 'asc' : 'desc'
  fetchData()
}
const handleTabChange = () => { fetchData() }

const openEdit = (row: any) => {
  editing.value = row
  showEditDialog.value = true
  Object.assign(editForm, {
    stock_name: row.stock_name || '',
    latest_price: row.latest_price || 0,
    pe_ratio: row.pe_ratio || 0,
    pb_ratio: row.pb_ratio || 0,
    turnover_rate: row.turnover_rate || 0,
    industry: row.industry || '',
    trend: row.trend || '',
  })
}

// ── Date Browser ──

interface BrowserState {
  table: string
  exactDate: string | null
  dateFrom: string | null
  dateTo: string | null
  code: string
  limit: number
  page: number
  offset: number
  loading: boolean
  error: string | null
  total: number
  columns: string[]
  rows: any[]
  lastQuery: string | null
}

const TABLE_OPTIONS = [
  { value: 'stock_info', label: 'Stock Info' },
  { value: 'kline_cache', label: 'K-Line Cache' },
  { value: 'fund_metric_hist', label: 'Financial History' },
  { value: 'market_snapshot', label: 'Market Snapshot' },
  { value: 'daily_nav', label: 'Daily NAV' },
  { value: 'portfolio', label: 'Portfolio' },
  { value: 'trade_records', label: 'Trade Records' },
  { value: 'orders', label: 'Orders' },
  { value: 'trades', label: 'Trades' },
  { value: 'style_signal', label: 'Style Signals' },
  { value: 'screen_result', label: 'Screen Results' },
  { value: 'dragon_tiger', label: 'Dragon Tiger' },
  { value: 'system_logs', label: 'System Logs' },
]

const browser = reactive<BrowserState>({
  table: 'stock_info',
  exactDate: null,
  dateFrom: null,
  dateTo: null,
  code: '',
  limit: 100,
  page: 1,
  offset: 0,
  loading: false,
  error: null,
  total: 0,
  columns: [],
  rows: [],
  lastQuery: null,
})

function formatCell(val: any): string {
  if (val === null || val === undefined) return '-'
  if (typeof val === 'object') return JSON.stringify(val).slice(0, 100)
  return String(val)
}

function handleRowClick(row: any) {
  // Could expand to show details
}

async function queryData() {
  browser.loading = true
  browser.error = null
  try {
    const params: any = {
      table: browser.table,
      limit: browser.limit,
      offset: browser.offset,
    }
    if (browser.exactDate) params.date = browser.exactDate
    if (browser.dateFrom && !browser.exactDate) params.date_from = browser.dateFrom
    if (browser.dateTo && !browser.exactDate) params.date_to = browser.dateTo
    if (browser.code) params.code = browser.code

    browser.lastQuery = `${browser.table} (offset=${browser.offset}, limit=${browser.limit})`

    const res = await dbApi.getDataByDate(params) as any
    browser.rows = res.rows || []
    browser.total = res.total || 0
    browser.columns = res.columns || []
  } catch (e: any) {
    browser.error = e.message || 'Query failed'
    browser.rows = []
  } finally {
    browser.loading = false
  }
}

function onTableChange() {
  resetBrowser()
}

function onPageChange(page: number) {
  browser.page = page
  browser.offset = (page - 1) * browser.limit
  queryData()
}

function resetBrowser() {
  browser.exactDate = null
  browser.dateFrom = null
  browser.dateTo = null
  browser.code = ''
  browser.limit = 100
  browser.page = 1
  browser.offset = 0
  browser.total = 0
  browser.columns = []
  browser.rows = []
  browser.error = null
  browser.loading = false
  browser.lastQuery = null
}

function safeInitCharts() {
  nextTick(() => {
    // requestAnimationFrame ensures browser has performed layout (critical for v-show transition)
    requestAnimationFrame(() => { requestAnimationFrame(() => { initCharts() }) })
  })
}

watch([stats, qualityData], safeInitCharts)
onMounted(() => {
  resizeHandler = () => { freshnessChart?.resize(); coverageChart?.resize() }
  window.addEventListener('resize', resizeHandler)
  fetchData()
  runSourceTest()
})
onBeforeUnmount(() => {
  if (resizeHandler) window.removeEventListener('resize', resizeHandler)
  freshnessChart?.dispose()
  coverageChart?.dispose()
})
</script>

<style lang="scss" scoped>
.database-container {
  .mono { font-family: 'JetBrains Mono', monospace; }
}

// ── 数据质量面板 ──
.quality-panel {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}

.quality-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}

.quality-title {
  font-size: 13px;
  font-weight: 600;
  font-family: 'JetBrains Mono', monospace;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-primary);
}

.quality-date {
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
  color: var(--accent-cyan);
}

.quality-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0;

  @media (max-width: 768px) {
    grid-template-columns: 1fr;
  }
}

// 左侧仪表盘
.quality-gauge {
  padding: 16px;
  border-right: 1px solid var(--border);

  @media (max-width: 768px) {
    border-right: none;
    border-bottom: 1px solid var(--border);
  }
}

.gauge-label {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 4px;
}

.gauge-value {
  font-size: 11px;
  color: var(--text-secondary);
  text-transform: none;
  letter-spacing: 0;
}

.gauge-chart {
  height: 240px;
  width: 100%;
}

.gauge-footer {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
  color: var(--text-muted);
  padding-top: 4px;
}

// 右侧字段完整度
.quality-details {
  padding: 16px;
}

.quality-detail-header {
  font-size: 10px;
  font-family: 'JetBrains Mono', monospace;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  margin-bottom: 10px;
}

.quality-field-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.quality-field-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.qf-label {
  width: 60px;
  font-size: 10px;
  font-family: 'JetBrains Mono', monospace;
  color: var(--text-secondary);
  text-align: right;
  flex-shrink: 0;
}

.qf-track {
  flex: 1;
  height: 8px;
  background: var(--bg-surface);
  border-radius: 4px;
  overflow: hidden;
}

.qf-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.5s ease;
  min-width: 2%;
}

.qf-pct {
  width: 36px;
  text-align: right;
  font-size: 10px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
}

.qf-nums {
  width: 64px;
  text-align: right;
  font-size: 9px;
  font-family: 'JetBrains Mono', monospace;
  color: var(--text-muted);
}

.quality-empty {
  padding: 30px 0;
  text-align: center;
}
</style>
