"use client"

import { useEffect, useState } from "react"
import { DashboardLayout } from "@/components/layout/dashboard-layout"
import {
  AlertTriangle,
  Boxes,
  Brain,
  Building2,
  Database,
  ExternalLink,
  FileDown,
  FileSearch,
  GitBranch,
  HeartPulse,
  Layers,
  Library,
  Loader2,
  Network,
  Rocket,
  Send,
  Users,
} from "lucide-react"

const API = "http://127.0.0.1:8001"

const SUBJECT_TYPES = [
  { id: "idea", label: "Idea" },
  { id: "project", label: "Project" },
  { id: "customer", label: "Customer" },
  { id: "process", label: "Process" },
  { id: "enterprise", label: "Enterprise" },
]

const SUBJECT_HINTS: Record<string, string> = {
  idea:
    "e.g. Twin the new Invoice SaaS idea for SME customers before the board reviews it: purpose business invoicing, React/Node.js/MongoDB, roadmap payment automation...",
  project:
    "e.g. Return the Invoice SaaS project to the twin: it shipped invoice search and a GDPR consent flow; adoption is high but advanced reports were ignored...",
  customer:
    "e.g. Deeply understand the Small Accounting Firm segment: fast invoicing and tax reports, pain is manual payment tracking, desired outcome is saving 10 hours a month...",
  process:
    "e.g. Map the invoice process: lead received, manual email, meeting, proposal; find the automation opportunities and the process owner...",
  enterprise:
    "e.g. Refresh the whole twin: audit all products, customers, agents, processes, decisions, and standards; flag what is stale or duplicated...",
}

interface Dept {
  id: string
  name: string
  title: string
  order: number
  is_coordinator: boolean
}

interface EkdtStats {
  total: number
  in_progress: number
  completed: number
  failed: number
  avg_confidence: number | null
  avg_knowledge_score: number | null
  total_checks: number
  total_findings: number
  total_recommendations: number
  departments: number
  organizations: number
  active_products: number
  ai_agents: number
  knowledge_items: number
  successful_patterns: number
  decisions_stored: number
  active_projects: number
  predictive_alerts: number
  learning_updates: number
  knowledge_links: number
  semantic_answers: number
  knowledge_health: number | null
  twin_status: string
}

