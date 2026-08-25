"use client"

import { useEffect, useState } from "react"
import { DashboardLayout } from "@/components/layout/dashboard-layout"
import {
  TrendingUp,
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
  Target,
  Sparkles,
  Crown,
} from "lucide-react"

const API = "http://127.0.0.1:8001"

const SUBJECT_TYPES = [
  { id: "landing_page", label: "Landing Page" },
  { id: "product", label: "Product Experience" },
  { id: "onboarding", label: "Onboarding Flow" },
  { id: "pricing", label: "Pricing & Monetization" },
  { id: "whole_business", label: "Whole Business" },
]

interface Dept {
  id: string
  name: string
  title: string
  order: number
  is_coordinator: boolean
}

interface GrowthStats {
  total: number
  in_progress: number
  completed: number
  failed: number
  avg_confidence: number | null
  avg_growth_score: number | null
  total_opportunities: number
  total_metrics: number
  departments: number
}

interface ReviewSummary {
  id: string
  request: string
  subject_type: string
  status: string
  stage: string
  created_at: string
  avg_confidence: number | null
  growth_score: number | null
  total_opportunities: number
  total_metrics: number
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
  metrics: string[]
  opportunities: string[]
  findings: string[]
  recommendations: string[]
  evidence: string[]
  status: string
  error: string
}

