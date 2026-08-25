"use client"

import { useEffect, useState } from "react"
import { DashboardLayout } from "@/components/layout/dashboard-layout"
import {
  ShieldCheck,
  Rocket,
  Loader2,
  Send,
  Scale,
  CheckCircle2,
  RefreshCw,
  ExternalLink,
  FileDown,
  Layers,
  FileSearch,
  AlertTriangle,
  RotateCcw,
  ScrollText,
  Crown,
} from "lucide-react"

const API = "http://127.0.0.1:8001"

const SUBJECT_TYPES = [
  { id: "release", label: "Versioned Release" },
  { id: "feature", label: "Feature Area" },
  { id: "service", label: "Service / API" },
  { id: "whole_product", label: "Whole Product" },
  { id: "enterprise", label: "Enterprise Deployment" },
]

interface Dept {
  id: string
  name: string
  title: string
  order: number
  is_coordinator: boolean
}

interface QualityStats {
  total: number
  in_progress: number
  completed: number
  failed: number
  avg_confidence: number | null
  avg_quality_score: number | null
  total_checks: number
  total_findings: number
  final_decisions: { go: number; conditional_go: number; no_go: number }
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
  quality_score: number | null
  final_decision: string
  release_version: string
  total_checks: number
  total_findings: number
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
  quality_score: number | null
  release_version: string
  functional_qa: string[]
  performance_review: string[]
  security_review: string[]
  compliance_review: string[]
  accessibility_review: string[]
  documentation_status: string[]
  architecture_review: string[]
  deployment_readiness: string[]
  monitoring_status: string[]
  enterprise_readiness: string[]
  known_risks: string[]
  rollback_strategy: string[]
  final_decision: string
  release_certificate: string
  executive_summary: string
  avg_confidence: number | null
  total_checks: number
  total_findings: number
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
  Go: "bg-green-500/15 text-green-400 border-green-500/40",
  "Conditional Go": "bg-amber-500/15 text-amber-400 border-amber-500/40",
  "No Go": "bg-red-500/15 text-red-400 border-red-500/40",
  pending: "bg-zinc-500/10 text-zinc-400 border-zinc-500/30",
}

function scoreColor(score: number): string {
  if (score >= 70) return "text-green-500"
  if (score >= 50) return "text-amber-500"
  return "text-red-500"
}

