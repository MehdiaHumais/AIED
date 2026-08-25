"use client"

import { DashboardLayout } from "@/components/layout/dashboard-layout"

export default function SecurityPage() {
  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Security</h1>
          <p className="text-muted-foreground">Security audits and vulnerability reports</p>
        </div>
        <div className="text-center py-12 border border-dashed border-border rounded-lg">
          <p className="text-muted-foreground">Security reports will appear after code analysis</p>
        </div>
      </div>
    </DashboardLayout>
  )
}
