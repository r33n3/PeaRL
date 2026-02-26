# ── dev stage — used by docker compose up locally ──────────────────────────
FROM node:20-alpine AS dev
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# ── build stage — compile static assets ────────────────────────────────────
FROM dev AS build
RUN npm run build

# ── prod stage — nginx serving the built SPA ────────────────────────────────
FROM nginx:1.25-alpine AS prod
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
