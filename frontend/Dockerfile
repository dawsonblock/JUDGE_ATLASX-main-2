FROM node:20.20.2-slim

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
