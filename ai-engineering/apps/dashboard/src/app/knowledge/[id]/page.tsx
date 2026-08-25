"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { useParams, useRouter } from "next/navigation"
import { DashboardLayout } from "@/components/layout/dashboard-layout"
import {
  ArrowLeft,
  BookOpen,
  MousePointerClick,
  Building2,
  LayoutTemplate,
  Workflow,
  Brain,
  TrendingUp,
  Accessibility,
  Search,
  Plus,
  Trash2,
  Pencil,
  X,
  RotateCcw,
  Check,
} from "lucide-react"

const API = "http://127.0.0.1:8001"

interface Item {
  id: string
  title: string
  summary: string
  content: string
  rules: string[]
  tags: string[]
  metadata: Record<string, any>
  updated_at: string
}

interface Category {
  id: string
  name: string
  description: string
  items: Item[]
}

interface Repository {
  id: string
  name: string
  description: string
  icon: string
  accent: string
  categories: Category[]
}

const iconMap: Record<string, any> = {
  Palette: BookOpen,
  MousePointerClick,
  Building2,
  LayoutTemplate,
  Workflow,
  Brain,
  TrendingUp,
  Accessibility,
  Search,
}

export default function KnowledgeDetailPage() {
  const params = useParams()
  const router = useRouter()
  const repoId = String(params.id || "")

  const [repo, setRepo] = useState<Repository | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  const [addingItem, setAddingItem] = useState<{ categoryId: string; title: string; summary: string; content: string; rules: string } | null>(null)
  const [saving, setSaving] = useState(false)
  const [editingItem, setEditingItem] = useState<{ categoryId: string; item: Item; title: string; summary: string; content: string; rules: string } | null>(null)
  const [addingCategory, setAddingCategory] = useState<{ name: string; description: string } | null>(null)
  const [message, setMessage] = useState("")

  const fetchRepo = () => {
    setLoading(true)
    fetch(`${API}/api/kb/repositories/${repoId}`)
      .then((r) => r.json())
      .then((data) => {
        if (data.error) {
          setError(data.error)
          setRepo(null)
        } else {
          setRepo(data.repository)
          setError("")
        }
      })
      .catch(() => setError("API not reachable"))
      .finally(() => setLoading(false))
  }

  useEffect(() => { if (repoId) fetchRepo() }, [repoId])

  const flash = (msg: string) => {
    setMessage(msg)
    setTimeout(() => setMessage(""), 2500)
  }

  const addItem = async () => {
    if (!addingItem) return
    setSaving(true)
    try {
      const res = await fetch(`${API}/api/kb/repositories/${repoId}/categories/${addingItem.categoryId}/items`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: addingItem.title,
          summary: addingItem.summary,
          content: addingItem.content,
          rules: addingItem.rules.split("\n").map((r) => r.trim()).filter(Boolean),
        }),
      })
      const data = await res.json()
      if (data.error) throw new Error(data.error)
      flash("Item added")
      setAddingItem(null)
      fetchRepo()
    } catch (e: any) {
      flash("Error: " + e.message)
    } finally {
      setSaving(false)
    }
  }

  const updateItem = async () => {
    if (!editingItem) return
    setSaving(true)
    try {
      const res = await fetch(`${API}/api/kb/repositories/${repoId}/items/${editingItem.item.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: editingItem.title,
          summary: editingItem.summary,
          content: editingItem.content,
          rules: editingItem.rules.split("\n").map((r) => r.trim()).filter(Boolean),
        }),
      })
      const data = await res.json()
      if (data.error) throw new Error(data.error)
      flash("Item updated")
      setEditingItem(null)
      fetchRepo()
    } catch (e: any) {
      flash("Error: " + e.message)
    } finally {
      setSaving(false)
    }
  }

  const deleteItem = async (itemId: string) => {
    if (!confirm("Delete this standard?")) return
    try {
      const res = await fetch(`${API}/api/kb/repositories/${repoId}/items/${itemId}`, { method: "DELETE" })
      const data = await res.json()
      if (data.error) throw new Error(data.error)
      flash("Item deleted")
      fetchRepo()
    } catch (e: any) {
      flash("Error: " + e.message)
    }
  }

  const addCategory = async () => {
    if (!addingCategory) return
    setSaving(true)
    try {
      const res = await fetch(`${API}/api/kb/repositories/${repoId}/categories`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(addingCategory),
      })
      const data = await res.json()
      if (data.error) throw new Error(data.error)
      flash("Category added")
      setAddingCategory(null)
      fetchRepo()
    } catch (e: any) {
      flash("Error: " + e.message)
    } finally {
      setSaving(false)
    }
  }

  const resetRepo = async () => {
    if (!confirm("Reset this repository to its factory seed content? Your edits will be lost.")) return
    try {
      const res = await fetch(`${API}/api/kb/repositories/${repoId}/reset`, { method: "POST" })
      const data = await res.json()
      if (data.error) throw new Error(data.error)
      flash("Repository reset to seed")
      fetchRepo()
    } catch (e: any) {
      flash("Error: " + e.message)
    }
  }

  const Icon = repo ? (iconMap[repo.icon] || BookOpen) : BookOpen

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <p className="text-muted-foreground">Loading repository...</p>
        </div>
      </DashboardLayout>
    )
  }

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <Link href="/knowledge" className="rounded-lg border border-border p-2 hover:bg-secondary">
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center">
            <Icon className="h-5 w-5 text-primary" />
          </div>
          <div className="flex-1">
            <h1 className="text-2xl font-bold tracking-tight">{repo?.name}</h1>
            <p className="text-sm text-muted-foreground">{repo?.description}</p>
          </div>
          <button
            onClick={resetRepo}
            className="rounded-lg border border-border px-3 py-2 text-xs font-semibold text-muted-foreground hover:bg-secondary"
          >
            <RotateCcw className="h-3.5 w-3.5 inline mr-1" /> Reset to seed
          </button>
        </div>

        {error && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-400">
            {error}
            <Link href="/knowledge" className="ml-2 underline">Back to knowledge base</Link>
          </div>
        )}

        {message && (
          <div className="rounded-lg border border-green-500/30 bg-green-500/10 p-3 text-sm text-green-400 flex items-center gap-2">
            <Check className="h-4 w-4" /> {message}
          </div>
        )}

        {repo && repo.categories.map((cat) => (
          <div key={cat.id} className="rounded-lg border border-border bg-card">
            <div className="flex items-center justify-between border-b border-border p-4">
              <div>
                <h2 className="text-base font-semibold">{cat.name}</h2>
                {cat.description && <p className="text-xs text-muted-foreground mt-0.5">{cat.description}</p>}
              </div>
              <span className="text-xs text-muted-foreground bg-secondary/60 rounded-full px-2.5 py-1">
                {cat.items.length} items
              </span>
            </div>
            <div className="divide-y divide-border/50">
              {cat.items.length === 0 && (
                <p className="p-4 text-sm text-muted-foreground">No items yet. Add the first standard.</p>
              )}
              {cat.items.map((item) => (
                <div key={item.id} className="p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold">{item.title}</p>
                      {item.summary && <p className="mt-0.5 text-xs text-muted-foreground">{item.summary}</p>}
                      {item.rules.length > 0 && (
                        <ul className="mt-2 space-y-1">
                          {item.rules.map((rule, i) => (
                            <li key={i} className="text-xs text-muted-foreground pl-3 border-l-2 border-primary/40">- {rule}</li>
                          ))}
                        </ul>
                      )}
                      {item.content && (
                        <details className="mt-2">
                          <summary className="text-xs text-primary cursor-pointer select-none">Details</summary>
                          <p className="mt-1 text-xs text-muted-foreground whitespace-pre-wrap">{item.content}</p>
                        </details>
                      )}
                      {item.tags.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {item.tags.map((tag, i) => (
                            <span key={i} className="text-[10px] text-muted-foreground bg-secondary/60 rounded-full px-2 py-0.5">
                              #{tag}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="flex gap-1 shrink-0">
                      <button
                        onClick={() => setEditingItem({ categoryId: cat.id, item, title: item.title, summary: item.summary, content: item.content, rules: item.rules.join("\n") })}
                        className="rounded-md border border-border p-1.5 hover:bg-secondary"
                        title="Edit"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={() => deleteItem(item.id)}
                        className="rounded-md border border-border p-1.5 hover:bg-red-500/10 hover:text-red-400"
                        title="Delete"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <div className="border-t border-border p-3">
              <button
                onClick={() => setAddingItem({ categoryId: cat.id, title: "", summary: "", content: "", rules: "" })}
                className="text-xs font-semibold text-primary flex items-center gap-1.5 hover:opacity-80"
              >
                <Plus className="h-3.5 w-3.5" /> Add standard
              </button>
            </div>
          </div>
        ))}

        {/* Add item form */}
        {addingItem && (
          <div className="rounded-lg border border-primary/40 bg-card p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-bold">Add Standard</h3>
              <button onClick={() => setAddingItem(null)} className="rounded-md p-1 hover:bg-secondary">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="space-y-3">
              <input
                value={addingItem.title}
                onChange={(e) => setAddingItem({ ...addingItem, title: e.target.value })}
                placeholder="Title (e.g. Button height)"
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
              />
              <input
                value={addingItem.summary}
                onChange={(e) => setAddingItem({ ...addingItem, summary: e.target.value })}
                placeholder="One-line summary (shown to agents)"
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
              />
              <textarea
                value={addingItem.content}
                onChange={(e) => setAddingItem({ ...addingItem, content: e.target.value })}
                placeholder="Full details / guidance"
                rows={3}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
              />
              <textarea
                value={addingItem.rules}
                onChange={(e) => setAddingItem({ ...addingItem, rules: e.target.value })}
                placeholder="Checkable rules - one per line"
                rows={3}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
              />
              <div className="flex justify-end gap-2">
                <button onClick={() => setAddingItem(null)} className="rounded-lg border border-border px-4 py-2 text-sm hover:bg-secondary">Cancel</button>
                <button
                  onClick={addItem}
                  disabled={saving || !addingItem.title.trim()}
                  className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
                >
                  {saving ? "Saving..." : "Add"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Edit item form */}
        {editingItem && (
          <div className="rounded-lg border border-primary/40 bg-card p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-bold">Edit Standard</h3>
              <button onClick={() => setEditingItem(null)} className="rounded-md p-1 hover:bg-secondary">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="space-y-3">
              <input
                value={editingItem.title}
                onChange={(e) => setEditingItem({ ...editingItem, title: e.target.value })}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
              />
              <input
                value={editingItem.summary}
                onChange={(e) => setEditingItem({ ...editingItem, summary: e.target.value })}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
              />
              <textarea
                value={editingItem.content}
                onChange={(e) => setEditingItem({ ...editingItem, content: e.target.value })}
                rows={3}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
              />
              <textarea
                value={editingItem.rules}
                onChange={(e) => setEditingItem({ ...editingItem, rules: e.target.value })}
                rows={3}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
              />
              <div className="flex justify-end gap-2">
                <button onClick={() => setEditingItem(null)} className="rounded-lg border border-border px-4 py-2 text-sm hover:bg-secondary">Cancel</button>
                <button
                  onClick={updateItem}
                  disabled={saving || !editingItem.title.trim()}
                  className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
                >
                  {saving ? "Saving..." : "Save"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Add category */}
        <button
          onClick={() => setAddingCategory({ name: "", description: "" })}
          className="w-full rounded-lg border border-dashed border-border p-4 text-sm font-semibold text-muted-foreground flex items-center justify-center gap-2 hover:bg-secondary"
        >
          <Plus className="h-4 w-4" /> Add Category
        </button>
        {addingCategory && (
          <div className="rounded-lg border border-primary/40 bg-card p-5">
            <div className="space-y-3">
              <input
                value={addingCategory.name}
                onChange={(e) => setAddingCategory({ ...addingCategory, name: e.target.value })}
                placeholder="Category name (e.g. Checkout)"
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
              />
              <input
                value={addingCategory.description}
                onChange={(e) => setAddingCategory({ ...addingCategory, description: e.target.value })}
                placeholder="Category description"
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
              />
              <div className="flex justify-end gap-2">
                <button onClick={() => setAddingCategory(null)} className="rounded-lg border border-border px-4 py-2 text-sm hover:bg-secondary">Cancel</button>
                <button
                  onClick={addCategory}
                  disabled={saving || !addingCategory.name.trim()}
                  className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
                >
                  {saving ? "Saving..." : "Add"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  )
}
