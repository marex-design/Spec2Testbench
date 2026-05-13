from setuptools import setup, find_packages

setup(
    name="spec2testbench",
    version="0.1.0",
    description="From Specs to SPICE Testbenches - LLM-Assisted Analog Verification",
    author="Your Name",
    author_email="your.email@example.com",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "pyspice>=1.5",
        "numpy>=1.24",
        "matplotlib>=3.7",
        "pyyaml>=6.0",
        "python-dotenv>=1.0",
        "typer>=0.9",
        "rich>=13.0",
    ],
    entry_points={
        "console_scripts": [
            "spec2testbench=spec2testbench.presentation.cli.main:app",
        ],
    },
    python_requires=">=3.10",
)
