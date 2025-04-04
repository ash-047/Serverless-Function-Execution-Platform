const fs = require('fs');
const path = require('path');

const functionPath = process.env.FUNCTION_PATH || '/function/function_code.js';
const functionName = process.env.FUNCTION_NAME || 'handler';
const inputDataStr = process.env.INPUT_DATA || '{}';

async function executeFunction() {
  try {
    const userModule = require(functionPath);
    
    if (typeof userModule[functionName] !== 'function') {
      throw new Error(`Function '${functionName}' not found in module`);
    }
    
    const inputData = JSON.parse(inputDataStr);
    
    const startTime = Date.now();
    
    try {
      const fnResult = userModule[functionName](inputData);
      let result;
      
      if (fnResult instanceof Promise) {
        result = await fnResult;
      } else {
        result = fnResult;
      }
      
      const executionTime = (Date.now() - startTime) / 1000;
      
      return {
        status: 'success',
        result: result,
        execution_time: executionTime
      };
    } catch (execError) {
      const executionTime = (Date.now() - startTime) / 1000;
      
      return {
        status: 'error',
        error: execError.message,
        traceback: execError.stack,
        execution_time: executionTime
      };
    }
  } catch (loadError) {
    return {
      status: 'error',
      error: `Failed to load function: ${loadError.message}`,
      traceback: loadError.stack
    };
  }
}

executeFunction()
  .then(result => {
    console.log(JSON.stringify(result));
  })
  .catch(error => {
    console.log(JSON.stringify({
      status: 'error',
      error: `Execution failed: ${error.message}`,
      traceback: error.stack
    }));
  });
