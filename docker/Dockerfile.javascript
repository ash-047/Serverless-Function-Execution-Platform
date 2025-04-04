FROM node:18-slim

WORKDIR /function

RUN npm install --no-save axios lodash

COPY function_handler.js /function/

ENTRYPOINT ["node", "/function/function_handler.js"]
