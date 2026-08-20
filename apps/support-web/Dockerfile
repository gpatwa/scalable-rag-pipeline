FROM node:22-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG VITE_SITE_URL=http://localhost:5173
ENV VITE_SITE_URL=${VITE_SITE_URL}
ENV PRERENDER_SKIP=1
RUN npm run build:fast

FROM nginx:1.27-alpine
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=builder /app/dist /usr/share/nginx/html

ENV SUPPORT_API_HOST=support-api:8080
EXPOSE 80
