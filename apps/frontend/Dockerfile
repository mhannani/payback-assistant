# Multi-stage build for the Next.js widget app → a small standalone runtime.
# NEXT_PUBLIC_API_BASE is baked at BUILD time (it's inlined into the client bundle), so it must be
# passed as a build arg, not a runtime env.

FROM node:22-alpine AS deps
WORKDIR /app
# .npmrc carries `legacy-peer-deps=true` (emoji-mart's React peer range predates React 19). Copy it
# AND pass the flag explicitly, so `npm ci` resolves identically in CI and locally.
COPY package.json package-lock.json .npmrc ./
RUN npm ci --legacy-peer-deps

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# The widget calls the API at this origin (prod: https://api.payback.mhannani.me).
ARG NEXT_PUBLIC_API_BASE=https://api.payback.mhannani.me
ENV NEXT_PUBLIC_API_BASE=${NEXT_PUBLIC_API_BASE}
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
# Run as a non-root user.
RUN addgroup -g 1001 nodejs && adduser -u 1001 -G nodejs -S nextjs
# Standalone output: the server bundle + the static assets + public/ (widget.js, etc.).
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
USER nextjs
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0
CMD ["node", "server.js"]
