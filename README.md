# LAMBDA-Serverless-Function

The objective of this project is to design and implement a serverless function execution platform, similar to AWS Lambda, that enables users to deploy and execute functions on-demand via HTTP requests. The system will support multiple programming languages (Python and JavaScript) and enforce execution constraints such as time limits and resource usage restrictions. 
To optimize execution, the platform will integrate at least two virtualization technologies, such as Firecracker MicroVMs, Nanos Unikernel, or Docker Containers, leveraging techniques like pre-warmed execution environments and request batching for improved performance. 
A key feature of the system is a web-based monitoring dashboard that provides real-time insights into function execution metrics, including request volume, response times, error rates, and resource utilization. The backend will handle function deployment, execution, and logging, while a frontend interface will allow users to manage and monitor their functions.

## Overview

The *Serverless Function Platform* is a self-contained system for deploying, executing, and monitoring serverless functions. It provides a simple yet powerful environment for running your code without worrying about server management.

### Key Features

- Support for multiple programming languages (Python, JavaScript)
- Multiple virtualization technologies (Docker, gVisor)
- Function warm-up for improved performance
- Comprehensive metrics and monitoring dashboard
- Simple web interface for function management
- RESTful API for integration with other systems

> *Note:* This platform is designed for educational and development purposes.  
> For production workloads, consider using established serverless platforms like *AWS Lambda, **Google Cloud Functions, or **Azure Functions*.

---

## Getting Started

Follow the steps below to set up and run the Serverless Function Platform on your machine.

### Prerequisites

Make sure you have the following installed:

- [Docker Desktop](https://www.docker.com/products/docker-desktop) (installed and running)
- Python 3.8 or higher
- For gVisor support: A Linux environment with [gVisor](https://gvisor.dev) installed

### Installation

Clone the repository:

```bash
git clone https://github.com/ash-047/LAMBDA-Serverless-Function-312-316-320-367.git
cd LAMBDA-Serverless-Function-312-316-320-367.git