interface ReportSummary {
  id: string
  request: string
  subject_type: string
  status: string
  stage: string
  created_at: string
  avg_confidence: number | null
  knowledge_score: number | null
  knowledge_status: string | null
  total_checks: number
  total_findings: number
  total_recommendations: number
  predictions: number
  patterns: number
  decisions: number
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
  knowledge_score: number | null
  knowledge_status: string | null
  org_snapshot: string[]
  product_snapshot: string[]
  customer_insights: string[]
  process_updates: string[]
  agent_insights: string[]
  decisions_logged: string[]
  knowledge_links: string[]
  semantic_answers: string[]
  proven_patterns: string[]
  detected_patterns: string[]
  predictions: string[]
  knowledge_actions: string[]
  knowledge_quality: string[]
  knowledge_brief: string
  executive_summary: string
  avg_confidence: number | null
  total_checks: number
  total_findings: number
  total_recommendations: number
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

const twinStatusStyle: Record<string, string> = {
  Optimal: "bg-green-500/10 text-green-500 border-green-500/30",
  Actionable: "bg-amber-500/10 text-amber-500 border-amber-500/30",
  Stale: "bg-red-500/10 text-red-500 border-red-500/30",
}

function scoreColor(score: number): string {
  if (score >= 70) return "text-green-500"
  if (score >= 50) return "text-amber-500"
  return "text-red-500"
}

export default function EkdtPage() {
  const [stats, setStats] = useState<EkdtStats | null>(null)
  const [departments, setDepartments] = useState<Dept[]>([])
  const [reports, setReports] = useState<ReportSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [apiDown, setApiDown] = useState(false)

  const [requestText, setRequestText] = useState("")
  const [subjectType, setSubjectType] = useState("idea")
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState("")

  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<ReportDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [sending, setSending] = useState<string | null>(null)
  const [lastAction, setLastAction] = useState("")

  const fetchOverview = () => {
    Promise.all([
      fetch(`${API}/api/ekdt/stats`).then((r) => r.json()),
      fetch(`${API}/api/ekdt/departments`).then((r) => r.json()),
      fetch(`${API}/api/ekdt/reports`).then((r) => r.json()),
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
    fetch(`${API}/api/ekdt/reports`, {
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
    return fetch(`${API}/api/ekdt/reports/${reportId}`)
      .then((r) => r.json())
      .then((data) => {
        const reportDetail = data.report
        if (reportDetail && (reportDetail.status === "completed" || reportDetail.status === "failed" || reportDetail.status === "cancelled")) {
          setLastAction(`Digital Twin Update Report finished: ${reportDetail.status}`)
          return
        }
        if (reportDetail && attempts % 15 === 0) {
          setLastAction(`Knowledge update in progress: ${reportDetail.departments_completed}/${reportDetail.total_departments} knowledge systems (${reportDetail.stage})`)
        }
        if (attempts > 7200) throw new Error("Timed out waiting for Digital Twin Update Report")
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
    fetch(`${API}/api/ekdt/reports/${id}`)
      .then((r) => r.json())
      .then((data) => setDetail(data.report))
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false))
  }

  const sendToBoard = (id: string) => {
    setSending(id)
    setLastAction("")
    fetch(`${API}/api/ekdt/reports/${id}/to-board`, { method: "POST" })
      .then((r) => r.json())
      .then((data) => {
        if (data.error) throw new Error(data.error)
        setLastAction(`Sent to Executive Product Board for strategy review (review ${data.board_review_id?.slice(0, 8)})`)
        fetchOverview()
      })
      .catch((e) => setLastAction(`Send to board failed: ${e.message}`))
      .finally(() => setSending(null))
  }

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <p className="text-muted-foreground">Loading Digital Twin Platform...</p>
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

  const hint = SUBJECT_HINTS[subjectType] || SUBJECT_HINTS.idea

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
              <Database className="h-8 w-8 text-cyan-500" />
              Enterprise Knowledge &amp; Digital Twin
              <span className="text-sm font-medium text-muted-foreground bg-secondary/60 rounded-full px-3 py-1">Layer 10</span>
            </h1>
            <p className="text-muted-foreground mt-1">
              The living digital representation of the entire organization - products, customers, processes, AI agents,
              decisions, standards, and historical lessons. The single source of truth for the AI enterprise, sitting
              underneath everything: every agent connects to EKDT before it works. Knowledge, relationships, context,
              reasoning, decisions, actions, learning - the system remembers why things exist.
            </p>
          </div>
          <button
            onClick={fetchOverview}
            className="rounded-lg border border-border bg-card px-3 py-2 text-sm text-muted-foreground hover:bg-secondary shrink-0"
          >
            <Layers className="h-4 w-4 inline mr-1" /> Refresh
          </button>
        </div>

        {lastAction && (
          <div className="rounded-lg border border-primary/30 bg-primary/10 p-3 text-sm text-primary">
            {lastAction}
          </div>
        )}

        {/* Enterprise Intelligence Dashboard */}
        <div className="rounded-lg border border-cyan-500/30 bg-cyan-500/5 p-6">
          <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
            <Network className="h-5 w-5 text-cyan-500" /> Enterprise Intelligence Dashboard
          </h2>
          <p className="text-sm text-muted-foreground mb-4">Live view of the entire digital twin - what the CEO reads.</p>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <div>
              <p className="text-sm text-muted-foreground flex items-center gap-1.5">
                <Building2 className="h-3.5 w-3.5 text-cyan-500" /> Organizations
              </p>
              <p className="text-3xl font-bold mt-1">{stats?.organizations || 0}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground flex items-center gap-1.5">
                <Boxes className="h-3.5 w-3.5 text-cyan-500" /> Active Products
              </p>
              <p className="text-3xl font-bold mt-1">{stats?.active_products || 0}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground flex items-center gap-1.5">
                <Users className="h-3.5 w-3.5 text-cyan-500" /> AI Agents
              </p>
              <p className="text-3xl font-bold mt-1">{stats?.ai_agents || 0}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground flex items-center gap-1.5">
                <Database className="h-3.5 w-3.5 text-cyan-500" /> Knowledge Items
              </p>
              <p className="text-3xl font-bold mt-1">{stats?.knowledge_items || 0}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground flex items-center gap-1.5">
                <Library className="h-3.5 w-3.5 text-green-500" /> Successful Patterns
              </p>
              <p className="text-3xl font-bold mt-1 text-green-500">{stats?.successful_patterns || 0}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground flex items-center gap-1.5">
                <GitBranch className="h-3.5 w-3.5 text-cyan-500" /> Decisions Stored
              </p>
              <p className="text-3xl font-bold mt-1">{stats?.decisions_stored || 0}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground flex items-center gap-1.5">
                <Rocket className="h-3.5 w-3.5 text-cyan-500" /> Active Projects
              </p>
              <p className="text-3xl font-bold mt-1">{stats?.active_projects || 0}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground flex items-center gap-1.5">
                <AlertTriangle className="h-3.5 w-3.5 text-red-500" /> Predictive Alerts
              </p>
              <p className="text-3xl font-bold mt-1 text-red-500">{stats?.predictive_alerts || 0}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Learning Updates</p>
              <p className="text-3xl font-bold mt-1">{stats?.learning_updates || 0}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground flex items-center gap-1.5">
                <HeartPulse className="h-3.5 w-3.5 text-cyan-500" /> Knowledge Health
              </p>
              <p className={`text-3xl font-bold mt-1 ${stats?.knowledge_health != null ? scoreColor(stats.knowledge_health) : ""}`}>
                {stats?.knowledge_health != null ? `${stats.knowledge_health}/100` : "—"}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Twin Status</p>
              <p className="text-3xl font-bold mt-1">{stats?.twin_status || "—"}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Twin Updates</p>
              <p className="text-3xl font-bold mt-1">{stats?.total || 0}</p>
              <p className="text-xs text-muted-foreground">
                {stats?.completed || 0} completed · {stats?.failed || 0} failed
              </p>
            </div>
          </div>
        </div>

        {/* Submit knowledge subject */}
        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
            <Send className="h-5 w-5 text-cyan-500" /> Request Digital Twin Update
          </h2>
          <p className="text-sm text-muted-foreground mb-4">
            Describe an idea, project, customer, process, or enterprise refresh. All eleven knowledge systems update the
            twin, then the Knowledge Architect merges their findings into one Digital Twin Update Report: knowledge score,
            knowledge status, decisions logged, knowledge graph links, semantic answers, proven patterns, detected
            patterns, and predictions.
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
                placeholder={hint}
                rows={2}
                className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
              />
              <button
                onClick={submitReport}
                disabled={submitting || !requestText.trim()}
                className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50 self-end"
              >
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : "Update Digital Twin"}
              </button>
            </div>
          </div>
          {submitError && <p className="mt-2 text-sm text-red-500">{submitError}</p>}
          {submitting && (
            <p className="mt-3 text-sm text-muted-foreground flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" /> Eleven knowledge systems are updating the twin (this can take a few minutes)...
            </p>
          )}
        </div>

        {/* Knowledge systems roster */}
        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
            <Layers className="h-5 w-5 text-cyan-500" /> Knowledge Systems
          </h2>
          <p className="text-sm text-muted-foreground mb-4">The twelve systems that keep the twin alive - every agent connects here before it works.</p>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {departments.map((dept) => (
              <div key={dept.id} className="rounded-lg border border-border/50 bg-background/50 p-4">
                <div className="flex items-center gap-3">
                  <div className="rounded-lg p-2 bg-cyan-500/10">
                    {dept.is_coordinator ? (
                      <Brain className="h-4 w-4 text-cyan-500" />
                    ) : (
                      <Database className="h-4 w-4 text-cyan-500" />
                    )}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold truncate">{dept.name}</p>
                    {dept.is_coordinator && <p className="text-xs text-cyan-500">The librarian: merges everything into the Digital Twin Update Report</p>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Reports */}
        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
            <FileSearch className="h-5 w-5 text-cyan-500" /> Digital Twin Update Reports
          </h2>
          <p className="text-sm text-muted-foreground mb-4">Every Digital Twin Update Report the platform has produced - the single source of truth.</p>
          {reports.length === 0 ? (
            <p className="text-sm text-muted-foreground">No reports yet. Request a Digital Twin Update above.</p>
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
                        {new Date(report.created_at).toLocaleString()} · {report.departments_completed}/{report.total_departments} knowledge systems ·{" "}
                        {SUBJECT_TYPES.find((s) => s.id === report.subject_type)?.label || report.subject_type}
                        {report.predictions ? ` · ${report.predictions} predictions` : ""}
                      </p>
                    </div>
                    {report.knowledge_score != null && (
                      <span className={`text-xs font-bold ${scoreColor(report.knowledge_score)}`}>
                        {report.knowledge_score}/100
                      </span>
                    )}
                    {report.knowledge_status && (
                      <span
                        className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${twinStatusStyle[report.knowledge_status] || "border-border bg-secondary/60 text-muted-foreground"}`}
                      >
                        {report.knowledge_status}
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

                          {detail.knowledge_score != null && (
                            <div className="rounded-lg border border-cyan-500/30 bg-cyan-500/5 p-4">
                              <div className="flex flex-wrap items-center gap-4">
                                <div>
                                  <p className="text-sm text-muted-foreground">Overall Knowledge Score</p>
                                  <p className={`text-3xl font-bold ${scoreColor(detail.knowledge_score)}`}>{detail.knowledge_score}/100</p>
                                </div>
                                {detail.knowledge_status && (
                                  <div>
                                    <p className="text-sm text-muted-foreground">Knowledge Status</p>
                                    <span
                                      className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${twinStatusStyle[detail.knowledge_status] || "border-border bg-secondary/60 text-muted-foreground"}`}
                                    >
                                      {detail.knowledge_status}
                                    </span>
                                  </div>
                                )}
                                <p className="text-sm text-muted-foreground flex-1">
                                  {detail.executive_summary || "Digital Twin Update Report completed. See the twin sections and knowledge brief."}
                                </p>
                              </div>
                            </div>
                          )}

                          {detail.knowledge_brief && (
                            <div className="rounded-lg border border-cyan-500/30 bg-cyan-500/5 p-4">
                              <h3 className="text-sm font-semibold mb-1 flex items-center gap-2">
                                <HeartPulse className="h-4 w-4 text-cyan-500" /> Knowledge Brief
                              </h3>
                              <p className="text-sm text-muted-foreground whitespace-pre-wrap">{detail.knowledge_brief}</p>
                            </div>
                          )}

                          {/* Knowledge system reports */}
                          <div>
                            <h3 className="text-sm font-semibold mb-2">Knowledge System Reports</h3>
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

                          {/* Twin sections */}
                          <div className="grid gap-4 md:grid-cols-2">
                            {sectionBlock("Organizational Twin Snapshot", detail.org_snapshot)}
                            {sectionBlock("Product Twin Snapshot", detail.product_snapshot)}
                            {sectionBlock("Customer Twin Insights", detail.customer_insights)}
                            {sectionBlock("Process Twin Updates", detail.process_updates)}
                            {sectionBlock("AI Agent Twin Insights", detail.agent_insights)}
                            {sectionBlock("Decisions Logged", detail.decisions_logged)}
                            {sectionBlock("Knowledge Graph Links", detail.knowledge_links)}
                            {sectionBlock("Semantic Answers", detail.semantic_answers)}
                            {sectionBlock("Proven Patterns", detail.proven_patterns)}
                            {sectionBlock("Detected Patterns", detail.detected_patterns)}
                            {sectionBlock("Predictions", detail.predictions)}
                            {sectionBlock("Knowledge Actions", detail.knowledge_actions)}
                            {sectionBlock("Knowledge Quality", detail.knowledge_quality)}
                          </div>

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
                              href={`${API}/api/ekdt/reports/${report.id}/export`}
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
          <GitBranch className="h-4 w-4" />
          This layer sits underneath everything - it is the single source of truth. Every agent queries it before
          working: how have we built dashboards before, what architecture worked, what failed in previous releases, what
          features usually increase retention. The system remembers why things exist.
        </div>
      </div>
    </DashboardLayout>
  )
}
