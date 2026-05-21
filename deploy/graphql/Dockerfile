FROM node:22-slim
WORKDIR /app
COPY package.json ./
RUN npm install --production
COPY server.js ./
USER 1000:1000
EXPOSE 5000
CMD ["node", "server.js"]
