/**
 * Sample JavaScript function that calculates Fibonacci sequence
 * 
 * @param {Object} event - Input event object
 * @param {number} event.n - Calculate Fibonacci sequence up to the nth number
 * @returns {Object} Result object with Fibonacci sequence
 */
function handler(event) {
    const n = event.n || 10;
    
    // Calculate Fibonacci sequence
    const fib = [0, 1];
    for (let i = 2; i < n; i++) {
        fib.push(fib[i-1] + fib[i-2]);
    }
    
    return {
        input: n,
        result: fib,
        length: fib.length
    };
}

// Export the function for Node.js
module.exports = { handler };
