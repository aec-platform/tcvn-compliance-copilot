# syntax=docker/dockerfile:1.7

FROM node:25-bookworm-slim AS base
RUN corepack enable && corepack prepare pnpm@9.12.2 --activate
WORKDIR /app

# ---- deps -------------------------------------------------------------
FROM base AS deps
COPY package.json pnpm-lock.yaml* ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    if [ -f pnpm-lock.yaml ]; then pnpm install --frozen-lockfile; \
    else pnpm install; fi

# ---- dev (hot reload) -------------------------------------------------
FROM deps AS dev
COPY . .
EXPOSE 3000
CMD ["pnpm", "dev"]

# ---- build ------------------------------------------------------------
FROM deps AS build
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm build

# ---- prod (standalone runtime) ---------------------------------------
FROM node:25-bookworm-slim AS prod
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
RUN groupadd --system --gid 1001 nextjs \
    && useradd --system --uid 1001 --gid nextjs --create-home nextjs

COPY --from=build --chown=nextjs:nextjs /app/.next/standalone ./
COPY --from=build --chown=nextjs:nextjs /app/.next/static ./.next/static
COPY --from=build --chown=nextjs:nextjs /app/public ./public

USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
