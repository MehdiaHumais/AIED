# AIED Dashboard - Release Notes

## Version 1.1.0 - Responsive Dashboard (2026-10-09)

### What's New
- **Fully responsive dashboard UI** - the dashboard now adapts to phones, tablets, and desktops.
- **Mobile navigation** - sidebar collapses into a slide-in drawer with a hamburger menu on small screens.
- **Responsive layout** - main content, headers, and task views resize cleanly down to phone widths; no horizontal scrolling.
- **Scrollable mobile sidebar** - navigation stays usable on small-height screens.
- **Static export support** - the dashboard can now be built into a fully static bundle (`AIED_STATIC_EXPORT=1`) for lightweight serving.
- **Synced desktop build** - static build synced to the desktop app's dashboard bundle so the desktop app stays in sync.

### Verification
- TypeScript type check: passed (no errors).
- Production static build: passed.
- Both local (dev server) and static build verified to serve the dashboard at login.