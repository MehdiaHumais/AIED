"use client"

import Link from "next/link"
import { useAuth } from "@/components/auth-provider"
import { useRouter } from "next/navigation"
import { useEffect } from "react"
import { Sun, Moon, Bot, Layers, Rocket, Shield, Brain, Zap, Globe, ArrowRight } from "lucide-react"
import { useTheme } from "@/components/theme-provider"

const features = [
  {
    icon: Brain,
    title: "10-Layer AI Architecture",
    desc: "From knowledge base to governance, every layer of your product is managed by specialized AI agents working together.",
    color: "text-purple-400",
    bg: "bg-purple-500/10",
  },
  {
    icon: Bot,
    title: "31 Autonomous Agents",
    desc: "Executive board, product researchers, UX designers, growth marketers, security auditors, and more — all AI-powered.",
    color: "text-blue-400",
    bg: "bg-blue-500/10",
  },
  {
    icon: Layers,
    title: "Workflow Orchestration",
    desc: "CEO chat sends requests through the full layer pipeline. Each layer reviews, refines, and passes work forward.",
    color: "text-teal-400",
    bg: "bg-teal-500/10",
  },
  {
    icon: Rocket,
    title: "VPS Deployment Agent",
    desc: "Connect your VPS, deploy from GitHub, auto-configure nginx, SSL, systemd. Full self-healing with 14-step workflow.",
    color: "text-orange-400",
    bg: "bg-orange-500/10",
  },
  {
    icon: Shield,
    title: "Quality & Security",
    desc: "Automated testing, code review, vulnerability scanning, and release management at every stage.",
    color: "text-green-400",
    bg: "bg-green-500/10",
  },
  {
    icon: Zap,
    title: "Intelligent Learning",
    desc: "Agents learn from past decisions, track metrics, and continuously improve the development process.",
    color: "text-yellow-400",
    bg: "bg-yellow-500/10",
  },
]

const stats = [
  { value: "31", label: "AI Agents" },
  { value: "10", label: "Architecture Layers" },
  { value: "14", label: "Deployment Steps" },
  { value: "24/7", label: "Autonomous Operation" },
]

