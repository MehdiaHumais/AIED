"use client"

import { useEffect, useState } from "react"
import { DashboardLayout } from "@/components/layout/dashboard-layout"
import {
  Brain,
  Crown,
  Loader2,
  Send,
  CheckCircle2,
  RefreshCw,
  ExternalLink,
  FileDown,
  Layers,
  FileSearch,
  AlertTriangle,
  BookOpenCheck,
  GitBranch,
  GraduationCap,
  Lightbulb,
} from "lucide-react"

const API = "http://127.0.0.1:8001"

const SUBJECT_TYPES = [
  { id: "project", label: "Completed Project" },
  { id: "release", label: "Released Version" },
  { id: "product", label: "Product Profile" },
  { id: "organization", label: "Organization" },
  { id: "learning_topic", label: "Learning Topic" },
]

interface Dept {
  id: string
  name: string
  title: string
  order: number
  is_coordinator: boolean
}

interface IntelStats {
  total: number
  in_progress: number
  completed: number
  failed: number
  avg_confidence: number | null
  avg_intelligence_score: number | null
  total_lessons: number
  total_recommendations: number
  total_standards: number
  departments: number
}

interface ReportSummary {
  id: string
  request: string
  subject_type: string
  status: string
  stage: string
  created_at: string
  avg_confidence: number | null
  intelligence_score: number | null
  total_lessons: number
  total_recommendations: number
  total_standards: number
  departments_completed: number
  total_departments: number
  board_review_id: string | null
}

interface DeptReport {
  department_id: string
  department_name: string
  department_title: string
  verdict: string
  confidence: number
  score: number | null
  checks: string[]
  findings: string[]
  recommendations: string[]
  evidence: string[]
  status: string
  error: string
}

interface ReportDetail {
  id: string
  request: string
  subject_type: string
  status: string
  stage: string
  created_at: string
  completed_at: string | null
  reports: DeptReport[]
  intelligence_score: number | null
  project_summary: string[]
  objectives_achieved: string[]
  customer_impact: string[]
  business_impact: string[]
  feature_adoption: string[]
  support_trends: string[]
  performance: string[]
  security: string[]
  ux_outcomes: string[]
  growth_outcomes: string[]
  lessons_learned: string[]
  process_improvements: string[]
  updated_standards: string[]
  future_recommendations: string[]
  confidence_levels: string[]
  knowledge_graph: string
  executive_summary: string
  avg_confidence: number | null
  total_lessons: number
  total_recommendations: number
  total_standards: number
  board_review_id: string | null
  error: string
}

const verdictStyle: Record<string, string> = {
  support: "bg-green-500/10 text-green-500 border-green-500/30",
  recommend: "bg-blue-500/10 text-blue-500 border-blue-500/30",
  caution: "bg-amber-500/10 text-amber-500 border-amber-500/30",
  risk: "bg-red-500/10 text-red-500 border-red-500/30",
  neutral: "bg-zinc-500/10 text-zinc-400 border-zinc-500/30",
}

const statusStyle: Record<string, string> = {
  completed: "bg-green-500/10 text-green-500 border-green-500/30",
  in_progress: "bg-blue-500/10 text-blue-500 border-blue-500/30",
  failed: "bg-red-500/10 text-red-500 border-red-500/30",
  cancelled: "bg-zinc-500/10 text-zinc-400 border-zinc-500/30",
}

function scoreColor(score: number): string {
  if (score >= 70) return "text-green-500"
  if (score >= 50) return "text-amber-500"
  return "text-red-500"
}

