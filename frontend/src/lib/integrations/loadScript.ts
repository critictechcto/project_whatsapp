const pending = new Map<string, Promise<void>>()

/** Loads a third-party script once. Later calls with the same `src` share the promise. */
export function loadScript(src: string, attributes: Record<string, string> = {}): Promise<void> {
  const existing = pending.get(src)
  if (existing) return existing

  const promise = new Promise<void>((resolve, reject) => {
    const script = document.createElement('script')
    script.src = src
    script.async = true
    for (const [key, value] of Object.entries(attributes)) script.setAttribute(key, value)
    script.onload = () => resolve()
    script.onerror = () => {
      pending.delete(src)
      script.remove()
      reject(new Error(`Failed to load ${src}`))
    }
    document.head.appendChild(script)
  })
  pending.set(src, promise)
  return promise
}
