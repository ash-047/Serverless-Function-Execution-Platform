def handler(event):
    """
    Sample function that calculates Fibonacci sequence
    
    Input event format:
    {
        "n": 10  # Calculate Fibonacci sequence up to the 10th number
    }
    """
    n = event.get("n", 10)
    
    # Calculate Fibonacci sequence
    fib = [0, 1]
    for i in range(2, n):
        fib.append(fib[i-1] + fib[i-2])
    
    return {
        "input": n,
        "result": fib,
        "length": len(fib)
    }
