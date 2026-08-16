from setuptools import setup, find_packages

setup(
    name="spec2testbench",
    version="0.5.0",
    description="Traceable specification-to-testbench verification for analog circuits",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="Exauce Kambale Maruba, Christian-Marie Moanda Ndeko Mosengo",
    author_email="exauce.kambale@unikin.ac.cd, christianmoanda@yahoo.fr",
    license="MIT",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "numpy>=1.24",
        "matplotlib>=3.7",
        "pyyaml>=6.0",
        "python-dotenv>=1.0",
        "pydantic>=2.10",
        "typer>=0.9",
        "rich>=13.0",
        "schemdraw>=0.19",
    ],
    extras_require={
        "dev": ["pytest>=7.0"],
        "pyspice": ["pyspice>=1.5"],
        "llm": [
            "openai>=1.0",
            "anthropic>=0.25",
            "google-generativeai>=0.5",
            "pillow>=9.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "spec2testbench=spec2testbench.presentation.cli.main:app",
        ],
    },
    python_requires=">=3.10",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Electronic Design Automation (EDA)",
    ],
)
