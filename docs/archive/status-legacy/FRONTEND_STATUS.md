# Frontend Status

**Date**: 2026-05-02  
**Node Support**: 20, 22, 24 (20+ required)  
**Package Manager**: npm

---

## Build Status

| Check | Status | Command |
|-------|--------|---------|
| Dependencies | ✅ Working | `npm ci` |
| Lint | ✅ No errors | `npm run lint` |
| Typecheck | ✅ No errors | `npm run typecheck` |
| Build | ✅ 9 pages | `npm run build` |

---

## Known Issues Fixed

### 1. Admin Token Bug (FIXED 2026-05-02)

**Issue**: `loadAIQueue()` in `app/admin/review/page.tsx` did not send the `X-JTA-Admin-Token` header, causing 403 errors when loading AI review items.

**Fix**: Added `"X-JTA-Admin-Token": token` to the fetch headers.

**Verification**:
1. Start backend with `JTA_ENABLE_ADMIN_REVIEW=true` and `JTA_ADMIN_REVIEW_TOKEN=your-token`
2. Start frontend: `npm run dev`
3. Navigate to `/admin/review`
4. Enter admin token
5. Click "Load AI review items"
6. Expected: Queue loads without 403 error

---

## Node Version Compatibility

The frontend supports Node.js 20 and later versions (22, 24, etc.).

**Verification script**: `scripts/verify_frontend.sh`

The script checks for Node 20+ (not exactly 20), allowing newer LTS versions.

---

## Manual Verification Steps

```bash
# Install dependencies
cd frontend
npm ci

# Run linting
npm run lint

# Run type checking
npm run typecheck

# Build for production
npm run build

# Start development server
npm run dev
```

---

## Architecture

- **Framework**: Next.js 14 with App Router
- **Language**: TypeScript
- **Styling**: CSS Modules + Global CSS
- **Map**: Leaflet via react-leaflet
- **State**: React hooks (no external state library)

---

## Limitations

- **No SSR for map**: Leaflet requires client-side rendering
- **Admin auth**: Shared token only (local-alpha)
- **API base**: Configurable via `apiBase()` helper

---

## Future Work

- OAuth/OIDC integration for real auth
- Role-based access control
- Admin action audit logging
- Session expiry handling
