FROM node:18-slim

WORKDIR /function

# Install common dependencies
RUN npm install --no-save axios lodash

# Copy the function handler script
COPY function_handler.js /function/

# Command to run the function
ENTRYPOINT ["node", "/function/function_handler.js"]
