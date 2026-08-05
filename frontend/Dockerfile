FROM node:24-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=10s \
  CMD node -e "fetch('http://localhost:5173').then((response) => process.exit(response.ok ? 0 : 1)).catch(() => process.exit(1))"

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
