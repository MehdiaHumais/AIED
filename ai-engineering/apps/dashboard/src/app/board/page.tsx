"use client"

import { useEffect, useState } from "react"
import { DashboardLayout } from "@/components/layout/dashboard-layout"
import {
  Crown,
  Gavel,
  Loader2,
  Send,
  Users,
  UserCheck,
  Scale,
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
  ExternalLink,
  ClipboardList,
  FileDown,
} from "lucide-react"

const API = "http://127.0.0.1:8001"

interface Member {
  id: string
  name: string
  title: string
  score_category: string | null
  order: number
}

interface BoardStats {
  total: number
  in_review: number
  approved: number
  revision: number
  rejected: number
  failed: number
  avg_score: number | null
  approve_threshold: number
}

interface ReviewSummary {
  id: string
  request: string
  status: string
  stage: string
  total_score: number | null
  final_verdict: string
  project_id: string | null
  created_at: string
  completed_at: string | null
  scored_members: number
  total_members: number
}

interface ScorecardEntry {
  category: string
  label: string
  weight: number
  score: number | null
  weighted: number | null
  member_id: string
  member_name: string
  scored: boolean
}

interface Verdict {
  member_id: string
  member_name: string
  score: number
  verdict: string
  findings: string[]
  recommendations: string[]
  status: string
  error: string
}

interface ReviewDetail {
  id: string
  request: string
  status: string
  stage: string
  total_score: number | null
  final_verdict: string
  project_id: string | null
  created_at: string
  completed_at: string | null
  strategist_scope: string
  verdicts: Verdict[]
  scorecard: ScorecardEntry[]
  decision: Record<string, any>
  decision_markdown: string
  error: string
}

const verdictStyle: Record<string, string> = {
  approved: "bg-green-500/10 text-green-500 border-green-500/30",
  revision: "bg-amber-500/10 text-amber-500 border-amber-500/30",
  rejected: "bg-red-500/10 text-red-500 border-red-500/30",
  failed: "bg-red-500/10 text-red-500 border-red-500/30",
  pending: "bg-blue-500/10 text-blue-500 border-blue-500/30",
  in_review: "bg-blue-500/10 text-blue-500 border-blue-500/30",
  cancelled: "bg-zinc-500/10 text-zinc-400 border-zinc-500/30",
}