export default function LandingPage() {
  const { user, loading } = useAuth()
  const { theme, toggle } = useTheme()
  const router = useRouter()

  useEffect(() => {
    if (!loading && user) {
      router.replace("/dashboard")
    }
  }, [user, loading, router])

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    )
  }

  // If logged in, we redirect to the dashboard, but keep the nav showing
  // the user profile + Dashboard button just in case the redirect isn't instant.
  const loggedInUser = user ? user : null

  return (
    <div className="min-h-screen bg-background">
      {/* Nav */}
      <nav className="fixed top-0 left-0 right-0 z-50 border-b border-border bg-background/80 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-primary flex items-center justify-center">
              <Bot className="h-5 w-5 text-primary-foreground" />
            </div>
            <div>
              <h1 className="text-sm font-bold">AIED</h1>
              <p className="text-[10px] text-muted-foreground">Britsync AI Engineering Department</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button onClick={toggle} className="rounded-lg p-2 hover:bg-secondary transition-colors">
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
            {loggedInUser ? (
              <>
                <span className="flex items-center gap-2 rounded-lg border border-border bg-secondary/50 px-3 py-2 text-sm">
                  <span className="h-6 w-6 rounded-full bg-primary text-primary-foreground text-xs font-bold flex items-center justify-center">
                    {(loggedInUser.name || "U").charAt(0).toUpperCase()}
                  </span>
                  <span className="font-medium">{loggedInUser.name}</span>
                </span>
                <Link href="/dashboard" className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 transition-opacity">
                  Dashboard
                </Link>
              </>
            ) : (
              <>
                <Link href="/login" className="rounded-lg px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">
                  Sign In
                </Link>
                <Link href="/signup" className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 transition-opacity">
                  Get Started
                </Link>
              </>
            )}
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="pt-32 pb-20 px-6">
        <div className="max-w-4xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 rounded-full border border-border bg-secondary/50 px-4 py-1.5 text-xs font-medium text-muted-foreground mb-6">
            <Globe className="h-3 w-3" />
            Autonomous AI Software Engineering Platform
          </div>
          <h1 className="text-5xl md:text-6xl font-bold tracking-tight mb-6">
            Your AI-Powered
            <br />
            <span className="text-primary">Engineering Department</span>
          </h1>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto mb-10">
            AIED is a 10-layer autonomous multi-agent system that manages the entire software lifecycle — from product research and UX design to deployment and governance. Talk to the CEO agent, and the whole team gets to work.
          </p>
          <div className="flex items-center justify-center gap-4">
            <Link href="/signup" className="inline-flex items-center gap-2 rounded-lg bg-primary px-6 py-3 text-sm font-medium text-primary-foreground hover:opacity-90 transition-opacity">
              Start Building <ArrowRight className="h-4 w-4" />
            </Link>
            <a href="https://github.com/BritsyncAI" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 rounded-lg border border-border px-6 py-3 text-sm font-medium text-muted-foreground hover:bg-secondary transition-colors">
              View on GitHub
            </a>
          </div>
        </div>
      </section>

      {/* Stats */}
      <section className="py-12 border-y border-border bg-secondary/20">
        <div className="max-w-5xl mx-auto px-6 grid grid-cols-2 md:grid-cols-4 gap-8">
          {stats.map((stat) => (
            <div key={stat.label} className="text-center">
              <p className="text-3xl font-bold">{stat.value}</p>
              <p className="text-sm text-muted-foreground mt-1">{stat.label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Features */}
      <section className="py-20 px-6">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-3xl font-bold text-center mb-4">Everything Your Team Needs</h2>
          <p className="text-center text-muted-foreground mb-12 max-w-xl mx-auto">
            Each layer of the architecture handles a specific aspect of product development, all orchestrated by AI agents.
          </p>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {features.map((f) => (
              <div key={f.title} className="rounded-xl border border-border bg-card p-6 hover:shadow-lg transition-shadow">
                <div className={`h-10 w-10 rounded-lg ${f.bg} flex items-center justify-center mb-4`}>
                  <f.icon className={`h-5 w-5 ${f.color}`} />
                </div>
                <h3 className="font-semibold mb-2">{f.title}</h3>
                <p className="text-sm text-muted-foreground">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Architecture */}
      <section className="py-20 px-6 bg-secondary/20">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-3xl font-bold text-center mb-12">10-Layer Architecture</h2>
          <div className="space-y-3">
            {[
              { layer: "L0", name: "Company Information", desc: "Your business context, goals, and constraints" },
              { layer: "L1", name: "Foundation Knowledge", desc: "9 product repositories, industry knowledge, best practices" },
              { layer: "L2", name: "Executive Product Board", desc: "Strategic decisions, prioritization, roadmap" },
              { layer: "L3", name: "Product Research & Discovery", desc: "Market analysis, user research, competitive intelligence" },
              { layer: "L4", name: "UX & Human Experience", desc: "User journeys, accessibility, interaction design" },
              { layer: "L5", name: "Visual Design & Systems", desc: "Design systems, component libraries, branding" },
              { layer: "L6", name: "Growth & Conversion", desc: "SEO, analytics, A/B testing, customer success" },
              { layer: "L7", name: "Quality & Release", desc: "Testing, security audits, CI/CD, release management" },
              { layer: "L8", name: "Intelligence & Learning", desc: "Metrics tracking, pattern recognition, continuous improvement" },
              { layer: "L9", name: "AI Governance", desc: "Compliance, ethics, orchestration across all layers" },
            ].map((l) => (
              <div key={l.layer} className="flex items-center gap-4 rounded-lg border border-border bg-card p-4">
                <span className="text-xs font-bold text-primary bg-primary/10 rounded px-2 py-1 shrink-0">{l.layer}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium">{l.name}</p>
                  <p className="text-xs text-muted-foreground">{l.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20 px-6">
        <div className="max-w-2xl mx-auto text-center">
          <h2 className="text-3xl font-bold mb-4">Ready to Build with AI?</h2>
          <p className="text-muted-foreground mb-8">
            Sign up and get access to your own AI engineering department. Admin approval required for new accounts.
          </p>
          <Link href="/signup" className="inline-flex items-center gap-2 rounded-lg bg-primary px-8 py-3 text-sm font-medium text-primary-foreground hover:opacity-90 transition-opacity">
            Create Account <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border py-8 px-6">
        <div className="max-w-7xl mx-auto flex items-center justify-between text-xs text-muted-foreground">
          <p>Britsync AI Engineering Department</p>
          <p>Powered by AIED v0.1.0</p>
        </div>
      </footer>
    </div>
  )
}