interface ReviewDetail {
  id: string
  request: string
  subject_type: string
  status: string
  stage: string
  created_at: string
  completed_at: string | null
  reports: DeptReport[]
  growth_score: number | null
  conversion_analysis: string[]
  landing_page_audit: string[]
  acquisition_opportunities: string[]
  activation_improvements: string[]
  retention_strategy: string[]
  pricing_recommendations: string[]
  customer_success_insights: string[]
  customer_feedback_summary: string[]
  analytics_findings: string[]
  experiment_recommendations: string[]
  trust_credibility_assessment: string[]
  quick_wins: string[]
  high_impact_projects: string[]
  estimated_business_impact: string[]
  implementation_specification: string
  executive_summary: string
  avg_confidence: number | null
  total_opportunities: number
  total_metrics: number
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

export default function GrowthPage() {
  const [stats, setStats] = useState<GrowthStats | null>(null)
  const [departments, setDepartments] = useState<Dept[]>([])
  const [reviews, setReviews] = useState<ReviewSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [apiDown, setApiDown] = useState(false)

  const [requestText, setRequestText] = useState("")
  const [subjectType, setSubjectType] = useState("landing_page")
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState("")

  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<ReviewDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [sending, setSending] = useState<string | null>(null)
  const [lastAction, setLastAction] = useState("")

  const fetchOverview = () => {
    Promise.all([
      fetch(`${API}/api/growth/stats`).then((r) => r.json()),
      fetch(`${API}/api/growth/departments`).then((r) => r.json()),
      fetch(`${API}/api/growth/reviews`).then((r) => r.json()),
    ])
      .then(([statsData, deptData, reviewData]) => {
        setStats(statsData || null)
        setDepartments(deptData.departments || [])
        setReviews(reviewData.reviews || [])
        setLoading(false)
        setApiDown(false)
      })
      .catch(() => {
        setLoading(false)
        setApiDown(true)
      })
  }

  useEffect(() => { fetchOverview() }, [])

  const submitReview = () => {
    if (!requestText.trim()) return
    setSubmitting(true)
    setSubmitError("")
    setLastAction("")
    fetch(`${API}/api/growth/reviews`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request: requestText.trim(), subject_type: subjectType, wait: false }),
    })
      .then((r) => r.json())
      .then(async (data) => {
        if (data.error) throw new Error(data.error)
        const reviewId = data.review_id || (data.review && data.review.id)
        if (!reviewId) throw new Error("No review id returned")
        await pollUntilDone(reviewId)
        setRequestText("")
        fetchOverview()
      })
      .catch((e) => setSubmitError(e.message || "Submission failed"))
      .finally(() => setSubmitting(false))
  }

  const pollUntilDone = (reviewId: string, attempts = 0): Promise<void> => {
    return fetch(`${API}/api/growth/reviews/${reviewId}`)
      .then((r) => r.json())
      .then((data) => {
        const reviewDetail = data.review
        if (reviewDetail && (reviewDetail.status === "completed" || reviewDetail.status === "failed" || reviewDetail.status === "cancelled")) {
          setLastAction(`Growth Intelligence Report finished: ${reviewDetail.status}`)
          return
        }
        if (reviewDetail && attempts % 15 === 0) {
          setLastAction(`Growth review in progress: ${reviewDetail.departments_completed}/${reviewDetail.total_departments} departments (${reviewDetail.stage})`)
        }
        if (attempts > 7200) throw new Error("Timed out waiting for Growth Intelligence Report")
        return new Promise((resolve) => setTimeout(resolve, 2000)).then(() =>
          pollUntilDone(reviewId, attempts + 1)
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
    fetch(`${API}/api/growth/reviews/${id}`)
      .then((r) => r.json())
      .then((data) => setDetail(data.review))
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false))
  }

  const sendToBoard = (id: string) => {
    setSending(id)
    setLastAction("")
    fetch(`${API}/api/growth/reviews/${id}/to-board`, { method: "POST" })
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
          <p className="text-muted-foreground">Loading Growth division...</p>
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
              <TrendingUp className="h-8 w-8 text-emerald-500" />
              Growth, Conversion &amp; Customer Success
              <span className="text-sm font-medium text-muted-foreground bg-secondary/60 rounded-full px-3 py-1">Layer 6</span>
            </h1>
            <p className="text-muted-foreground mt-1">
              Eleven departments optimize the entire customer lifecycle - conversion, landing pages, acquisition,
              onboarding, customer success, retention, pricing, feedback, analytics, experimentation, and trust.
              The Growth Director merges everything into a Growth Intelligence Report the Frontend and Backend
              Development Agents implement. Everything is measured; nothing is based on opinions.
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
            <p className="text-sm text-muted-foreground">Growth Reviews</p>
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
              <Scale className="h-3.5 w-3.5 text-primary" /> Avg Growth Score
            </p>
            <p className={`text-3xl font-bold mt-1 ${stats?.avg_growth_score != null ? scoreColor(stats.avg_growth_score) : ""}`}>
              {stats?.avg_growth_score != null ? `${stats.avg_growth_score}/100` : "—"}
            </p>
          </div>
          <div className="rounded-lg border border-border bg-card p-6">
            <p className="text-sm text-muted-foreground">Opportunities &amp; Metrics</p>
            <p className="text-3xl font-bold mt-1">{stats?.total_opportunities || 0}</p>
            <p className="text-xs text-muted-foreground">{stats?.total_metrics || 0} tracked metrics</p>
          </div>
        </div>

        {/* Submit subject */}
        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
            <Send className="h-5 w-5 text-emerald-500" /> Request Growth Intelligence Report
          </h2>
          <p className="text-sm text-muted-foreground mb-4">
            Describe the growth subject. All eleven growth departments assess it, then the Growth Director
            writes one report with prioritized opportunities, quick wins, high-impact projects, estimated
            business impact, and an implementation-ready specification for the development agents.
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
                placeholder="e.g. Improve our recruitment SaaS. Move the primary CTA above the fold, add employer testimonials and a pricing comparison, add a demo request flow, and shorten the lead form..."
                rows={2}
                className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
              />
              <button
                onClick={submitReview}
                disabled={submitting || !requestText.trim()}
                className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50 self-end"
              >
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : "Run Growth Review"}
              </button>
            </div>
          </div>
          {submitError && <p className="mt-2 text-sm text-red-500">{submitError}</p>}
          {submitting && (
            <p className="mt-3 text-sm text-muted-foreground flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" /> Eleven growth departments are assessing (this can take a few minutes)...
            </p>
          )}
        </div>

        {/* Department roster */}
        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
            <Layers className="h-5 w-5 text-emerald-500" /> Growth Departments
          </h2>
          <p className="text-sm text-muted-foreground mb-4">The twelve departments that own the customer lifecycle.</p>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {departments.map((dept) => (
              <div key={dept.id} className="rounded-lg border border-border/50 bg-background/50 p-4">
                <div className="flex items-center gap-3">
                  <div className={`rounded-lg p-2 ${dept.is_coordinator ? "bg-amber-500/10" : "bg-emerald-500/10"}`}>
                    {dept.is_coordinator ? (
                      <Crown className="h-4 w-4 text-amber-500" />
                    ) : (
                      <Rocket className="h-4 w-4 text-emerald-500" />
                    )}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold truncate">{dept.name}</p>
                    {dept.is_coordinator && <p className="text-xs text-amber-500">Merges findings into the report + implementation spec</p>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Reviews */}
        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
            <FileSearch className="h-5 w-5 text-emerald-500" /> Growth Intelligence Reports
          </h2>
          <p className="text-sm text-muted-foreground mb-4">Every Growth Intelligence Report the division has produced.</p>
          {reviews.length === 0 ? (
            <p className="text-sm text-muted-foreground">No reports yet. Request a Growth Intelligence Report above.</p>
          ) : (
            <div className="space-y-2">
              {reviews.map((review) => (
                <div key={review.id} className="rounded-lg border border-border/50 bg-background/50">
                  <button
                    onClick={() => toggleDetail(review.id)}
                    className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-secondary/40 transition-colors"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold truncate">{review.request}</p>
                      <p className="text-xs text-muted-foreground">
                        {new Date(review.created_at).toLocaleString()} · {review.departments_completed}/{review.total_departments} departments ·{" "}
                        {SUBJECT_TYPES.find((s) => s.id === review.subject_type)?.label || review.subject_type}
                      </p>
                    </div>
                    {review.growth_score != null && (
                      <span className={`text-xs font-bold ${scoreColor(review.growth_score)}`}>
                        {review.growth_score}/100
                      </span>
                    )}
                    <span
                      className={`rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${statusStyle[review.status] || "border-border bg-secondary/60 text-muted-foreground"}`}
                    >
                      {review.status}
                    </span>
                  </button>

                  {expandedId === review.id && (
                    <div className="border-t border-border/50 px-4 py-4">
                      {detailLoading ? (
                        <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
                          <Loader2 className="h-4 w-4 animate-spin" /> Loading report...
                        </div>
                      ) : detail ? (
                        <div className="space-y-4">
                          {detail.error && <p className="text-sm text-red-500">Error: {detail.error}</p>}

                          {detail.growth_score != null && (
                            <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4 flex items-center gap-4">
                              <div>
                                <p className="text-sm text-muted-foreground">Overall Growth Score</p>
                                <p className={`text-3xl font-bold ${scoreColor(detail.growth_score)}`}>{detail.growth_score}/100</p>
                              </div>
                              <p className="text-sm text-muted-foreground flex-1">
                                {detail.executive_summary || "Growth Intelligence Report completed. See the specification for what to build."}
                              </p>
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
                                      ? `${r.score != null ? `${r.score}/100 · ` : ""}${Math.round(r.confidence * 100)}% confidence · ${r.metrics.length} metrics · ${r.opportunities.length} opportunities`
                                      : r.status}
                                  </p>
                                  {r.status === "failed" && r.error && (
                                    <p className="text-xs text-red-500 mt-1" title={r.error}>{r.error}</p>
                                  )}
                                  {r.status === "completed" && r.opportunities.length > 0 && (
                                    <ul className="mt-1.5 space-y-0.5">
                                      {r.opportunities.slice(0, 3).map((o, i) => (
                                        <li key={i} className="text-xs text-muted-foreground">- {o}</li>
                                      ))}
                                    </ul>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>

                          {/* Metrics */}
                          <div className="grid gap-4 md:grid-cols-2">
                            <div>
                              <h4 className="text-sm font-semibold mb-1.5">Tracked Metrics</h4>
                              <ul className="space-y-1">
                                {detail.reports
                                  .filter((r) => r.status === "completed")
                                  .flatMap((r) => r.metrics)
                                  .filter((m, i, arr) => arr.indexOf(m) === i)
                                  .slice(0, 16)
                                  .map((m, i) => (
                                    <li key={i} className="text-xs text-muted-foreground">- {m}</li>
                                  ))}
                              </ul>
                            </div>
                            <div>
                              <h4 className="text-sm font-semibold mb-1.5 flex items-center gap-1.5">
                                <Target className="h-3.5 w-3.5 text-emerald-500" /> Estimated Business Impact
                              </h4>
                              <ul className="space-y-1">
                                {detail.estimated_business_impact.map((imp, i) => (
                                  <li key={i} className="text-xs text-muted-foreground">- {imp}</li>
                                ))}
                              </ul>
                            </div>
                          </div>

                          {/* Report sections */}
                          <div className="grid gap-4 md:grid-cols-2">
                            {sectionBlock("Conversion Analysis", detail.conversion_analysis)}
                            {sectionBlock("Landing Page Audit", detail.landing_page_audit)}
                            {sectionBlock("Acquisition Opportunities", detail.acquisition_opportunities)}
                            {sectionBlock("Activation Improvements", detail.activation_improvements)}
                            {sectionBlock("Retention Strategy", detail.retention_strategy)}
                            {sectionBlock("Pricing Recommendations", detail.pricing_recommendations)}
                            {sectionBlock("Customer Success Insights", detail.customer_success_insights)}
                            {sectionBlock("Customer Feedback Summary", detail.customer_feedback_summary)}
                            {sectionBlock("Analytics Findings", detail.analytics_findings)}
                            {sectionBlock("Experiment Recommendations", detail.experiment_recommendations)}
                            {sectionBlock("Trust & Credibility Assessment", detail.trust_credibility_assessment)}
                            {sectionBlock("Quick Wins", detail.quick_wins)}
                            {sectionBlock("High Impact Projects", detail.high_impact_projects)}
                          </div>

                          {detail.implementation_specification && (
                            <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4">
                              <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
                                <Sparkles className="h-4 w-4" /> Implementation-Ready Specification for Development Agents
                              </h3>
                              <pre className="text-xs whitespace-pre-wrap font-sans text-muted-foreground max-h-96 overflow-y-auto">
                                {detail.implementation_specification}
                              </pre>
                            </div>
                          )}

                          {!detail.implementation_specification && detail.executive_summary && (
                            <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4">
                              <h3 className="text-sm font-semibold mb-1">Executive Summary</h3>
                              <p className="text-sm text-muted-foreground">{detail.executive_summary}</p>
                            </div>
                          )}

                          {/* Actions */}
                          <div className="flex flex-wrap gap-2 pt-1">
                            {review.status === "completed" && (
                              <button
                                onClick={() => sendToBoard(review.id)}
                                disabled={sending === review.id || detail.board_review_id != null}
                                className="rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
                              >
                                {sending === review.id ? (
                                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                ) : (
                                  <ExternalLink className="h-3.5 w-3.5 inline mr-1" />
                                )}
                                {detail.board_review_id ? "Sent to Board" : "Send to Board"}
                              </button>
                            )}
                            <a
                              href={`${API}/api/growth/reviews/${review.id}/export`}
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
          <TrendingUp className="h-4 w-4" />
          The Growth Division never builds features itself - it delivers an implementation-ready
          Growth Intelligence Report that the Frontend and Backend Development Agents implement as
          tasks. Everything is measured; nothing is based on opinions.
        </div>
      </div>
    </DashboardLayout>
  )
}
