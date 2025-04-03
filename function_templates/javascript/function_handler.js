const fs = require('fs');
const path = require('path');

// Get environment variables for execution
const functionPath = process.env.FUNCTION_PATH || '/function/function_code.js';
const functionName = process.env.FUNCTION_NAME || 'handler';
const inputDataStr = process.env.INPUT_DATA || '{}';

/**
 * Load and execute the user function
 */
async function executeFunction() {
  try {
    // Load the user function
    const userModule = require(functionPath);
    
    if (typeof userModule[functionName] !== 'function') {
      throw new Error(`Function '${functionName}' not found in module`);
    }
    
    // Parse input data
    const inputData = JSON.parse(inputDataStr);
    
    // Execute the function
    const startTime = Date.now();
    
    try {
      // Check if function returns a promise
      const fnResult = userModule[functionName](inputData);
      let result;
      
      if (fnResult instanceof Promise) {
        result = await fnResult;
      } else {
        result = fnResult;
      }
      
      const executionTime = (Date.now() - startTime) / 1000;
      
      // Return success result
      return {
        status: 'success',
        result: result,
        execution_time: executionTime
      };
    } catch (execError) {
      const executionTime = (Date.now() - startTime) / 1000;
      
      // Return error result
      return {
        status: 'error',
        error: execError.message,
        traceback: execError.stack,
        execution_time: executionTime
      };
    }
  } catch (loadError) {
    // Return load error result
    return {
      status: 'error',
      error: `Failed to load function: ${loadError.message}`,
      traceback: loadError.stack
    };
  }
}

// Execute the function and print the result
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
