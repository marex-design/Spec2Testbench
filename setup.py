from setuptools import setup, find_packages
setup(
    name='spec2testbench',
    version='0.5.0',
    description='Deterministic and hybrid LLM-SPICE verification framework for analog circuits',
    author='Exauce K. Maruba',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'numpy>=1.24','matplotlib>=3.7','pyyaml>=6.0','python-dotenv>=1.0',
        'pydantic>=2.6','typer>=0.9','rich>=13.0','schemdraw>=0.19','openai>=1.0'
    ],
    extras_require={'dev':['pytest>=8.0']},
    entry_points={'console_scripts':['spec2testbench=spec2testbench.presentation.cli.main:app']},
    python_requires='>=3.10',
)
