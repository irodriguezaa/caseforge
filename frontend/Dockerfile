FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

RUN addgroup --system caseforge && adduser --system --ingroup caseforge caseforge

COPY --chown=caseforge:caseforge . ./
RUN chown -R caseforge:caseforge /app

EXPOSE 3000

USER caseforge

CMD ["npm", "run", "dev"]
