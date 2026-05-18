"""Setup script for ai-agent"""
from setuptools import setup, find_packages

setup(
    name="ai-agent",
    version="1.0.0",
    description="Multi-provider AI coding agent with auto-failover",
    packages=find_packages(include=["providers", "tools", "modes", "validator", "web"]),
    python_requires=">=3.9",
    install_requires=[
        "httpx>=0.24.0",
        "flask>=2.3.0",
        "flask-socketio>=5.3.0",
        "python-socketio>=5.8.0",
        "python-dotenv>=1.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "flake8>=6.0.0",
            "pylint>=2.17.0",
            "black>=23.0.0",
        ],
        "web": [
            "eventlet>=0.33.0",
            "gunicorn>=21.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "ai-agent=main:main",
        ],
    },
)
