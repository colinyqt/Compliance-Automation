from setuptools import setup, find_packages

setup(
    name="meter_analyzer",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "PyPDF2",
        "ollama",
    ],
)