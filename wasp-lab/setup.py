from setuptools import setup, find_packages

setup(
    name="wasp-lab",
    version="0.1.0",
    package_dir={"": ".."},
    packages=["wasp_lab", "wasp_lab.server", "wasp_lab.terminal"],
    entry_points={
        "console_scripts": [
            "wasp=wasp_lab.__main__:main",
        ],
    },
)
