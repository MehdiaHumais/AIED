"use client"

import { useEffect, useState } from "react"
import { DashboardLayout } from "@/components/layout/dashboard-layout"
import {
  Activity,
  AlertTriangle,
  Boxes,
  Crown,
  ExternalLink,
  FileDown,
  FileSearch,
  GitBranch,
  HeartPulse,
  Layers,
  Loader2,
  Rocket,
  Send,
  ShieldCheck,
  Users,
  Workflow,
} from "lucide-react"

const API = "http://127.0.0.1:8001"

const SUBJECT_TYPES = [
  { id: "operation", label: "Operation" },
  { id: "workflow", label: "Workflow" },
  { id: "conflict", label: "Conflict" },
  { id: "enterprise", label: "Enterprise" },
]

const SUBJECT_HINTS: Record<string, string> = {
  operation:
    "e.g. Build the Invoice SaaS module. Research first, then UX, Growth and Competitor Review in parallel, Development after UX/UI approval, then QA, then Deployment...",
  workflow:
    "e.g. Optimize the agent workflow for invoice generation: the orchestrator over-activates agents, frontend gates are unenforced, and agents run out of order...",
  conflict:
    "e.g. Arbitrate between UX and Compliance on how many fields the invoice form collects, and between the backend and data agents over where reporting lives...",
  enterprise:
    "e.g. Run an enterprise-wide health review of the AI workforce: 14 agents, 3 workflows, infrastructure at 87%, and two unenforced dependency gates...",
}

interface Dept {
  id: string
  name: string
  title: string
  order: number
  is_coordinator: boolean
}

interface GovStats {
  total: number
  in_progress: number
  completed: number
  failed: number
  avg_confidence: number | null
  avg_governance_score: number | null
  total_checks: number
  total_findings: number
  total_recommendations: number
  departments: number
  organization_health: number | null
  projects_active: number
  blocked: number
  releases_this_week: number
  critical_risks: number
  agents_online: number
  avg_utilization: number | null
  avg_task_completion: number | null
  quality_score: number | null
  customer_satisfaction: number | null
  infrastructure_status: string
  executive_alerts: number
}

