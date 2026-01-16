FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json* tsconfig.json ./
RUN npm install --quiet

COPY src ./src

EXPOSE 3000
CMD ["npm", "run", "start"]