export default function QualityPage() {
  const [stats, setStats] = useState<QualityStats | null>(null)
  const [departments, setDepartments] = useState<Dept[]>([])
  const [reports, setReports] = useState<ReportSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [apiDown, setApiDown] = useState(false)

  const [requestText, setRequestText] = useState("")
  const [subjectType, setSubjectType] = useState("release")
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState("")

  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<ReportDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [sending, setSending] = useState<string | null>(null)
  const [lastAction, setLastAction] = useState("")

  const fetchOverview = () => {
    Promise.all([
      fetch(`${API}/api/quality/stats`).then((r) => r.json()),
      fetch(`${API}/api/quality/departments`).then((r) => r.json()),
      fetch(`${API}/api/quality/reports`).then((r) => r.json()),
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
    fetch(`${API}/api/quality/reports`, {
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
    return fetch(`${API}/api/quality/reports/${reportId}`)
      .then((r) => r.json())
      .then((data) => {
        const reportDetail = data.report
        if (reportDetail && (reportDetail.status === "completed" || reportDetail.status === "failed" || reportDetail.status === "cancelled")) {
          setLastAction(`Release Excellence Report finished: ${reportDetail.status}`)
          return
        }
        if (reportDetail && attempts % 15 === 0) {
          setLastAction(`Release review in progress: ${reportDetail.departments_completed}/${reportDetail.total_departments} departments (${reportDetail.stage})`)
        }
        if (attempts > 7200) throw new Error("Timed out waiting for Release Excellence Report")
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
    fetch(`${API}/api/quality/reports/${id}`)
      .then((r) => r.json())
      .then((data) => setDetail(data.report))
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false))
  }

  const sendToBoard = (id: string) => {
    setSending(id)
    setLastAction("")
    fetch(`${API}/api/quality/reports/${id}/to-board`, { method: "POST" })
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
          <p className="text-muted-foreground">Loading Quality division...</p>
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

  const decisions = stats?.final_decisions

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
              <ShieldCheck className="h-8 w-8 text-sky-500" />
              Quality, Security &amp; Release Excellence
              <span className="text-sm font-medium text-muted-foreground bg-secondary/60 rounded-full px-3 py-1">Layer 7</span>
            </h1>
            <p className="text-muted-foreground mt-1">
              Twelve departments form the final gate before production - functional QA, performance engineering,
              security review, privacy &amp; compliance, accessibility validation, release readiness, documentation,
              DevOps quality, architecture review, production monitoring, incident prevention, and enterprise
              readiness. The Release Director merges everything into a Release Excellence Report with a formal
              Go / Conditional Go / No Go decision and a release certificate. Nothing reaches customers without
              approval from this division.
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
            <p className="text-sm text-muted-foreground">Release Reviews</p>
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
              <Scale className="h-3.5 w-3.5 text-primary" /> Avg Quality Score
            </p>
            <p className={`text-3xl font-bold mt-1 ${stats?.avg_quality_score != null ? scoreColor(stats.avg_quality_score) : ""}`}>
              {stats?.avg_quality_score != null ? `${stats.avg_quality_score}/100` : "—"}
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              {decisions ? `${decisions.go} Go · ${decisions.conditional_go} Conditional Go · ${decisions.no_go} No Go` : ""}
            </p>
          </div>
          <div className="rounded-lg border border-border bg-card p-6">
            <p className="text-sm text-muted-foreground">Checks &amp; Findings</p>
            <p className="text-3xl font-bold mt-1">{stats?.total_checks || 0}</p>
            <p className="text-xs text-muted-foreground">{stats?.total_findings || 0} findings logged</p>
          </div>
        </div>

        {/* Submit subject */}
        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
            <Send className="h-5 w-5 text-sky-500" /> Request Release Excellence Report
          </h2>
          <p className="text-sm text-muted-foreground mb-4">
            Describe the release. All twelve quality departments review it, then the Release Director
            writes one Release Excellence Report with an overall quality score, known risks, a rollback
            strategy, and the formal Go / Conditional Go / No Go decision with a release certificate.
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
                placeholder="e.g. Gate release v3.2 of our recruitment SaaS for production. New invoice search, role-based permissions, SSO, and a GDPR consent flow ship in this release..."
                rows={2}
                className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
              />
              <button
                onClick={submitReport}
                disabled={submitting || !requestText.trim()}
                className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50 self-end"
              >
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : "Run Release Review"}
              </button>
            </div>
          </div>
          {submitError && <p className="mt-2 text-sm text-red-500">{submitError}</p>}
          {submitting && (
            <p className="mt-3 text-sm text-muted-foreground flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" /> Twelve quality departments are reviewing (this can take a few minutes)...
            </p>
          )}
        </div>

        {/* Department roster */}
        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
            <Layers className="h-5 w-5 text-sky-500" /> Quality Departments
          </h2>
          <p className="text-sm text-muted-foreground mb-4">The thirteen departments that own the final release gate.</p>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {departments.map((dept) => (
              <div key={dept.id} className="rounded-lg border border-border/50 bg-background/50 p-4">
                <div className="flex items-center gap-3">
                  <div className={`rounded-lg p-2 ${dept.is_coordinator ? "bg-amber-500/10" : "bg-sky-500/10"}`}>
                    {dept.is_coordinator ? (
                      <Crown className="h-4 w-4 text-amber-500" />
                    ) : (
                      <ShieldCheck className="h-4 w-4 text-sky-500" />
                    )}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold truncate">{dept.name}</p>
                    {dept.is_coordinator && <p className="text-xs text-amber-500">Issues the final Go / Conditional Go / No Go decision</p>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Reports */}
        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
            <FileSearch className="h-5 w-5 text-sky-500" /> Release Excellence Reports
          </h2>
          <p className="text-sm text-muted-foreground mb-4">Every Release Excellence Report the division has produced.</p>
          {reports.length === 0 ? (
            <p className="text-sm text-muted-foreground">No reports yet. Request a Release Excellence Report above.</p>
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
                        {report.release_version ? ` · ${report.release_version}` : ""}
                      </p>
                    </div>
                    {report.quality_score != null && (
                      <span className={`text-xs font-bold ${scoreColor(report.quality_score)}`}>
                        {report.quality_score}/100
                      </span>
                    )}
                    {report.final_decision && report.final_decision !== "pending" && (
                      <span className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${decisionStyle[report.final_decision] || decisionStyle.pending}`}>
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

                          {detail.quality_score != null && (
                            <div className="rounded-lg border border-sky-500/30 bg-sky-500/5 p-4">
                              <div className="flex flex-wrap items-center gap-4">
                                <div>
                                  <p className="text-sm text-muted-foreground">Overall Quality Score</p>
                                  <p className={`text-3xl font-bold ${scoreColor(detail.quality_score)}`}>{detail.quality_score}/100</p>
                                </div>
                                {detail.final_decision && detail.final_decision !== "pending" && (
                                  <div>
                                    <p className="text-sm text-muted-foreground">Final Decision</p>
                                    <span className={`inline-block rounded-full border px-3 py-1 text-sm font-bold ${decisionStyle[detail.final_decision] || decisionStyle.pending}`}>
                                      {detail.final_decision}
                                    </span>
                                  </div>
                                )}
                                <p className="text-sm text-muted-foreground flex-1">
                                  {detail.executive_summary || "Release Excellence Report completed. See the certificate for the final decision."}
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
                                      ? `${r.score != null ? `${r.score}/100 · ` : ""}${Math.round(r.confidence * 100)}% confidence · ${r.checks.length} checks · ${r.findings.length} findings`
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

                          {/* Findings */}
                          <div className="grid gap-4 md:grid-cols-2">
                            <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-4">
                              <h4 className="text-sm font-semibold mb-1.5 flex items-center gap-1.5">
                                <AlertTriangle className="h-3.5 w-3.5 text-red-500" /> Known Risks
                              </h4>
                              <ul className="space-y-1">
                                {detail.known_risks.map((item, i) => (
                                  <li key={i} className="text-xs text-muted-foreground">- {item}</li>
                                ))}
                              </ul>
                            </div>
                            <div className="rounded-lg border border-sky-500/30 bg-sky-500/5 p-4">
                              <h4 className="text-sm font-semibold mb-1.5 flex items-center gap-1.5">
                                <RotateCcw className="h-3.5 w-3.5 text-sky-500" /> Rollback Strategy
                              </h4>
                              <ul className="space-y-1">
                                {detail.rollback_strategy.map((item, i) => (
                                  <li key={i} className="text-xs text-muted-foreground">- {item}</li>
                                ))}
                              </ul>
                            </div>
                          </div>

                          {/* Report sections */}
                          <div className="grid gap-4 md:grid-cols-2">
                            {sectionBlock("Functional QA", detail.functional_qa)}
                            {sectionBlock("Performance Review", detail.performance_review)}
                            {sectionBlock("Security Review", detail.security_review)}
                            {sectionBlock("Compliance Review", detail.compliance_review)}
                            {sectionBlock("Accessibility Review", detail.accessibility_review)}
                            {sectionBlock("Documentation Status", detail.documentation_status)}
                            {sectionBlock("Architecture Review", detail.architecture_review)}
                            {sectionBlock("Deployment Readiness", detail.deployment_readiness)}
                            {sectionBlock("Monitoring Status", detail.monitoring_status)}
                            {sectionBlock("Enterprise Readiness", detail.enterprise_readiness)}
                          </div>

                          {detail.release_certificate && (
                            <div className="rounded-lg border border-sky-500/30 bg-sky-500/5 p-4">
                              <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
                                <ScrollText className="h-4 w-4" /> Release Certificate
                              </h3>
                              <pre className="text-xs whitespace-pre-wrap font-sans text-muted-foreground max-h-96 overflow-y-auto">
                                {detail.release_certificate}
                              </pre>
                            </div>
                          )}

                          {!detail.release_certificate && detail.executive_summary && (
                            <div className="rounded-lg border border-sky-500/30 bg-sky-500/5 p-4">
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
                              href={`${API}/api/quality/reports/${report.id}/export`}
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
          <ShieldCheck className="h-4 w-4" />
          Nothing reaches customers without approval from this division. The Release Director issues the
          formal Go / Conditional Go / No Go decision and a release certificate - the final gate before production.
        </div>
      </div>
    </DashboardLayout>
  )
}
