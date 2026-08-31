"use client"
import { createContext, useContext, useEffect, useState, ReactNode } from "react"

interface AuthUser {
  id: string
  name: string
  email: string
  company_name: string
  is_admin: boolean
  status: string
}

interface AuthContextType {
  user: AuthUser | null
  token: string | null
  loading: boolean
  login: (email: string, password: string) => Promise<{ error?: string }>
  signup: (data: { name: string; email: string; password: string; company_name?: string; company_role?: string; company_size?: string; company_website?: string }) => Promise<{ error?: string; pending?: boolean }>
  logout: () => void
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextType>({
  user: null, token: null, loading: true,
  login: async () => ({}), signup: async () => ({}), logout: () => {},
  refreshUser: async () => {},
})

export function useAuth() { return useContext(AuthContext) }

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchUser = async (tok: string) => {
    try {
      const res = await fetch(`http://127.0.0.1:8001/api/auth/me?token=${encodeURIComponent(tok)}`)
      const data = await res.json()
      if (data.user) {
        setUser(data.user)
        return
      }
    } catch {}
    setUser(null)
    setToken(null)
    localStorage.removeItem("aied-token")
  }

  useEffect(() => {
    const saved = localStorage.getItem("aied-token")
    if (saved) {
      setToken(saved)
      fetchUser(saved).finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [])

  const login = async (email: string, password: string) => {
    for (let attempt = 1; attempt <= 2; attempt++) {
      try {
        const res = await fetch("http://127.0.0.1:8001/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password }),
        })
        const data = await res.json()
        if (data.error) return { error: data.error }
        setToken(data.token)
        setUser(data.user)
        localStorage.setItem("aied-token", data.token)
        ;(window as any).aied?.notifyLogin?.(data.token)
        return {}
      } catch (e) {
        if (attempt > 1) {
          console.error("AIED login failed:", e)
          return { error: "Failed to connect to server. Please try again." }
        }
        await new Promise((r) => setTimeout(r, 1200))
      }
    }
    return { error: "Failed to connect to server. Please try again." }
  }

  const signup = async (signupData: { name: string; email: string; password: string; company_name?: string; company_role?: string; company_size?: string; company_website?: string }) => {
    try {
      const res = await fetch("http://127.0.0.1:8001/api/auth/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(signupData),
      })
      const data = await res.json()
      if (data.error) return { error: data.error }
      if (data.user?.status === "pending") {
        return { pending: true }
      }
      if (data.token) {
        setToken(data.token)
        setUser(data.user)
        localStorage.setItem("aied-token", data.token)
        ;(window as any).aied?.notifyLogin?.(data.token)
      }
      return {}
    } catch {
      return { error: "Failed to connect to server" }
    }
  }

  const logout = () => {
    setUser(null)
    setToken(null)
    localStorage.removeItem("aied-token")
    ;(window as any).aied?.notifyLogout?.()
  }

  const refreshUser = async () => {
    if (token) await fetchUser(token)
  }

  return (
    <AuthContext.Provider value={{ user, token, loading, login, signup, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  )
}
