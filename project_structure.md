```
CC-project/
├── backend/
│   ├── api/                  # API routes and controllers
│   ├── database/             # Database models and connection
│   ├── execution_engine/     # Core execution logic
│   │   ├── docker_runtime.py # Docker-based execution
│   │   └── utils.py          # Utility functions for execution
│   └── main.py               # Main application entry point
├── function_templates/       # Templates for different languages
│   └── python/               # Python function template
├── tests/                    # Test files
└── docker/                   # Docker configuration
    ├── Dockerfile.python     # Base image for Python functions
    └── docker-compose.yml    # Docker compose for development
```
