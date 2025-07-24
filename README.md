# Serverless-Function-Execution-Platform

This project implements a serverless function execution platform inspired by AWS Lambda, enabling users to deploy and execute functions on-demand via HTTP requests. The system supports multiple programming languages (Python and JavaScript) and enforces execution constraints such as time limits and resource usage restrictions.

The platform integrates **Docker** and **gVisor** as dual virtualization technologies, leveraging container pooling and pre-warmed execution environments for optimized performance. A key feature is the web-based monitoring dashboard that provides real-time insights into function execution metrics, including request volume, response times, error rates, and resource utilization.

## Overview

The *Serverless Function Platform* is a self-contained system for deploying, executing, and monitoring serverless functions. It provides a simple yet powerful environment for running your code without worrying about server management.

### Key Features

- Support for multiple programming languages (Python, JavaScript)
- Multiple virtualization technologies (Docker, gVisor)
- Function warm-up for improved performance
- Comprehensive metrics and monitoring dashboard
- Simple web interface for function management
- RESTful API for integration with other systems

---

## Getting Started

Follow the steps below to set up and run the Serverless Function Platform on your machine.

### Prerequisites

Make sure you have the following installed:

- [Docker Desktop](https://www.docker.com/products/docker-desktop) (installed and running)
- Python 3.8 or higher
- For gVisor support: A Linux environment with [gVisor](https://gvisor.dev) installed
    - *Note: The platform automatically falls back to Docker if gVisor is unavailable*

### Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/ash-047/Serverless-Function-Execution-Platform.git
   cd Serverless-Function-Execution-Platform
   ```

2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Build Docker images:**
   ```bash
   # On Windows
   cd docker
   build.bat
   
   # On Linux/macOS
   cd docker
   ./build.sh
   ```

4. **Start the platform:**
   ```bash
   python backend/main.py
   ```

5. **Access the interface:**
   - Web UI: [http://localhost:8000](http://localhost:8000)
   - API Docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## Project Structure

```
├── backend/               # FastAPI backend
├── docker/                # Runtime Docker images  
├── static/                # Web UI
├── tests/                 # Test scripts
├── function_templates/    # Container handlers
└── metrics_data/          # Metrics storage
```

## API Endpoints

Key endpoints include:
- `POST /execute` - Direct function execution
- `POST /functions` - Create/update stored functions
- `GET /functions` - List all functions
- `POST /functions/{id}/execute` - Execute stored function
- `GET /metrics` - Execution metrics
- `GET /system/status` - System status

---
