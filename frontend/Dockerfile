FROM node:22.22.3-bookworm-slim

ENV NEXT_TELEMETRY_DISABLED=1

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

ENV NODE_ENV=production
RUN groupadd --system --gid 999 nodejs && useradd --system --uid 999 --gid nodejs nextjs
USER nextjs

EXPOSE 3000
CMD ["npm", "run", "start"]
