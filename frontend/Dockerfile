# --- Build stage -----------------------------------------------------------
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci 2>/dev/null || npm install

COPY . .

# Baked in at build time by Vite; empty means "same origin" (see nginx proxy).
ARG VITE_API_BASE_URL=""
ARG VITE_DEFAULT_TENANT="tenant-c"
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_DEFAULT_TENANT=$VITE_DEFAULT_TENANT

RUN npm run build

# --- Runtime stage ---------------------------------------------------------
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
