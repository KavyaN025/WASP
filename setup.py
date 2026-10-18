from setuptools import setup, find_packages

setup(
    name="wasp-lab",
    version="0.1.0",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "wasp=wasp_lab.__main__:main",
        ],
    },
)
