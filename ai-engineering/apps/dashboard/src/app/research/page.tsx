"use client"

import { useEffect, useState } from "react"
import { DashboardLayout } from "@/components/layout/dashboard-layout"
import {
  FlaskConical,
  Microscope,
  Loader2,
  Send,
  Scale,
  CheckCircle2,
  RefreshCw,
  ExternalLink,
  FileDown,
  Layers,
  FileSearch,
  Crosshair,
} from "lucide-react"

const API = "http://127.0.0.1:8001"

const SUBJECT_TYPES = [
  { id: "new_product", label: "New Product" },
  { id: "existing_product", label: "Existing Product" },
  { id: "market", label: "Market / Industry" },
  { id: "competitor", label: "Competitor" },
  { id: "feature", label: "Feature" },
]

interface Dept {
  id: string
  name: string
  title: string
  order: number
  is_coordinator: boolean
}

interface ResearchStats {
  total: number
  in_progress: number
  completed: number
  failed: number
  avg_confidence: number | null
  total_recommendations: number
  departments: number
}

interface DossierSummary {
  id: string
  request: string
  subject_type: string
  status: string
  stage: string
  created_at: string
  avg_confidence: number | null
  total_recommendations: number
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
  findings: string[]
  recommendations: string[]
  evidence: string[]
  status: string
  error: string
}

