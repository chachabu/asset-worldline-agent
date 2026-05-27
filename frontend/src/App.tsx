import {
  Activity,
  BarChart3,
  Bot,
  Database,
  FileText,
  Globe2,
  LayoutDashboard,
  LogOut,
  Play,
  Shield,
  SlidersHorizontal,
  Target,
} from 'lucide-react';
import { FormEvent, ReactNode, useEffect, useMemo, useState } from 'react';
import { apiGet, apiPost, apiPut } from './api/client';

type User = { id: number; username: string };
type NavKey =
  | 'overview'
  | 'sources'
  | 'news'
  | 'scoring'
  | 'assets'
  | 'forecasts'
  | 'models'
  | 'system';

type InformationSource = {
  id: number;
  name: string;
  source_type: string;
  entry_url: string;
  fetch_mode: string;
  source_weight: number;
  fetch_frequency_minutes: number;
  enabled: boolean;
  last_status: string;
  last_error: string | null;
};

type SourceCandidate = {
  title: string;
  url: string;
  snippet?: string | null;
  status: string;
  error?: string | null;
};

type AssetGroup = {
  id: number;
  name: string;
  category: string;
  region: string;
  assets: Array<{
    id: number;
    symbol: string;
    display_name: string;
    market: string;
    asset_type: string;
    role: string;
  }>;
};

type Forecast = {
  id: number;
  branch: string;
  asset_group: string;
  region: string;
  horizon: string;
  direction: string;
  confidence: number | null;
  base_target: number | null;
  bull_target: number | null;
  bear_target: number | null;
  rationale: string | null;
};

type ModelConfig = {
  role: string;
  provider: string;
  model_name: string;
  temperature: number;
  max_tokens: number;
  timeout_seconds: number;
  enabled: boolean;
};

type Job = {
  id: number;
  job_type: string;
  status: string;
  priority: number;
  scheduled_at: string;
  error_message: string | null;
};

type Overview = {
  sources: { total: number; enabled: number };
  events: { clusters: number; scores: number };
  jobs: { pending: number; failed: number };
  latest_prediction_run: { id: number; status: string; created_at: string } | null;
  latest_forecasts: Forecast[];
};

const navItems: Array<{ key: NavKey; label: string; icon: typeof LayoutDashboard }> = [
  { key: 'overview', label: '总览', icon: LayoutDashboard },
  { key: 'sources', label: '信息源', icon: Globe2 },
  { key: 'news', label: '新闻池', icon: FileText },
  { key: 'scoring', label: '人工评分', icon: Target },
  { key: 'assets', label: '资产池', icon: Database },
  { key: 'forecasts', label: '预测矩阵', icon: BarChart3 },
  { key: 'models', label: '模型配置', icon: Bot },
  { key: 'system', label: '系统状态', icon: Activity },
];

const emptySource = {
  name: '',
  source_type: 'financial_news',
  entry_url: '',
  fetch_mode: 'list_page',
  language: '',
  region: '',
  default_tags: [],
  source_weight: 1,
  fetch_frequency_minutes: 180,
  requires_browser: false,
  enabled: true,
  selectors: {},
  url_rules: {},
};

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [active, setActive] = useState<NavKey>('overview');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiGet<User>('/auth/me')
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="boot">Asset Worldline Agent</div>;
  }

  if (!user) {
    return <LoginPage onLogin={setUser} />;
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <Shield size={22} />
          <div>
            <strong>Worldline</strong>
            <span>Asset Forecast Desk</span>
          </div>
        </div>
        <nav>
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                className={active === item.key ? 'nav-item active' : 'nav-item'}
                key={item.key}
                onClick={() => setActive(item.key)}
                type="button"
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
        <button
          className="nav-item logout"
          type="button"
          onClick={() => {
            apiPost('/auth/logout').finally(() => setUser(null));
          }}
        >
          <LogOut size={18} />
          <span>{user.username}</span>
        </button>
      </aside>
      <main className="content">
        {active === 'overview' && <OverviewPage />}
        {active === 'sources' && <SourcesPage />}
        {active === 'news' && <NewsPage />}
        {active === 'scoring' && <ScoringPage />}
        {active === 'assets' && <AssetsPage />}
        {active === 'forecasts' && <ForecastsPage />}
        {active === 'models' && <ModelsPage />}
        {active === 'system' && <SystemPage />}
      </main>
    </div>
  );
}