export default function IntelligencePage() {
  const [stats, setStats] = useState<IntelStats | null>(null)
  const [departments, setDepartments] = useState<Dept[]>([])
  const [reports, setReports] = useState<ReportSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [apiDown, setApiDown] = useState(false)

  const [requestText, setRequestText] = useState("")
  const [subjectType, setSubjectType] = useState("project")
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState("")

  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<ReportDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [sending, setSending] = useState<string | null>(null)
  const [lastAction, setLastAction] = useState("")

  const fetchOverview = () => {
    Promise.all([
      fetch(`${API}/api/intelligence/stats`).then((r) => r.json()),
      fetch(`${API}/api/intelligence/departments`).then((r) => r.json()),
      fetch(`${API}/api/intelligence/reports`).then((r) => r.json()),
    ])
      .then(([statsData, deptData, reportData]) => {
        setStats(statsData || null)
        setDepartments(deptData.departments || [])
        setReports(reportData.reports || [])
        setLoading(false)
        setApiDown(false)
      })
      .catch(() => {
        setLoading(false)
        setApiDown(true)
      })
  }

  useEffect(() => { fetchOverview() }, [])

  const submitReport = () => {
    if (!requestText.trim()) return
    setSubmitting(true)
    setSubmitError("")
    setLastAction("")
    fetch(`${API}/api/intelligence/reports`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request: requestText.trim(), subject_type: subjectType, wait: false }),
    })
      .then((r) => r.json())
      .then(async (data) => {
        if (data.error) throw new Error(data.error)
        const reportId = data.report_id || (data.report && data.report.id)
        if (!reportId) throw new Error("No report id returned")
        await pollUntilDone(reportId)
        setRequestText("")
        fetchOverview()
      })
      .catch((e) => setSubmitError(e.message || "Submission failed"))
      .finally(() => setSubmitting(false))
  }

  const pollUntilDone = (reportId: string, attempts = 0): Promise<void> => {
    return fetch(`${API}/api/intelligence/reports/${reportId}`)
      .then((r) => r.json())
      .then((data) => {
        const reportDetail = data.report
        if (reportDetail && (reportDetail.status === "completed" || reportDetail.status === "failed" || reportDetail.status === "cancelled")) {
          setLastAction(`Project Intelligence Report finished: ${reportDetail.status}`)
          return
        }
        if (reportDetail && attempts % 15 === 0) {
          setLastAction(`Intelligence review in progress: ${reportDetail.departments_completed}/${reportDetail.total_departments} departments (${reportDetail.stage})`)
        }
        if (attempts > 7200) throw new Error("Timed out waiting for Project Intelligence Report")
        return new Promise((resolve) => setTimeout(resolve, 2000)).then(() =>
          pollUntilDone(reportId, attempts + 1)
        )
      })
  }

  const toggleDetail = (id: string) => {
    if (expandedId === id) {
      setExpandedId(null)
      setDetail(null)
      return
    }
    setExpandedId(id)
    setDetailLoading(true)
    fetch(`${API}/api/intelligence/reports/${id}`)
      .then((r) => r.json())
      .then((data) => setDetail(data.report))
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false))
  }

  const sendToBoard = (id: string) => {
    setSending(id)
    setLastAction("")
    fetch(`${API}/api/intelligence/reports/${id}/to-board`, { method: "POST" })
      .then((r) => r.json())
      .then((data) => {
        if (data.error) throw new Error(data.error)
        setLastAction(`Sent to Executive Product Board for review (review ${data.board_review_id?.slice(0, 8)})`)
        fetchOverview()
      })
      .catch((e) => setLastAction(`Send to board failed: ${e.message}`))
      .finally(() => setSending(null))
  }

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <p className="text-muted-foreground">Loading Intelligence division...</p>
        </div>
      </DashboardLayout>
    )
  }

  if (apiDown) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <div className="text-center">
            <p className="text-xl font-semibold mb-2">API Server Not Running</p>
            <p className="text-muted-foreground">
              Start the API: <code className="bg-secondary px-1 rounded">py -m apps.api.main</code>
            </p>
          </div>
        </div>
      </DashboardLayout>
    )
  }

  const sectionBlock = (title: string, items: string[]) =>
    items.length > 0 && (
      <div>
        <h4 className="text-sm font-semibold mb-1.5">{title}</h4>
        <ul className="space-y-1">
          {items.map((item, i) => (
            <li key={i} className="text-xs text-muted-foreground">{item}</li>
          ))}
        </ul>
      </div>
    )

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
              <Brain className="h-8 w-8 text-violet-500" />
              Intelligence, Learning &amp; Continuous Improvement
              <span className="text-sm font-medium text-muted-foreground bg-secondary/60 rounded-full px-3 py-1">Layer 8</span>
            </h1>
            <p className="text-muted-foreground mt-1">
              Eleven intelligence departments learn from every completed project, release, product, or topic, and the
              Intelligence Director merges their findings into one Project Intelligence Report: the organizational
              memory and continuous improvement engine. Lessons learned, updated standards, and a knowledge graph make
              every other division smarter - this division does not create products, it improves how they are made.
            </p>
          </div>
          <button
            onClick={fetchOverview}
            className="rounded-lg border border-border bg-card px-3 py-2 text-sm text-muted-foreground hover:bg-secondary shrink-0"
          >
            <RefreshCw className="h-4 w-4 inline mr-1" /> Refresh
          </button>
        </div>

        {lastAction && (
          <div className="rounded-lg border border-primary/30 bg-primary/10 p-3 text-sm text-primary">
            {lastAction}
          </div>
        )}

        {/* Stats */}
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-lg border border-border bg-card p-6">
            <p className="text-sm text-muted-foreground">Intelligence Reports</p>
            <p className="text-3xl font-bold mt-1">{stats?.total || 0}</p>
            <p className="text-xs text-muted-foreground">{stats?.in_progress || 0} in progress</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-6">
            <p className="text-sm text-muted-foreground flex items-center gap-1.5">
              <CheckCircle2 className="h-3.5 w-3.5 text-green-500" /> Completed
            </p>
            <p className="text-3xl font-bold mt-1 text-green-500">{stats?.completed || 0}</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-6">
            <p className="text-sm text-muted-foreground flex items-center gap-1.5">
              <GraduationCap className="h-3.5 w-3.5 text-violet-500" /> Avg Intelligence Score
            </p>
            <p className={`text-3xl font-bold mt-1 ${stats?.avg_intelligence_score != null ? scoreColor(stats.avg_intelligence_score) : ""}`}>
              {stats?.avg_intelligence_score != null ? `${stats.avg_intelligence_score}/100` : "—"}
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              {stats?.avg_confidence != null ? `${stats.avg_confidence * 100}% avg confidence` : ""}
            </p>
          </div>
          <div className="rounded-lg border border-border bg-card p-6">
            <p className="text-sm text-muted-foreground flex items-center gap-1.5">
              <BookOpenCheck className="h-3.5 w-3.5 text-violet-500" /> Lessons Learned
            </p>
            <p className="text-3xl font-bold mt-1">{stats?.total_lessons || 0}</p>
            <p className="text-xs text-muted-foreground">
              {stats?.total_recommendations || 0} recommendations · {stats?.total_standards || 0} standards updated
            </p>
          </div>
        </div>

        {/* Submit subject */}
        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
            <Send className="h-5 w-5 text-violet-500" /> Request Project Intelligence Report
          </h2>
          <p className="text-sm text-muted-foreground mb-4">
            Describe a learning subject. All eleven intelligence departments review it, then the Intelligence Director
            merges their findings into one Project Intelligence Report: overall intelligence score, lessons learned,
            process improvements, updated Layer 1 standards, future recommendations, and the organization-wide
            knowledge graph.
          </p>
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap gap-2">
              {SUBJECT_TYPES.map((st) => (
                <button
                  key={st.id}
                  onClick={() => setSubjectType(st.id)}
                  className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
                    subjectType === st.id
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border bg-background text-muted-foreground hover:bg-secondary"
                  }`}
                >
                  {st.label}
                </button>
              ))}
            </div>
            <div className="flex flex-col sm:flex-row gap-2">
              <textarea
                value={requestText}
                onChange={(e) => setRequestText(e.target.value)}
                placeholder="e.g. Learn from the completed Invoice SaaS project. It shipped invoice search, role-based permissions, SSO, and a GDPR consent flow; adoption of invoice search is high but advanced reports were ignored..."
                rows={2}
                className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
              />
              <button
                onClick={submitReport}
                disabled={submitting || !requestText.trim()}
                className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50 self-end"
              >
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : "Run Intelligence Review"}
              </button>
            </div>
          </div>
          {submitError && <p className="mt-2 text-sm text-red-500">{submitError}</p>}
          {submitting && (
            <p className="mt-3 text-sm text-muted-foreground flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" /> Eleven intelligence departments are learning (this can take a few minutes)...
            </p>
          )}
        </div>

        {/* Department roster */}
        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
            <Layers className="h-5 w-5 text-violet-500" /> Intelligence Departments
          </h2>
          <p className="text-sm text-muted-foreground mb-4">The twelve departments that run the learning loop and keep the organization smarter.</p>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {departments.map((dept) => (
              <div key={dept.id} className="rounded-lg border border-border/50 bg-background/50 p-4">
                <div className="flex items-center gap-3">
                  <div className={`rounded-lg p-2 ${dept.is_coordinator ? "bg-amber-500/10" : "bg-violet-500/10"}`}>
                    {dept.is_coordinator ? (
                      <Crown className="h-4 w-4 text-amber-500" />
                    ) : (
                      <Brain className="h-4 w-4 text-violet-500" />
                    )}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold truncate">{dept.name}</p>
                    {dept.is_coordinator && <p className="text-xs text-amber-500">Merges everything into the Project Intelligence Report + knowledge graph</p>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Reports */}
        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
            <FileSearch className="h-5 w-5 text-violet-500" /> Project Intelligence Reports
          </h2>
          <p className="text-sm text-muted-foreground mb-4">Every Project Intelligence Report the division has produced - the organizational memory.</p>
          {reports.length === 0 ? (
            <p className="text-sm text-muted-foreground">No reports yet. Request a Project Intelligence Report above.</p>
          ) : (
            <div className="space-y-2">
              {reports.map((report) => (
                <div key={report.id} className="rounded-lg border border-border/50 bg-background/50">
                  <button
                    onClick={() => toggleDetail(report.id)}
                    className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-secondary/40 transition-colors"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold truncate">{report.request}</p>
                      <p className="text-xs text-muted-foreground">
                        {new Date(report.created_at).toLocaleString()} · {report.departments_completed}/{report.total_departments} departments ·{" "}
                        {SUBJECT_TYPES.find((s) => s.id === report.subject_type)?.label || report.subject_type}
                        {report.total_lessons ? ` · ${report.total_lessons} lessons` : ""}
                      </p>
                    </div>
                    {report.intelligence_score != null && (
                      <span className={`text-xs font-bold ${scoreColor(report.intelligence_score)}`}>
                        {report.intelligence_score}/100
                      </span>
                    )}
                    <span
                      className={`rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${statusStyle[report.status] || "border-border bg-secondary/60 text-muted-foreground"}`}
                    >
                      {report.status}
                    </span>
                  </button>

                  {expandedId === report.id && (
                    <div className="border-t border-border/50 px-4 py-4">
                      {detailLoading ? (
                        <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
                          <Loader2 className="h-4 w-4 animate-spin" /> Loading report...
                        </div>
                      ) : detail ? (
                        <div className="space-y-4">
                          {detail.error && <p className="text-sm text-red-500">Error: {detail.error}</p>}

                          {detail.intelligence_score != null && (
                            <div className="rounded-lg border border-violet-500/30 bg-violet-500/5 p-4">
                              <div className="flex flex-wrap items-center gap-4">
                                <div>
                                  <p className="text-sm text-muted-foreground">Overall Intelligence Score</p>
                                  <p className={`text-3xl font-bold ${scoreColor(detail.intelligence_score)}`}>{detail.intelligence_score}/100</p>
                                </div>
                                <p className="text-sm text-muted-foreground flex-1">
                                  {detail.executive_summary || "Project Intelligence Report completed. See the report sections and knowledge graph."}
                                </p>
                              </div>
                            </div>
                          )}

                          {/* Department reports */}
                          <div>
                            <h3 className="text-sm font-semibold mb-2">Department Reports</h3>
                            <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
                              {detail.reports.map((r) => (
                                <div key={r.department_id} className="rounded-lg border border-border/50 bg-background/60 p-3">
                                  <div className="flex items-center justify-between gap-2">
                                    <p className="text-xs font-semibold truncate">{r.department_name}</p>
                                    {r.status === "completed" ? (
                                      <span className={`rounded-full border px-1.5 py-0.5 text-[10px] capitalize shrink-0 ${verdictStyle[r.verdict] || verdictStyle.neutral}`}>
                                        {r.verdict}
                                      </span>
                                    ) : null}
                                  </div>
                                  <p className="text-xs text-muted-foreground mt-0.5">
                                    {r.status === "completed"
                                      ? `${r.score != null ? `${r.score}/100 · ` : ""}${Math.round(r.confidence * 100)}% confidence · ${r.findings.length} findings`
                                      : r.status}
                                  </p>
                                  {r.status === "failed" && r.error && (
                                    <p className="text-xs text-red-500 mt-1" title={r.error}>{r.error}</p>
                                  )}
                                  {r.status === "completed" && r.findings.length > 0 && (
                                    <ul className="mt-1.5 space-y-0.5">
                                      {r.findings.slice(0, 3).map((f, i) => (
                                        <li key={i} className="text-xs text-muted-foreground">- {f}</li>
                                      ))}
                                    </ul>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>

                          {/* Learning highlights */}
                          <div className="grid gap-4 md:grid-cols-2">
                            <div className="rounded-lg border border-violet-500/30 bg-violet-500/5 p-4">
                              <h4 className="text-sm font-semibold mb-1.5 flex items-center gap-1.5">
                                <Lightbulb className="h-3.5 w-3.5 text-violet-500" /> Lessons Learned
                              </h4>
                              <ul className="space-y-1">
                                {detail.lessons_learned.map((item, i) => (
                                  <li key={i} className="text-xs text-muted-foreground">- {item}</li>
                                ))}
                              </ul>
                            </div>
                            <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4">
                              <h4 className="text-sm font-semibold mb-1.5 flex items-center gap-1.5">
                                <BookOpenCheck className="h-3.5 w-3.5 text-emerald-500" /> Updated Standards
                              </h4>
                              <ul className="space-y-1">
                                {detail.updated_standards.map((item, i) => (
                                  <li key={i} className="text-xs text-muted-foreground">- {item}</li>
                                ))}
                              </ul>
                            </div>
                          </div>

                          {/* Report sections */}
                          <div className="grid gap-4 md:grid-cols-2">
                            {sectionBlock("Project Summary", detail.project_summary)}
                            {sectionBlock("Objectives Achieved", detail.objectives_achieved)}
                            {sectionBlock("Customer Impact", detail.customer_impact)}
                            {sectionBlock("Business Impact", detail.business_impact)}
                            {sectionBlock("Feature Adoption", detail.feature_adoption)}
                            {sectionBlock("Support Trends", detail.support_trends)}
                            {sectionBlock("Performance", detail.performance)}
                            {sectionBlock("Security", detail.security)}
                            {sectionBlock("UX Outcomes", detail.ux_outcomes)}
                            {sectionBlock("Growth Outcomes", detail.growth_outcomes)}
                            {sectionBlock("Process Improvements", detail.process_improvements)}
                            {sectionBlock("Future Recommendations", detail.future_recommendations)}
                            {sectionBlock("Confidence Levels", detail.confidence_levels)}
                          </div>

                          {/* Knowledge graph */}
                          {detail.knowledge_graph && (
                            <div className="rounded-lg border border-violet-500/30 bg-violet-500/5 p-4">
                              <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
                                <GitBranch className="h-4 w-4" /> Knowledge Graph
                              </h3>
                              <pre className="text-xs whitespace-pre-wrap font-sans text-muted-foreground max-h-96 overflow-y-auto">
                                {detail.knowledge_graph}
                              </pre>
                            </div>
                          )}

                          {!detail.knowledge_graph && detail.executive_summary && (
                            <div className="rounded-lg border border-violet-500/30 bg-violet-500/5 p-4">
                              <h3 className="text-sm font-semibold mb-1">Executive Summary</h3>
                              <p className="text-sm text-muted-foreground">{detail.executive_summary}</p>
                            </div>
                          )}

                          {/* Actions */}
                          <div className="flex flex-wrap gap-2 pt-1">
                            {report.status === "completed" && (
                              <button
                                onClick={() => sendToBoard(report.id)}
                                disabled={sending === report.id || detail.board_review_id != null}
                                className="rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
                              >
                                {sending === report.id ? (
                                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                ) : (
                                  <ExternalLink className="h-3.5 w-3.5 inline mr-1" />
                                )}
                                {detail.board_review_id ? "Sent to Board" : "Send to Board"}
                              </button>
                            )}
                            <a
                              href={`${API}/api/intelligence/reports/${report.id}/export`}
                              target="_blank"
                              rel="noreferrer"
                              className="rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-secondary"
                            >
                              <FileDown className="h-3.5 w-3.5 inline mr-1" /> Export
                            </a>
                          </div>
                        </div>
                      ) : (
                        <p className="text-sm text-red-500">Failed to load report detail.</p>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Brain className="h-4 w-4" />
          This division does not create products. It is the organizational memory - lessons learned and updated standards
          make the next project better than the last, and every department queries the knowledge graph before deciding.
        </div>
      </div>
    </DashboardLayout>
  )
}
