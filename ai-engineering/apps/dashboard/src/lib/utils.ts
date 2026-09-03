import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001"

export async function apiFetch<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    ...options,
  })

  if (!res.ok) {
    throw new Error(`API error: ${res.status}`)
  }

  return res.json()
}

export async function apiFetchWithRetry<T>(
  endpoint: string,
  options?: RequestInit,
  retries = 2,
  delayMs = 1500,
): Promise<T> {
  let lastError: any
  for (let i = 0; i <= retries; i++) {
    try {
      const res = await fetch(`${API_BASE}${endpoint}`, {
        headers: {
          "Content-Type": "application/json",
          ...options?.headers,
        },
        ...options,
      })
      if (!res.ok) throw new Error(`API error: ${res.status}`)
      return res.json()
    } catch (e: any) {
      lastError = e
      if (i < retries) await new Promise((r) => setTimeout(r, delayMs))
    }
  }
  throw lastError
}