function LoginPage({ onLogin }: { onLogin: (user: User) => void }) {
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      onLogin(await apiPost<User>('/auth/login', { username, password }));
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败');
    }
  }

  return (
    <div className="login-screen">
      <form className="login-panel" onSubmit={submit}>
        <div className="brand compact">
          <Shield size={24} />
          <div>
            <strong>Asset Worldline Agent</strong>
            <span>Research Dashboard</span>
          </div>
        </div>
        <label>
          用户名
          <input value={username} onChange={(event) => setUsername(event.target.value)} />
        </label>
        <label>
          密码
          <input
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            type="password"
            autoFocus
          />
        </label>
        {error && <div className="error">{error}</div>}
        <button className="primary" type="submit">
          登录
        </button>
      </form>
    </div>
  );
}

function OverviewPage() {
  const [overview, setOverview] = useState<Overview | null>(null);

  useEffect(() => {
    apiGet<Overview>('/overview').then(setOverview);
  }, []);

  return (
    <Page title="总览" subtitle="新闻、任务、预测运行和分支状态。">
      <div className="metric-grid">
        <Metric label="信息源" value={`${overview?.sources.enabled ?? 0}/${overview?.sources.total ?? 0}`} />
        <Metric label="事件簇" value={overview?.events.clusters ?? 0} />
        <Metric label="评分数" value={overview?.events.scores ?? 0} />
        <Metric label="待处理任务" value={overview?.jobs.pending ?? 0} />
        <Metric label="失败任务" value={overview?.jobs.failed ?? 0} tone="bad" />
      </div>
      <section className="panel">
        <h2>最近预测</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>资产</th>
                <th>分支</th>
                <th>区域</th>
                <th>周期</th>
                <th>方向</th>
                <th>目标价</th>
                <th>置信度</th>
              </tr>
            </thead>
            <tbody>
              {(overview?.latest_forecasts ?? []).map((forecast) => (
                <tr key={forecast.id}>
                  <td>{forecast.asset_group}</td>
                  <td>{forecast.branch}</td>
                  <td>{forecast.region}</td>
                  <td>{forecast.horizon}</td>
                  <td>
                    <Badge value={forecast.direction} />
                  </td>
                  <td>{formatPrice(forecast.base_target)}</td>
                  <td>{formatPercent(forecast.confidence)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </Page>
  );
}

function SourcesPage() {
  const [sources, setSources] = useState<InformationSource[]>([]);
  const [form, setForm] = useState(emptySource);
  const [candidates, setCandidates] = useState<SourceCandidate[]>([]);
  const [message, setMessage] = useState<string | null>(null);

  const load = () => apiGet<InformationSource[]>('/sources').then(setSources);

  useEffect(() => {
    load();
  }, []);

  async function createSource(event: FormEvent) {
    event.preventDefault();
    setMessage(null);
    await apiPost('/sources', form);
    setForm(emptySource);
    setMessage('信息源已保存');
    load();
  }

  async function testSource() {
    setMessage(null);
    const result = await apiPost<SourceCandidate[]>('/sources/test', {
      entry_url: form.entry_url,
      fetch_mode: form.fetch_mode,
      selectors: form.selectors,
    });
    setCandidates(result);
  }

  return (
    <Page title="信息源" subtitle="添加具体网站、测试抓取和查看来源状态。">
      <section className="panel">
        <h2>新增网站</h2>
        <form className="source-form" onSubmit={createSource}>
          <input
            placeholder="名称"
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
          />
          <select
            value={form.source_type}
            onChange={(event) => setForm({ ...form, source_type: event.target.value })}
          >
            <option value="financial_news">财经新闻</option>
            <option value="research">机构观点/研报</option>
            <option value="announcement">公司公告/IR</option>
            <option value="policy">政策/监管/央行</option>
            <option value="industry_data">行业协会/产业数据</option>
            <option value="other">其他</option>
          </select>
          <select
            value={form.fetch_mode}
            onChange={(event) => setForm({ ...form, fetch_mode: event.target.value })}
          >
            <option value="list_page">列表页</option>
            <option value="rss">RSS</option>
            <option value="article">单篇文章</option>
            <option value="pdf">PDF</option>
          </select>
          <input
            className="wide-input"
            placeholder="入口 URL"
            value={form.entry_url}
            onChange={(event) => setForm({ ...form, entry_url: event.target.value })}
          />
          <button className="secondary" type="button" onClick={testSource}>
            测试抓取
          </button>
          <button className="primary" type="submit">
            保存
          </button>
        </form>
        {message && <div className="success">{message}</div>}
        {candidates.length > 0 && (
          <div className="table-wrap compact-table">
            <table>
              <thead>
                <tr>
                  <th>标题</th>
                  <th>状态</th>
                  <th>片段</th>
                </tr>
              </thead>
              <tbody>
                {candidates.slice(0, 10).map((candidate) => (
                  <tr key={candidate.url}>
                    <td>
                      <a href={candidate.url} target="_blank" rel="noreferrer">
                        {candidate.title}
                      </a>
                    </td>
                    <td>{candidate.status}</td>
                    <td>{candidate.snippet}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <section className="panel">
        <h2>已配置网站</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>类型</th>
                <th>模式</th>
                <th>频率</th>
                <th>状态</th>
                <th>URL</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((source) => (
                <tr key={source.id}>
                  <td>{source.name}</td>
                  <td>{source.source_type}</td>
                  <td>{source.fetch_mode}</td>
                  <td>{source.fetch_frequency_minutes}m</td>
                  <td>
                    <Badge value={source.last_status} />
                  </td>
                  <td className="url-cell">{source.entry_url}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </Page>
  );
}

function NewsPage() {
  const [clusters, setClusters] = useState<any[]>([]);

  useEffect(() => {
    apiGet<any[]>('/news/clusters').then(setClusters);
  }, []);

  return (
    <Page title="新闻池" subtitle="去重后的事件簇会进入人工评分和自动评分分支。">
      <section className="panel">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>事件</th>
                <th>来源数</th>
                <th>来源类型</th>
                <th>涉及主题</th>
                <th>摘要</th>
              </tr>
            </thead>
            <tbody>
              {clusters.map((cluster) => (
                <tr key={cluster.id}>
                  <td>{cluster.canonical_title}</td>
                  <td>{cluster.source_count}</td>
                  <td>{cluster.source_types?.join(', ')}</td>
                  <td>{cluster.involved_themes?.join(', ')}</td>
                  <td>{cluster.summary}</td>
                </tr>
              ))}
              {clusters.length === 0 && <EmptyRow columns={5} text="暂无事件簇" />}
            </tbody>
          </table>
        </div>
      </section>
    </Page>
  );
}

function ScoringPage() {
  const [clusters, setClusters] = useState<any[]>([]);
  const [saving, setSaving] = useState<number | null>(null);

  useEffect(() => {
    apiGet<any[]>('/news/clusters').then(setClusters);
  }, []);

  async function score(clusterId: number, importance: number) {
    setSaving(clusterId);
    await apiPost(`/news/clusters/${clusterId}/human-score`, {
      importance,
      direction: 'uncertain',
      impact_horizons: ['1W', '1M', '3M'],
      affected_groups: [],
      affected_assets: [],
      reason: '',
    });
    setSaving(null);
  }

  return (
    <Page title="人工评分" subtitle="人工分支只使用这里评分过且分数大于 0 的事件。">
      <section className="panel">
        <div className="scoring-list">
          {clusters.map((cluster) => (
            <div className="score-row" key={cluster.id}>
              <div>
                <strong>{cluster.canonical_title}</strong>
                <span>{cluster.summary || '无摘要'}</span>
              </div>
              <div className="score-buttons">
                {[0, 1, 2, 3, 4, 5].map((value) => (
                  <button
                    key={value}
                    className="score-button"
                    type="button"
                    disabled={saving === cluster.id}
                    onClick={() => score(cluster.id, value)}
                  >
                    {value}
                  </button>
                ))}
              </div>
            </div>
          ))}
          {clusters.length === 0 && <div className="empty">暂无待评分事件</div>}
        </div>
      </section>
    </Page>
  );
}

function AssetsPage() {
  const [groups, setGroups] = useState<AssetGroup[]>([]);

  useEffect(() => {
    apiGet<AssetGroup[]>('/assets/groups').then(setGroups);
  }, []);

  const grouped = useMemo(() => {
    return groups.reduce<Record<string, AssetGroup[]>>((acc, group) => {
      acc[group.category] = [...(acc[group.category] ?? []), group];
      return acc;
    }, {});
  }, [groups]);

  return (
    <Page title="资产池" subtitle="展示对象绑定 primary/supporting proxy，用于目标价和复盘。">
      {Object.entries(grouped).map(([category, items]) => (
        <section className="panel" key={category}>
          <h2>{category}</h2>
          <div className="asset-grid">
            {items.map((group) => (
              <article className="asset-card" key={group.id}>
                <header>
                  <strong>{group.name}</strong>
                  <Badge value={group.region} />
                </header>
                <div className="proxy-list">
                  {group.assets.map((asset) => (
                    <span key={asset.id} className={asset.role === 'primary' ? 'proxy primary-proxy' : 'proxy'}>
                      {asset.symbol}
                    </span>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </section>
      ))}
    </Page>
  );
}

function ForecastsPage() {
  const [forecasts, setForecasts] = useState<Forecast[]>([]);
  const [branch, setBranch] = useState<'model_scored' | 'human_scored'>('model_scored');

  const load = () => apiGet<Forecast[]>('/forecasts/matrix').then(setForecasts);

  useEffect(() => {
    load();
  }, []);

  async function runPrediction() {
    await apiPost(`/forecasts/runs?branch_name=${branch}`);
  }

  return (
    <Page title="预测矩阵" subtitle="按分支、资产和 1W/1M/3M 查看目标价推演。">
      <div className="toolbar">
        <select value={branch} onChange={(event) => setBranch(event.target.value as any)}>
          <option value="model_scored">自动评分分支</option>
          <option value="human_scored">人工评分分支</option>
        </select>
        <button className="primary inline" type="button" onClick={runPrediction}>
          <Play size={16} />
          运行预测任务
        </button>
        <button className="secondary" type="button" onClick={load}>
          刷新
        </button>
      </div>
      <section className="panel">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>资产/板块</th>
                <th>分支</th>
                <th>区域</th>
                <th>周期</th>
                <th>方向</th>
                <th>基准</th>
                <th>上行</th>
                <th>下行</th>
                <th>理由</th>
              </tr>
            </thead>
            <tbody>
              {forecasts.map((forecast) => (
                <tr key={forecast.id}>
                  <td>{forecast.asset_group}</td>
                  <td>{forecast.branch}</td>
                  <td>{forecast.region}</td>
                  <td>{forecast.horizon}</td>
                  <td>
                    <Badge value={forecast.direction} />
                  </td>
                  <td>{formatPrice(forecast.base_target)}</td>
                  <td>{formatPrice(forecast.bull_target)}</td>
                  <td>{formatPrice(forecast.bear_target)}</td>
                  <td>{forecast.rationale}</td>
                </tr>
              ))}
              {forecasts.length === 0 && <EmptyRow columns={9} text="暂无预测，先运行预测任务" />}
            </tbody>
          </table>
        </div>
      </section>
    </Page>
  );
}

function ModelsPage() {
  const [configs, setConfigs] = useState<ModelConfig[]>([]);

  const load = () => apiGet<ModelConfig[]>('/model-configs').then(setConfigs);

  useEffect(() => {
    load();
  }, []);

  async function update(config: ModelConfig) {
    await apiPut(`/model-configs/${config.role}`, config);
    load();
  }

  return (
    <Page title="模型配置" subtitle="配置各角色使用的 provider/model。API Key 从服务器环境变量读取。">
      <section className="panel">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>角色</th>
                <th>Provider</th>
                <th>Model</th>
                <th>温度</th>
                <th>Token</th>
                <th>状态</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {configs.map((config, index) => (
                <tr key={config.role}>
                  <td>{config.role}</td>
                  <td>
                    <input
                      value={config.provider}
                      onChange={(event) =>
                        setConfigs(replaceAt(configs, index, { ...config, provider: event.target.value }))
                      }
                    />
                  </td>
                  <td>
                    <input
                      value={config.model_name}
                      onChange={(event) =>
                        setConfigs(replaceAt(configs, index, { ...config, model_name: event.target.value }))
                      }
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      step="0.1"
                      value={config.temperature}
                      onChange={(event) =>
                        setConfigs(
                          replaceAt(configs, index, { ...config, temperature: Number(event.target.value) }),
                        )
                      }
                    />
                  </td>
                  <td>{config.max_tokens}</td>
                  <td>{config.enabled ? '启用' : '停用'}</td>
                  <td>
                    <button className="secondary" type="button" onClick={() => update(config)}>
                      保存
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </Page>
  );
}

function SystemPage() {
  const [jobs, setJobs] = useState<Job[]>([]);

  useEffect(() => {
    apiGet<Job[]>('/jobs').then(setJobs);
  }, []);

  return (
    <Page title="系统状态" subtitle="后台任务、失败原因和调度状态。">
      <section className="panel">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>类型</th>
                <th>状态</th>
                <th>优先级</th>
                <th>计划时间</th>
                <th>错误</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id}>
                  <td>{job.id}</td>
                  <td>{job.job_type}</td>
                  <td>
                    <Badge value={job.status} />
                  </td>
                  <td>{job.priority}</td>
                  <td>{new Date(job.scheduled_at).toLocaleString()}</td>
                  <td>{job.error_message}</td>
                </tr>
              ))}
              {jobs.length === 0 && <EmptyRow columns={6} text="暂无任务" />}
            </tbody>
          </table>
        </div>
      </section>
    </Page>
  );
}

function Page({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </div>
        <SlidersHorizontal size={22} />
      </header>
      {children}
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: string | number; tone?: 'bad' }) {
  return (
    <div className={tone === 'bad' ? 'metric metric-bad' : 'metric'}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Badge({ value }: { value: string }) {
  return <span className={`badge badge-${value.replace(/_/g, '-')}`}>{value}</span>;
}

function EmptyRow({ columns, text }: { columns: number; text: string }) {
  return (
    <tr>
      <td colSpan={columns} className="empty-cell">
        {text}
      </td>
    </tr>
  );
}

function formatPrice(value: number | null) {
  if (value === null || value === undefined) return '-';
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function formatPercent(value: number | null) {
  if (value === null || value === undefined) return '-';
  return `${Math.round(value * 100)}%`;
}

function replaceAt<T>(items: T[], index: number, value: T) {
  return items.map((item, itemIndex) => (itemIndex === index ? value : item));
}