interface ReportSummary {
  id: string
  request: string
  subject_type: string
  status: string
  stage: string
  created_at: string
  avg_confidence: number | null
  governance_score: number | null
  final_decision: string | null
  total_checks: number
  total_findings: number
  total_recommendations: number
  alerts: number
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
  governance_score: number | null
  final_decision: string | null
  required_divisions: string[]
  work_packages: string[]
  agent_assignments: string[]
  capability_matches: string[]
  arbitration_rulings: string[]
  resource_plan: string[]
  dependency_map: string[]
  schedule: string[]
  policy_compliance: string[]
  performance_insights: string[]
  audit_trail: string[]
  operational_alerts: string[]
  enterprise_kpis: string[]
  approvals: string[]
  operations_brief: string
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

const decisionStyle: Record<string, string> = {
  Approved: "bg-green-500/10 text-green-500 border-green-500/30",
  "Conditional Approval": "bg-amber-500/10 text-amber-500 border-amber-500/30",
  "Not Approved": "bg-red-500/10 text-red-500 border-red-500/30",
}

function scoreColor(score: number): string {
  if (score >= 70) return "text-green-500"
  if (score >= 50) return "text-amber-500"
  return "text-red-500"
}

export default function GovernancePage() {
  const [stats, setStats] = useState<GovStats | null>(null)
  const [departments, setDepartments] = useState<Dept[]>([])
  const [reports, setReports] = useState<ReportSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [apiDown, setApiDown] = useState(false)

  const [requestText, setRequestText] = useState("")
  const [subjectType, setSubjectType] = useState("operation")
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState("")

  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<ReportDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [sending, setSending] = useState<string | null>(null)
  const [lastAction, setLastAction] = useState("")

  const fetchOverview = () => {
    Promise.all([
      fetch(`${API}/api/governance/stats`).then((r) => r.json()),
      fetch(`${API}/api/governance/departments`).then((r) => r.json()),
      fetch(`${API}/api/governance/reports`).then((r) => r.json()),
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
    fetch(`${API}/api/governance/reports`, {
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
    return fetch(`${API}/api/governance/reports/${reportId}`)
      .then((r) => r.json())
      .then((data) => {
        const reportDetail = data.report
        if (reportDetail && (reportDetail.status === "completed" || reportDetail.status === "failed" || reportDetail.status === "cancelled")) {
          setLastAction(`Division Operations Report finished: ${reportDetail.status}`)
          return
        }
        if (reportDetail && attempts % 15 === 0) {
          setLastAction(`Operations review in progress: ${reportDetail.departments_completed}/${reportDetail.total_departments} departments (${reportDetail.stage})`)
        }
        if (attempts > 7200) throw new Error("Timed out waiting for Division Operations Report")
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
    fetch(`${API}/api/governance/reports/${id}`)
      .then((r) => r.json())
      .then((data) => setDetail(data.report))
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false))
  }

  const sendToBoard = (id: string) => {
    setSending(id)
    setLastAction("")
    fetch(`${API}/api/governance/reports/${id}/to-board`, { method: "POST" })
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
          <p className="text-muted-foreground">Loading Governance division...</p>
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

  const hint = SUBJECT_HINTS[subjectType] || SUBJECT_HINTS.operation

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
              <ShieldCheck className="h-8 w-8 text-amber-500" />
              Enterprise AI Governance &amp; Orchestration
              <span className="text-sm font-medium text-muted-foreground bg-secondary/60 rounded-full px-3 py-1">Layer 9</span>
            </h1>
            <p className="text-muted-foreground mt-1">
              The Chief Operating Office for the AI workforce: right agents, right time, right information, right order.
              Twelve operations departments run on every operation, workflow, conflict, or enterprise health review, and the
              Chief AI Operations Director merges their findings into one Division Operations Report - required divisions,
              work packages, agent assignments, dependency map, schedule, and approvals. This layer does not replace the CEO;
              it governs and orchestrates every AI agent, workflow, and decision so no department bypasses the operating office.
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

        {/* Executive operations dashboard */}
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-6">
          <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
            <Activity className="h-5 w-5 text-amber-500" /> Executive Operations Dashboard
          </h2>
          <p className="text-sm text-muted-foreground mb-4">Live view of the AI workforce - what the CEO reads.</p>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <div>
              <p className="text-sm text-muted-foreground flex items-center gap-1.5">
                <HeartPulse className="h-3.5 w-3.5 text-amber-500" /> Organization Health
              </p>
              <p className={`text-3xl font-bold mt-1 ${stats?.organization_health != null ? scoreColor(stats.organization_health) : ""}`}>
                {stats?.organization_health != null ? `${stats.organization_health}/100` : "—"}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground flex items-center gap-1.5">
                <Boxes className="h-3.5 w-3.5 text-amber-500" /> Active Projects
              </p>
              <p className="text-3xl font-bold mt-1">{stats?.projects_active || 0}</p>
              <p className="text-xs text-muted-foreground">{stats?.blocked || 0} blocked</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground flex items-center gap-1.5">
                <Rocket className="h-3.5 w-3.5 text-green-500" /> Releases This Week
              </p>
              <p className="text-3xl font-bold mt-1 text-green-500">{stats?.releases_this_week || 0}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground flex items-center gap-1.5">
                <Users className="h-3.5 w-3.5 text-amber-500" /> Agents Online
              </p>
              <p className="text-3xl font-bold mt-1">{stats?.agents_online || 0}</p>
              <p className="text-xs text-muted-foreground">assigned across operations</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground flex items-center gap-1.5">
                <AlertTriangle className="h-3.5 w-3.5 text-red-500" /> Critical Risks
              </p>
              <p className="text-3xl font-bold mt-1 text-red-500">{stats?.critical_risks || 0}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground flex items-center gap-1.5">
                <Activity className="h-3.5 w-3.5 text-amber-500" /> Infrastructure
              </p>
              <p className="text-3xl font-bold mt-1">{stats?.infrastructure_status || "—"}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Executive Alerts</p>
              <p className="text-3xl font-bold mt-1">{stats?.executive_alerts || 0}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Division Reports</p>
              <p className="text-3xl font-bold mt-1">{stats?.total || 0}</p>
              <p className="text-xs text-muted-foreground">
                {stats?.completed || 0} completed · {stats?.failed || 0} failed
              </p>
            </div>
          </div>
        </div>

        {/* Submit operation */}
        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
            <Send className="h-5 w-5 text-amber-500" /> Request Division Operations Report
          </h2>
          <p className="text-sm text-muted-foreground mb-4">
            Describe an enterprise operation, a workflow to optimize, a conflict to arbitrate, or an enterprise-wide health
            review. All twelve operations departments review it, then the Chief AI Operations Director merges their findings
            into one Division Operations Report: overall governance score, final decision, required divisions, work packages,
            agent assignments, dependency map, schedule, and approvals.
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
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : "Run Operations Review"}
              </button>
            </div>
          </div>
          {submitError && <p className="mt-2 text-sm text-red-500">{submitError}</p>}
          {submitting && (
            <p className="mt-3 text-sm text-muted-foreground flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" /> Twelve operations departments are reviewing (this can take a few minutes)...
            </p>
          )}
        </div>

        {/* Department roster */}
        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
            <Layers className="h-5 w-5 text-amber-500" /> Operations Departments
          </h2>
          <p className="text-sm text-muted-foreground mb-4">The thirteen operations departments - every agent reports operational status here.</p>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {departments.map((dept) => (
              <div key={dept.id} className="rounded-lg border border-border/50 bg-background/50 p-4">
                <div className="flex items-center gap-3">
                  <div className={`rounded-lg p-2 ${dept.is_coordinator ? "bg-amber-500/10" : "bg-amber-500/10"}`}>
                    {dept.is_coordinator ? (
                      <Crown className="h-4 w-4 text-amber-500" />
                    ) : (
                      <Workflow className="h-4 w-4 text-amber-500" />
                    )}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold truncate">{dept.name}</p>
                    {dept.is_coordinator && <p className="text-xs text-amber-500">Merges everything into the Division Operations Report</p>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Reports */}
        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
            <FileSearch className="h-5 w-5 text-amber-500" /> Division Operations Reports
          </h2>
          <p className="text-sm text-muted-foreground mb-4">Every Division Operations Report the operating office has produced.</p>
          {reports.length === 0 ? (
            <p className="text-sm text-muted-foreground">No reports yet. Request a Division Operations Report above.</p>
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
                        {report.alerts ? ` · ${report.alerts} alerts` : ""}
                      </p>
                    </div>
                    {report.governance_score != null && (
                      <span className={`text-xs font-bold ${scoreColor(report.governance_score)}`}>
                        {report.governance_score}/100
                      </span>
                    )}
                    {report.final_decision && (
                      <span
                        className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${decisionStyle[report.final_decision] || "border-border bg-secondary/60 text-muted-foreground"}`}
                      >
                        {report.final_decision}
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

                          {detail.governance_score != null && (
                            <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4">
                              <div className="flex flex-wrap items-center gap-4">
                                <div>
                                  <p className="text-sm text-muted-foreground">Overall Governance Score</p>
                                  <p className={`text-3xl font-bold ${scoreColor(detail.governance_score)}`}>{detail.governance_score}/100</p>
                                </div>
                                {detail.final_decision && (
                                  <div>
                                    <p className="text-sm text-muted-foreground">Final Decision</p>
                                    <span
                                      className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${decisionStyle[detail.final_decision] || "border-border bg-secondary/60 text-muted-foreground"}`}
                                    >
                                      {detail.final_decision}
                                    </span>
                                  </div>
                                )}
                                <p className="text-sm text-muted-foreground flex-1">
                                  {detail.executive_summary || "Division Operations Report completed. See the required divisions, work packages, and schedule."}
                                </p>
                              </div>
                            </div>
                          )}

                          {detail.operations_brief && (
                            <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4">
                              <h3 className="text-sm font-semibold mb-1 flex items-center gap-2">
                                <HeartPulse className="h-4 w-4 text-amber-500" /> Executive Operations Brief
                              </h3>
                              <p className="text-sm text-muted-foreground whitespace-pre-wrap">{detail.operations_brief}</p>
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

                          {/* Operations sections */}
                          <div className="grid gap-4 md:grid-cols-2">
                            {sectionBlock("Required Divisions", detail.required_divisions)}
                            {sectionBlock("Work Packages", detail.work_packages)}
                            {sectionBlock("Agent Assignments", detail.agent_assignments)}
                            {sectionBlock("Capability Matches", detail.capability_matches)}
                            {sectionBlock("Arbitration Rulings", detail.arbitration_rulings)}
                            {sectionBlock("Resource Plan", detail.resource_plan)}
                            {sectionBlock("Dependency Map", detail.dependency_map)}
                            {sectionBlock("Schedule", detail.schedule)}
                            {sectionBlock("Policy Compliance", detail.policy_compliance)}
                            {sectionBlock("Performance Insights", detail.performance_insights)}
                            {sectionBlock("Audit Trail", detail.audit_trail)}
                            {sectionBlock("Operational Alerts", detail.operational_alerts)}
                            {sectionBlock("Enterprise KPIs", detail.enterprise_kpis)}
                            {sectionBlock("Approvals", detail.approvals)}
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
                              href={`${API}/api/governance/reports/${report.id}/export`}
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
          This layer does not replace the CEO - it is the Chief Operating Office for the AI workforce. Right agents, right
          time, right information, right order: every agent reports operational status here, and no department bypasses this layer.
        </div>
      </div>
    </DashboardLayout>
  )
}
