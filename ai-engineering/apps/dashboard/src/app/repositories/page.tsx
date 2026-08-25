"use client"

import { useEffect, useState } from "react"
import { DashboardLayout } from "@/components/layout/dashboard-layout"

interface Repo {
  id: number
  name: string
  full_name: string
  description: string
  html_url: string
  language: string
  stargazers_count: number
  forks_count: number
  open_issues_count: number
  updated_at: string
  private: boolean
  default_branch: string
}

const langColors: Record<string, string> = {
  Python: "bg-blue-500",
  TypeScript: "bg-blue-400",
  JavaScript: "bg-yellow-500",
  Dart: "bg-cyan-500",
  Go: "bg-cyan-400",
  Rust: "bg-orange-500",
  HTML: "bg-red-500",
  CSS: "bg-purple-500",
}

export default function RepositoriesPage() {
  const [repos, setRepos] = useState<Repo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [search, setSearch] = useState("")
  const [showCreate, setShowCreate] = useState(false)
  const [newRepo, setNewRepo] = useState({ name: "", description: "", private: true })
  const [creating, setCreating] = useState(false)

  const GITHUB_TOKEN = process.env.NEXT_PUBLIC_GITHUB_TOKEN || ""

  const fetchRepos = () => {
    setLoading(true)
    setError("")
    fetch("https://api.github.com/user/repos?per_page=50&sort=updated", {
      headers: {
        Authorization: `token ${GITHUB_TOKEN}`,
        Accept: "application/vnd.github.v3+json",
      },
    })
      .then((res) => {
        if (!res.ok) throw new Error(`GitHub API: ${res.status}`)
        return res.json()
      })
      .then((data) => {
        setRepos(Array.isArray(data) ? data : [])
        setLoading(false)
      })
      .catch((e) => {
        setError(e.message)
        setLoading(false)
      })
  }

  useEffect(() => { fetchRepos() }, [])

  const createRepo = async () => {
    if (!newRepo.name) return
    setCreating(true)
    try {
      const res = await fetch("https://api.github.com/user/repos", {
        method: "POST",
        headers: {
          Authorization: `token ${GITHUB_TOKEN}`,
          "Content-Type": "application/json",
          Accept: "application/vnd.github.v3+json",
        },
        body: JSON.stringify({
          name: newRepo.name,
          description: newRepo.description,
          private: newRepo.private,
          auto_init: true,
        }),
      })
      if (res.ok) {
        setNewRepo({ name: "", description: "", private: true })
        setShowCreate(false)
        fetchRepos()
      } else {
        const err = await res.json()
        setError(err.message || "Failed to create repo")
      }
    } catch (e: any) {
      setError(e.message)
    }
    setCreating(false)
  }

  const filtered = repos.filter(
    (r) =>
      r.name.toLowerCase().includes(search.toLowerCase()) ||
      (r.description && r.description.toLowerCase().includes(search.toLowerCase()))
  )

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Repositories</h1>
            <p className="text-muted-foreground">GitHub repositories for Britsync</p>
          </div>
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            + New Repository
          </button>
        </div>

        {error && (
          <div className="rounded-lg bg-red-500/10 border border-red-500/20 px-4 py-3 text-sm text-red-400">
            {error}
          </div>
        )}

        {showCreate && (
          <div className="rounded-lg border border-border bg-card p-6 space-y-4">
            <h3 className="font-semibold text-lg">Create Repository on GitHub</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Repository Name *</label>
                <input
                  placeholder="e.g. my-new-app"
                  value={newRepo.name}
                  onChange={(e) => setNewRepo({ ...newRepo, name: e.target.value })}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                />
              </div>
              <label className="flex items-center gap-2 text-sm self-end pb-1">
                <input
                  type="checkbox"
                  checked={newRepo.private}
                  onChange={(e) => setNewRepo({ ...newRepo, private: e.target.checked })}
                  className="rounded"
                />
                Private repository
              </label>
              <div className="col-span-2">
                <label className="text-xs text-muted-foreground mb-1 block">Description</label>
                <textarea
                  placeholder="What is this repo for?"
                  value={newRepo.description}
                  onChange={(e) => setNewRepo({ ...newRepo, description: e.target.value })}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm h-16"
                />
              </div>
            </div>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowCreate(false)} className="rounded-lg px-4 py-2 text-sm hover:bg-secondary">Cancel</button>
              <button
                onClick={createRepo}
                disabled={creating || !newRepo.name}
                className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
              >
                {creating ? "Creating..." : "Create Repository"}
              </button>
            </div>
          </div>
        )}

        <div className="relative">
          <input
            placeholder="Search repositories..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm"
          />
        </div>

        {loading ? (
          <div className="text-center py-12 text-muted-foreground">Loading repositories...</div>
        ) : error ? (
          <div className="text-center py-16 border border-dashed border-border rounded-lg">
            <p className="text-lg font-medium mb-2">Could not load repositories</p>
            <p className="text-sm text-muted-foreground mb-4">GitHub API returned an error. Check network or add a token.</p>
            <button
              onClick={fetchRepos}
              className="rounded-lg bg-primary px-6 py-2 text-sm font-medium text-primary-foreground"
            >
              Retry
            </button>
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-16 border border-dashed border-border rounded-lg">
            <p className="text-lg font-medium mb-2">No repositories found</p>
            <p className="text-sm text-muted-foreground mb-4">
              {search ? "Try a different search" : "Create your first repository to get started"}
            </p>
            {!search && (
              <button
                onClick={() => setShowCreate(true)}
                className="rounded-lg bg-primary px-6 py-2 text-sm font-medium text-primary-foreground"
              >
                + Create Repository
              </button>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            {filtered.map((repo) => (
              <a
                key={repo.id}
                href={repo.html_url}
                target="_blank"
                rel="noopener noreferrer"
                className="block rounded-lg border border-border bg-card p-5 hover:shadow-md transition-all"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="font-semibold text-primary">{repo.name}</h3>
                      {repo.private && (
                        <span className="text-xs bg-yellow-500/10 text-yellow-500 px-2 py-0.5 rounded">Private</span>
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground mt-1">
                      {repo.description || "No description"}
                    </p>
                    <div className="flex items-center gap-4 mt-3 text-xs text-muted-foreground">
                      {repo.language && (
                        <span className="flex items-center gap-1">
                          <span className={`h-2 w-2 rounded-full ${langColors[repo.language] || "bg-gray-500"}`} />
                          {repo.language}
                        </span>
                      )}
                      <span>{repo.stargazers_count} stars</span>
                      <span>{repo.forks_count} forks</span>
                      <span>{repo.open_issues_count} issues</span>
                      <span>Updated {new Date(repo.updated_at).toLocaleDateString()}</span>
                    </div>
                  </div>
                </div>
              </a>
            ))}
          </div>
        )}
      </div>
    </DashboardLayout>
  )
}
