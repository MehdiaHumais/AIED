"use client"

import { ReactNode, useState, useEffect } from "react"
import { Sidebar } from "./sidebar"
import { Header } from "./header"

interface DashboardLayoutProps {
  children: ReactNode
}

export function DashboardLayout({ children }: DashboardLayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const closeSidebar = () => setSidebarOpen(false)

  useEffect(() => {
    if (!sidebarOpen) return
    document.body.style.overflow = "hidden"
    return () => { document.body.style.overflow = "" }
  }, [sidebarOpen])

  return (
    <div className="relative flex h-full overflow-hidden overscroll-none">
      <Sidebar mobileOpen={sidebarOpen} onClose={closeSidebar} />
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        <Header onMenuClick={() => setSidebarOpen(true)} />
        <main className="flex-1 overflow-y-auto overflow-x-hidden overscroll-contain p-4 lg:p-6">
          {children}
        </main>
      </div>
    </div>
  )
}