interface DossierDetail {
  id: string
  request: string
  subject_type: string
  status: string
  stage: string
  created_at: string
  completed_at: string | null
  reports: DeptReport[]
  research_summary: string
  business_objective: string
  customer_needs: string[]
  market_insights: string[]
  competitor_findings: string[]
  missing_features: string[]
  ux_risks: string[]
  growth_opportunities: string[]
  security_considerations: string[]
  industry_expectations: string[]
  pricing_suggestions: string[]
  recommended_priorities: string[]
  confidence_levels: string[]
  evidence_sources: string[]
  executive_summary: string
  avg_confidence: number | null
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

function p0Class(feature: string): string {
  if (feature.startsWith("[P0]")) return "text-green-500"
  if (feature.startsWith("[P1]")) return "text-amber-500"
  return "text-muted-foreground"
}

export default function ResearchPage() {
  const [stats, setStats] = useState<ResearchStats | null>(null)
  const [departments, setDepartments] = useState<Dept[]>([])
  const [dossiers, setDossiers] = useState<DossierSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [apiDown, setApiDown] = useState(false)

  const [requestText, setRequestText] = useState("")
  const [subjectType, setSubjectType] = useState("new_product")
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState("")

  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<DossierDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [sending, setSending] = useState<string | null>(null)
  const [lastAction, setLastAction] = useState("")

  const fetchOverview = () => {
    Promise.all([
      fetch(`${API}/api/research/stats`).then((r) => r.json()),
      fetch(`${API}/api/research/departments`).then((r) => r.json()),
      fetch(`${API}/api/research/dossiers`).then((r) => r.json()),
    ])
      .then(([statsData, deptData, dossierData]) => {
        setStats(statsData || null)
        setDepartments(deptData.departments || [])
        setDossiers(dossierData.dossiers || [])
        setLoading(false)
        setApiDown(false)
      })
      .catch(() => {
        setLoading(false)
        setApiDown(true)
      })
  }

  useEffect(() => { fetchOverview() }, [])

  const submitResearch = () => {
    if (!requestText.trim()) return
    setSubmitting(true)
    setSubmitError("")
    setLastAction("")
    fetch(`${API}/api/research/dossiers`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request: requestText.trim(), subject_type: subjectType, wait: false }),
    })
      .then((r) => r.json())
      .then(async (data) => {
        if (data.error) throw new Error(data.error)
        const dossierId = data.dossier_id || (data.dossier && data.dossier.id)
        if (!dossierId) throw new Error("No dossier id returned")
        await pollUntilDone(dossierId)
        setRequestText("")
        fetchOverview()
      })
      .catch((e) => setSubmitError(e.message || "Submission failed"))
      .finally(() => setSubmitting(false))
  }

  const pollUntilDone = (dossierId: string, attempts = 0): Promise<void> => {
    return fetch(`${API}/api/research/dossiers/${dossierId}`)
      .then((r) => r.json())
      .then((data) => {
        const dossier = data.dossier
        if (dossier && (dossier.status === "completed" || dossier.status === "failed" || dossier.status === "cancelled")) {
          setLastAction(`Research finished: ${dossier.status}`)
          return
        }
        if (attempts > 400) throw new Error("Timed out waiting for research")
        return new Promise((resolve) => setTimeout(resolve, 2000)).then(() =>
          pollUntilDone(dossierId, attempts + 1)
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
    fetch(`${API}/api/research/dossiers/${id}`)
      .then((r) => r.json())
      .then((data) => setDetail(data.dossier))
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false))
  }

  const sendToBoard = (id: string) => {
    setSending(id)
    setLastAction("")
    fetch(`${API}/api/research/dossiers/${id}/to-board`, { method: "POST" })
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
          <p className="text-muted-foreground">Loading research division...</p>
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

  const sectionBlock = (title: string, items: string[], priority?: boolean) =>
    items.length > 0 && (
      <div>
        <h4 className="text-sm font-semibold mb-1.5">{title}</h4>
        <ul className="space-y-1">
          {items.map((item, i) => (
            <li key={i} className={`text-xs ${priority ? p0Class(item) : "text-muted-foreground"}`}>
              {item}
            </li>
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
              <Microscope className="h-8 w-8 text-primary" />
              Product Research & Discovery
              <span className="text-sm font-medium text-muted-foreground bg-secondary/60 rounded-full px-3 py-1">Layer 3</span>
            </h1>
            <p className="text-muted-foreground mt-1">
              Ten departments gather evidence about customer needs, markets, competitors, missing features,
              positioning, trends, pricing, and industry standards - then the Research Coordinator merges it
              into one dossier for the Executive Product Board.
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
            <p className="text-sm text-muted-foreground">Dossiers</p>
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
              <Scale className="h-3.5 w-3.5 text-primary" /> Avg Confidence
            </p>
            <p className="text-3xl font-bold mt-1 text-primary">
              {stats?.avg_confidence != null ? `${Math.round(stats.avg_confidence * 100)}%` : "—"}
            </p>
          </div>
          <div className="rounded-lg border border-border bg-card p-6">
            <p className="text-sm text-muted-foreground">Recommendations</p>
            <p className="text-3xl font-bold mt-1">{stats?.total_recommendations || 0}</p>
            <p className="text-xs text-muted-foreground">across all dossiers</p>
          </div>
        </div>

        {/* Submit research subject */}
        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
            <Send className="h-5 w-5 text-primary" /> Request Research
          </h2>
          <p className="text-sm text-muted-foreground mb-4">
            Describe the subject. All nine research departments investigate it, then the Coordinator
            writes one dossier with confidence levels and evidence.
          </p>
          <div className="flex flex-col gap-2">
            <div className="flex gap-2">
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
                placeholder="e.g. Build a mobile-first invoicing app for freelancers and micro businesses..."
                rows={2}
                className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
              />
              <button
                onClick={submitResearch}
                disabled={submitting || !requestText.trim()}
                className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50 self-end"
              >
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : "Run Research"}
              </button>
            </div>
          </div>
          {submitError && <p className="mt-2 text-sm text-red-500">{submitError}</p>}
          {submitting && (
            <p className="mt-3 text-sm text-muted-foreground flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" /> Nine departments are researching (this can take a few minutes)...
            </p>
          )}
        </div>

        {/* Department roster */}
        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
            <Layers className="h-5 w-5 text-primary" /> Research Departments
          </h2>
          <p className="text-sm text-muted-foreground mb-4">The ten departments that gather evidence.</p>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {departments.map((dept) => (
              <div key={dept.id} className="rounded-lg border border-border/50 bg-background/50 p-4">
                <div className="flex items-center gap-3">
                  <div className={`rounded-lg p-2 ${dept.is_coordinator ? "bg-amber-500/10" : "bg-primary/10"}`}>
                    {dept.is_coordinator ? (
                      <Crosshair className="h-4 w-4 text-amber-500" />
                    ) : (
                      <FlaskConical className="h-4 w-4 text-primary" />
                    )}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold truncate">{dept.name}</p>
                    {dept.is_coordinator && <p className="text-xs text-amber-500">Merges findings into the dossier</p>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Dossiers */}
        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
            <FileSearch className="h-5 w-5 text-primary" /> Research Dossiers
          </h2>
          <p className="text-sm text-muted-foreground mb-4">Every research dossier the division has produced.</p>
          {dossiers.length === 0 ? (
            <p className="text-sm text-muted-foreground">No dossiers yet. Request research above.</p>
          ) : (
            <div className="space-y-2">
              {dossiers.map((dossier) => (
                <div key={dossier.id} className="rounded-lg border border-border/50 bg-background/50">
                  <button
                    onClick={() => toggleDetail(dossier.id)}
                    className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-secondary/40 transition-colors"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold truncate">{dossier.request}</p>
                      <p className="text-xs text-muted-foreground">
                        {new Date(dossier.created_at).toLocaleString()} · {dossier.departments_completed}/{dossier.total_departments} departments ·{" "}
                        {SUBJECT_TYPES.find((s) => s.id === dossier.subject_type)?.label || dossier.subject_type}
                      </p>
                    </div>
                    {dossier.avg_confidence != null && (
                      <span className="text-xs font-bold text-muted-foreground">
                        {Math.round(dossier.avg_confidence * 100)}% conf
                      </span>
                    )}
                    <span
                      className={`rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${statusStyle[dossier.status] || "border-border bg-secondary/60 text-muted-foreground"}`}
                    >
                      {dossier.status}
                    </span>
                  </button>

                  {expandedId === dossier.id && (
                    <div className="border-t border-border/50 px-4 py-4">
                      {detailLoading ? (
                        <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
                          <Loader2 className="h-4 w-4 animate-spin" /> Loading dossier...
                        </div>
                      ) : detail ? (
                        <div className="space-y-4">
                          {detail.error && <p className="text-sm text-red-500">Error: {detail.error}</p>}

                          {detail.research_summary && (
                            <div>
                              <h3 className="text-sm font-semibold mb-1">Research Summary</h3>
                              <p className="text-sm text-muted-foreground">{detail.research_summary}</p>
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
                                    {r.status === "completed" ? `${Math.round(r.confidence * 100)}% confidence` : r.status}
                                  </p>
                                  {r.status === "failed" && r.error && (
                                    <p className="text-xs text-red-500 mt-1" title={r.error}>{r.error}</p>
                                  )}
                                  {r.status === "completed" && r.recommendations.length > 0 && (
                                    <ul className="mt-1.5 space-y-0.5">
                                      {r.recommendations.slice(0, 3).map((rec, i) => (
                                        <li key={i} className="text-xs text-muted-foreground">- {rec}</li>
                                      ))}
                                    </ul>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>

                          {/* Dossier sections */}
                          <div className="grid gap-4 md:grid-cols-2">
                            {sectionBlock("Customer Needs", detail.customer_needs)}
                            {sectionBlock("Market Insights", detail.market_insights)}
                            {sectionBlock("Competitor Findings", detail.competitor_findings)}
                            {sectionBlock("Missing Features", detail.missing_features, true)}
                            {sectionBlock("UX Risks", detail.ux_risks)}
                            {sectionBlock("Growth Opportunities", detail.growth_opportunities)}
                            {sectionBlock("Security Considerations", detail.security_considerations)}
                            {sectionBlock("Industry Expectations", detail.industry_expectations)}
                            {sectionBlock("Pricing Suggestions", detail.pricing_suggestions)}
                            {sectionBlock("Recommended Priorities", detail.recommended_priorities, true)}
                          </div>

                          {sectionBlock("Confidence Levels", detail.confidence_levels)}
                          {sectionBlock("Evidence Sources", detail.evidence_sources)}

                          {detail.executive_summary && (
                            <div className="rounded-lg border border-primary/30 bg-primary/5 p-4">
                              <h3 className="text-sm font-semibold mb-1">Executive Summary</h3>
                              <p className="text-sm text-muted-foreground">{detail.executive_summary}</p>
                            </div>
                          )}

                          {/* Actions */}
                          <div className="flex flex-wrap gap-2 pt-1">
                            {dossier.status === "completed" && (
                              <button
                                onClick={() => sendToBoard(dossier.id)}
                                disabled={sending === dossier.id || detail.board_review_id != null}
                                className="rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
                              >
                                {sending === dossier.id ? (
                                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                ) : (
                                  <ExternalLink className="h-3.5 w-3.5 inline mr-1" />
                                )}
                                {detail.board_review_id ? "Sent to Board" : "Send to Board"}
                              </button>
                            )}
                            <a
                              href={`${API}/api/research/dossiers/${dossier.id}/export`}
                              target="_blank"
                              rel="noreferrer"
                              className="rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-secondary"
                            >
                              <FileDown className="h-3.5 w-3.5 inline mr-1" /> Export
                            </a>
                          </div>
                        </div>
                      ) : (
                        <p className="text-sm text-red-500">Failed to load dossier detail.</p>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <FileSearch className="h-4 w-4" />
          Every recommendation carries a confidence level and evidence. The Executive Product Board requests
          research here before approving major product work.
        </div>
      </div>
    </DashboardLayout>
  )
}