export default function BoardPage() {
  const [stats, setStats] = useState<BoardStats | null>(null)
  const [members, setMembers] = useState<Member[]>([])
  const [reviews, setReviews] = useState<ReviewSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [apiDown, setApiDown] = useState(false)

  const [requestText, setRequestText] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState("")

  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<ReviewDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [creatingProject, setCreatingProject] = useState<string | null>(null)
  const [lastAction, setLastAction] = useState("")

  const fetchOverview = () => {
    Promise.all([
      fetch(`${API}/api/board/stats`).then((r) => r.json()),
      fetch(`${API}/api/board/members`).then((r) => r.json()),
      fetch(`${API}/api/board/reviews`).then((r) => r.json()),
    ])
      .then(([statsData, membersData, reviewsData]) => {
        setStats(statsData || null)
        setMembers(membersData.members || [])
        setReviews(reviewsData.reviews || [])
        setLoading(false)
        setApiDown(false)
      })
      .catch(() => {
        setLoading(false)
        setApiDown(true)
      })
  }

  useEffect(() => { fetchOverview() }, [])

  const submitReview = (overrideText?: any) => {
    const textToSubmit = (typeof overrideText === "string" ? overrideText : requestText).trim()
    if (!textToSubmit) return
    setRequestText(textToSubmit)
    setSubmitting(true)
    setSubmitError("")
    setLastAction("Submitting proposal review to board...")
    window.scrollTo({ top: 0, behavior: "smooth" })
    fetch(`${API}/api/board/reviews`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request: textToSubmit, wait: false }),
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
    return fetch(`${API}/api/board/reviews/${reviewId}`)
      .then((r) => r.json())
      .then((data) => {
        const review = data.review
        if (review && (review.status === "completed" || review.status === "failed" || review.status === "cancelled")) {
          setLastAction(`Review finished: ${review.final_verdict}`)
          return
        }
        if (attempts > 300) throw new Error("Timed out waiting for review")
        return new Promise((resolve) => setTimeout(resolve, 1500)).then(() =>
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
    fetch(`${API}/api/board/reviews/${id}`)
      .then((r) => r.json())
      .then((data) => setDetail(data.review))
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false))
  }

  const createProject = (id: string) => {
    setCreatingProject(id)
    setLastAction("")
    fetch(`${API}/api/board/reviews/${id}/create-project`, { method: "POST" })
      .then((r) => r.json())
      .then((data) => {
        if (data.error) throw new Error(data.error)
        setLastAction(`Project created: ${data.project_name} (${data.tasks_created} tasks)`)
        fetchOverview()
      })
      .catch((e) => setLastAction(`Create project failed: ${e.message}`))
      .finally(() => setCreatingProject(null))
  }

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <p className="text-muted-foreground">Loading board...</p>
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

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
              <Gavel className="h-8 w-8 text-primary" />
              Executive Product Board
              <span className="text-sm font-medium text-muted-foreground bg-secondary/60 rounded-full px-3 py-1">Layer 2</span>
            </h1>
            <p className="text-muted-foreground mt-1">
              Nine executives review every product request before development. The board emits a weighted
              scorecard and a binding Decision Package for the engineering team.
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
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
          <div className="rounded-lg border border-border bg-card p-6">
            <p className="text-sm text-muted-foreground">Reviews</p>
            <p className="text-3xl font-bold mt-1">{stats?.total || 0}</p>
            <p className="text-xs text-muted-foreground">{stats?.in_review || 0} in review</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-6">
            <p className="text-sm text-muted-foreground flex items-center gap-1.5">
              <CheckCircle2 className="h-3.5 w-3.5 text-green-500" /> Approved
            </p>
            <p className="text-3xl font-bold mt-1 text-green-500">{stats?.approved || 0}</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-6">
            <p className="text-sm text-muted-foreground flex items-center gap-1.5">
              <AlertTriangle className="h-3.5 w-3.5 text-amber-500" /> Revision
            </p>
            <p className="text-3xl font-bold mt-1 text-amber-500">{stats?.revision || 0}</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-6">
            <p className="text-sm text-muted-foreground">Avg Score</p>
            <p className="text-3xl font-bold mt-1">
              {stats?.avg_score != null ? `${stats.avg_score}%` : "—"}
            </p>
          </div>
          <div className="rounded-lg border border-border bg-card p-6">
            <p className="text-sm text-muted-foreground flex items-center gap-1.5">
              <Scale className="h-3.5 w-3.5 text-primary" /> Approve Threshold
            </p>
            <p className="text-3xl font-bold mt-1 text-primary">{stats?.approve_threshold || 0}%</p>
          </div>
        </div>

        {/* Submit request */}
        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
            <Send className="h-5 w-5 text-primary" /> Submit a Product Request
          </h2>
          <p className="text-sm text-muted-foreground mb-4">
            Describe what to build. All nine members review it, then the Chair delivers a Decision Package.
          </p>
          <div className="flex flex-col sm:flex-row gap-2">
            <textarea
              value={requestText}
              onChange={(e) => setRequestText(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && submitReview()}
              placeholder="e.g. Build an invoicing system for small businesses..."
              rows={2}
              className="flex-1 rounded-lg border border-border bg-background text-foreground placeholder:text-muted-foreground px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
            />
            <button
              onClick={() => submitReview()}
              disabled={submitting || !requestText.trim()}
              className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50 self-end"
            >
              {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : "Run Review"}
            </button>
          </div>
          {submitError && (
            <div className="mt-3 p-3 bg-red-500/10 border border-red-500/30 rounded-lg flex items-center justify-between gap-2">
              <p className="text-sm text-red-400 font-medium">{submitError}</p>
              <button
                onClick={() => submitReview()}
                className="rounded-lg bg-amber-600 px-3 py-1 text-xs font-semibold text-white hover:bg-amber-700 shadow-sm shrink-0"
              >
                🔄 Try Again
              </button>
            </div>
          )}
          {submitting && (
            <p className="mt-3 text-sm text-muted-foreground flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" /> Nine executives are deliberating (can take a minute or two)...
            </p>
          )}
        </div>

        {/* Board roster */}
        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
            <Users className="h-5 w-5 text-primary" /> Board Members
          </h2>
          <p className="text-sm text-muted-foreground mb-4">The nine executives who review every request.</p>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {members.map((member) => (
              <div key={member.id} className="rounded-lg border border-border/50 bg-background/50 p-4">
                <div className="flex items-center gap-3">
                  <div className="rounded-lg bg-primary/10 p-2">
                    <Crown className="h-4 w-4 text-primary" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold truncate">{member.title}</p>
                    {member.score_category && (
                      <p className="text-xs text-muted-foreground">
                        Scores: {member.score_category.replace(/_/g, " ")}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Reviews */}
        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
            <ClipboardList className="h-5 w-5 text-primary" /> Review History
          </h2>
          <p className="text-sm text-muted-foreground mb-4">Every product request the board has ruled on.</p>
          {reviews.length === 0 ? (
            <p className="text-sm text-muted-foreground">No reviews yet. Submit your first request above.</p>
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
                        {new Date(review.created_at).toLocaleString()} · {review.scored_members}/{review.total_members} members
                      </p>
                    </div>
                    {review.total_score != null && (
                      <span className="text-lg font-bold text-muted-foreground">{review.total_score}%</span>
                    )}
                    <div className="flex items-center gap-2">
                      <span
                        className={`rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${verdictStyle[review.final_verdict] || "border-border bg-secondary/60 text-muted-foreground"}`}
                      >
                        {review.final_verdict}
                      </span>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation()
                          submitReview(review.request)
                        }}
                        className="rounded-lg bg-amber-500/20 text-amber-300 border border-amber-500/30 px-2.5 py-1 text-xs font-semibold hover:bg-amber-500/30 transition-colors flex items-center gap-1"
                        title="Re-run review with current proposal text"
                      >
                        <RefreshCw className="h-3 w-3" /> Quick Try Again
                      </button>
                    </div>
                  </button>

                  {expandedId === review.id && (
                    <div className="border-t border-border/50 px-4 py-4">
                      {detailLoading ? (
                        <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
                          <Loader2 className="h-4 w-4 animate-spin" /> Loading decision...
                        </div>
                      ) : detail ? (
                        <div className="space-y-4">
                          {detail.error && (
                            <p className="text-sm text-red-500">Error: {detail.error}</p>
                          )}

                          {/* Scorecard */}
                          <div>
                            <h3 className="text-sm font-semibold mb-2">Weighted Scorecard</h3>
                            <div className="space-y-1.5">
                              {detail.scorecard.map((entry) => (
                                <div key={entry.category} className="flex items-center gap-3">
                                  <div className="w-40 shrink-0 text-sm">{entry.label}</div>
                                  <div className="flex-1 h-2 rounded-full bg-secondary overflow-hidden">
                                    <div
                                      className={`h-full rounded-full ${entry.score != null && entry.score >= (stats?.approve_threshold || 75) ? "bg-green-500" : entry.score != null ? "bg-amber-500" : "bg-zinc-600"}`}
                                      style={{ width: `${entry.scored ? entry.score || 0 : 0}%` }}
                                    />
                                  </div>
                                  <div className="w-16 shrink-0 text-right text-sm text-muted-foreground">
                                    {entry.score != null ? `${entry.score}` : "—"}
                                  </div>
                                  <div className="w-16 shrink-0 text-right text-xs text-muted-foreground">
                                    {entry.weighted != null ? `× ${entry.weight}` : ""}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>

                          {/* Member verdicts */}
                          {detail.verdicts.length > 0 && (
                            <div>
                              <h3 className="text-sm font-semibold mb-2">Member Verdicts</h3>
                              <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
                                {detail.verdicts.map((v) => (
                                  <div key={v.member_id} className="rounded-lg border border-border/50 bg-background/60 p-3">
                                    <div className="flex items-center justify-between gap-2">
                                      <p className="text-xs font-semibold truncate">{v.member_name}</p>
                                      <span className="text-xs font-bold text-muted-foreground shrink-0">
                                        {v.status === "completed" ? `${v.score}` : "—"}
                                      </span>
                                    </div>
                                    <p className="text-xs text-muted-foreground capitalize mt-0.5">{v.verdict}</p>
                                    {v.status === "failed" && v.error && (
                                      <p className="text-xs text-red-500 mt-1 truncate" title={v.error}>{v.error}</p>
                                    )}
                                    {v.status === "completed" && v.recommendations.length > 0 && (
                                      <ul className="mt-1.5 space-y-0.5">
                                        {v.recommendations.slice(0, 3).map((rec, i) => (
                                          <li key={i} className="text-xs text-muted-foreground">- {rec}</li>
                                        ))}
                                      </ul>
                                    )}
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Decision package */}
                          {detail.decision_markdown && (
                            <div>
                              <h3 className="text-sm font-semibold mb-2">Decision Package</h3>
                              <pre className="rounded-lg border border-border/50 bg-background/60 p-4 text-xs whitespace-pre-wrap font-mono text-muted-foreground max-h-80 overflow-y-auto">
                                {detail.decision_markdown}
                              </pre>
                            </div>
                          )}

                          {/* Actions */}
                          <div className="flex flex-wrap gap-2 pt-1">
                            <button
                              onClick={() => createProject(review.id)}
                              disabled={creatingProject === review.id}
                              className="rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50 flex items-center gap-1"
                            >
                              {creatingProject === review.id ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              ) : (
                                <ExternalLink className="h-3.5 w-3.5 inline" />
                              )}
                              {creatingProject === review.id
                                ? "Creating..."
                                : review.final_verdict === "approved"
                                ? "Create Project"
                                : "🔨 Create Project (Override)"}
                            </button>

                            <button
                              type="button"
                              onClick={() => submitReview(review.request)}
                              disabled={submitting}
                              className="rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-700 disabled:opacity-50 transition-colors flex items-center gap-1 shadow-sm"
                            >
                              <RefreshCw className={`h-3.5 w-3.5 ${submitting ? "animate-spin" : ""}`} />
                              ⚡ Re-Run Review (Try Again)
                            </button>

                            <button
                              type="button"
                              onClick={() => {
                                setRequestText(review.request)
                                window.scrollTo({ top: 0, behavior: "smooth" })
                              }}
                              className="rounded-lg bg-secondary border border-border px-3 py-1.5 text-xs font-medium hover:bg-secondary/80 transition-colors flex items-center gap-1"
                            >
                              ✏️ Edit & Re-submit
                            </button>

                            <a
                              href={`${API}/api/board/reviews/${review.id}/export`}
                              target="_blank"
                              rel="noreferrer"
                              className="rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-secondary flex items-center gap-1"
                            >
                              <FileDown className="h-3.5 w-3.5" /> Export
                            </a>
                          </div>
                        </div>
                      ) : (
                        <p className="text-sm text-red-500">Failed to load review detail.</p>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <UserCheck className="h-4 w-4" />
          Layer 2 produces decisions only — the Hermes engineering agents handle implementation.
        </div>
      </div>
    </DashboardLayout>
  )
}
