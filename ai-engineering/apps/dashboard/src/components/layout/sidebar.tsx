"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { cn } from "@/lib/utils"
import { useAuth } from "@/components/auth-provider"
import {
  LayoutDashboard,
  FolderKanban,
  Bot,
  Rocket,
  Activity,
  Crown,
  Cpu,
  Code2,
  Palette,
  Shield,
  Settings,
  ChevronDown,
  ChevronRight,
  History,
  BookMarked,
  Gavel,
  Microscope,
  MousePointerClick,
  SwatchBook,
  TrendingUp,
  ShieldCheck,
  Brain,
  Workflow,
  Database,
  Route,
  FlaskConical,
  MessageSquare,
  Building2,
} from "lucide-react"
import { useState, useRef, useCallback, useEffect } from "react"

const departments = [
  {
    name: "Executive Command",
    icon: Crown,
    color: "text-yellow-400",
    items: [
      { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
      { name: "History", href: "/history", icon: History },
    ],
  },
  {
    name: "Layer 0 — Company Info",
    icon: Building2,
    color: "text-amber-400",
    items: [
      { name: "Company & Projects", href: "/company", icon: Building2 },
    ],
  },
  {
    name: "Layer 1 — CEO & Foundation",
    icon: BookMarked,
    color: "text-indigo-400",
    items: [
      { name: "CEO Chat & Knowledge", href: "/knowledge", icon: BookMarked },
    ],
  },
  {
    name: "Workflow Orchestration",
    icon: Route,
    color: "text-teal-400",
    items: [
      { name: "Layer Pipeline", href: "/workflow", icon: Route },
    ],
  },
  {
    name: "Executive Product Board (Layer 2)",
    icon: Gavel,
    color: "text-violet-400",
    items: [
      { name: "Product Board", href: "/board", icon: Gavel },
    ],
  },
  {
    name: "Product Research & Discovery (Layer 3)",
    icon: Microscope,
    color: "text-cyan-400",
    items: [
      { name: "Research Division", href: "/research", icon: Microscope },
    ],
  },
  {
    name: "UX & Human Experience (Layer 4)",
    icon: MousePointerClick,
    color: "text-pink-400",
    items: [
      { name: "UX Division", href: "/ux", icon: MousePointerClick },
    ],
  },
  {
    name: "Visual Design & Design System (Layer 5)",
    icon: SwatchBook,
    color: "text-orange-400",
    items: [
      { name: "Design Division", href: "/design", icon: SwatchBook },
    ],
  },
  {
    name: "Growth & Conversion (Layer 6)",
    icon: TrendingUp,
    color: "text-emerald-400",
    items: [
      { name: "Growth Division", href: "/growth", icon: TrendingUp },
    ],
  },
  {
    name: "Quality, Security & Release (Layer 7)",
    icon: ShieldCheck,
    color: "text-sky-400",
    items: [
      { name: "Release Division", href: "/quality", icon: ShieldCheck },
    ],
  },
  {
    name: "Intelligence & Learning (Layer 8)",
    icon: Brain,
    color: "text-fuchsia-400",
    items: [
      { name: "Intelligence Division", href: "/intelligence", icon: Brain },
    ],
  },
  {
    name: "AI Governance & Orchestration (Layer 9)",
    icon: Workflow,
    color: "text-amber-400",
    items: [
      { name: "Governance Division", href: "/governance", icon: Workflow },
    ],
  },
  {
    name: "Knowledge & Digital Twin (Layer 10)",
    icon: Database,
    color: "text-cyan-400",
    items: [
      { name: "Digital Twin Platform", href: "/ekdt", icon: Database },
    ],
  },
  {
    name: "Engineering & Platform",
    icon: Code2,
    color: "text-blue-400",
    items: [
      { name: "Projects", href: "/projects", icon: FolderKanban },
      { name: "Tester", href: "/tester", icon: FlaskConical },
      { name: "Monitor", href: "/monitor", icon: Activity },
      { name: "Agents", href: "/agents", icon: Bot },
    ],
  },
  {
    name: "Quality & Security",
    icon: Shield,
    color: "text-green-400",
    items: [
      { name: "Store Deploy", href: "/deployments", icon: Rocket },
      { name: "VPS Deploy", href: "/deployments/vps", icon: Rocket },
    ],
  },
]

const bottomNav = [
  { name: "Admin", href: "/admin", icon: Shield },
  { name: "Settings", href: "/settings", icon: Settings },
]

export function Sidebar() {
  const pathname = usePathname()
  const { user } = useAuth()
  const navRef = useRef<HTMLElement>(null)
  const scrollKey = "aied-sidebar-scroll"

  const handleNavClick = useCallback(() => {
    if (navRef.current) {
      try { sessionStorage.setItem(scrollKey, String(navRef.current.scrollTop)) } catch {}
    }
  }, [])

  useEffect(() => {
    if (navRef.current) {
      const saved = sessionStorage.getItem(scrollKey)
      if (saved) navRef.current.scrollTop = Number(saved)
    }
  }, [])

  const [expanded, setExpanded] = useState<Record<string, boolean>>({
    "Executive Command": true,
    "Workflow Orchestration": true,
    "Foundation (Layer 1)": true,
    "Executive Product Board (Layer 2)": true,
    "Product Research & Discovery (Layer 3)": true,
    "UX & Human Experience (Layer 4)": true,
    "Visual Design & Design System (Layer 5)": true,
    "Growth & Conversion (Layer 6)": true,
    "Quality, Security & Release (Layer 7)": true,
    "Intelligence & Learning (Layer 8)": true,
    "AI Governance & Orchestration (Layer 9)": true,
    "Knowledge & Digital Twin (Layer 10)": true,
    "Engineering & Platform": true,
    "Quality & Security": true,
  })

  return (
    <aside className="w-64 border-r border-border bg-card flex flex-col h-full">
      <div className="flex h-16 items-center border-b border-border px-6 shrink-0">
        <div className="flex items-center gap-2">
          <div className="h-8 w-8 rounded-lg bg-primary flex items-center justify-center">
            <Bot className="h-5 w-5 text-primary-foreground" />
          </div>
          <div>
            <h1 className="text-sm font-bold">AIED</h1>
            <p className="text-xs text-muted-foreground">Britsync AI Company</p>
          </div>
        </div>
      </div>
      <nav
        ref={navRef}
        className="flex flex-col gap-1 p-4 flex-1 overflow-y-auto"
        onScroll={() => {
          if (navRef.current) {
            try { sessionStorage.setItem(scrollKey, String(navRef.current.scrollTop)) } catch {}
          }
        }}
      >
        {departments.map((dept) => {
          const isExpanded = expanded[dept.name] !== false
          return (
            <div key={dept.name} className="mb-2">
              <button
                onClick={() => setExpanded((prev) => ({ ...prev, [dept.name]: !isExpanded }))}
                className="flex w-full items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-bold uppercase tracking-wider text-muted-foreground hover:bg-secondary"
              >
                <dept.icon className={cn("h-3.5 w-3.5", dept.color)} />
                <span className="flex-1 text-left">{dept.name}</span>
                {isExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
              </button>
              {isExpanded && (
                <div className="mt-1 ml-2 space-y-0.5">
                  {dept.items.map((item) => {
                    const isActive = pathname === item.href
                    return (
                      <Link
                        key={item.name}
                        href={item.href}
                        className={cn(
                          "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                          isActive
                            ? "bg-primary/10 text-primary"
                            : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                        )}
                      >
                        <item.icon className="h-4 w-4" />
                        {item.name}
                      </Link>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
      </nav>
      <div className="border-t border-border p-4 shrink-0">
        {bottomNav.filter(item => !(item.name === "Admin" && !user?.is_admin)).map((item) => {
          const isActive = pathname === item.href
          return (
            <Link
              key={item.name}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-secondary hover:text-foreground"
              )}
            >
              <item.icon className="h-4 w-4" />
              {item.name}
            </Link>
          )
        })}
      </div>
    </aside>
  )
}
