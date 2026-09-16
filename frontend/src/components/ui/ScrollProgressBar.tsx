import './ScrollProgressBar.css'

/**
 * A thin accent line along the top of the viewport that fills as the page scrolls.
 *
 * Pure CSS (`animation-timeline: scroll()`), so it costs no JavaScript while scrolling. Browsers without
 * scroll-driven animations and reduced-motion users get nothing visible. Mount it once, e.g. at the top
 * of the landing page; it sits above the sticky navbar (z-50).
 */
export function ScrollProgressBar() {
  return <div aria-hidden="true" className="scroll-progress" />
}
