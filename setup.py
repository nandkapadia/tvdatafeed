from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="tvdatafeed-enhanced",
    version="2.2.1",
    packages=find_packages(exclude=["tests", "*.tests", "*.tests.*"]),
    url="https://github.com/rongardF/tvdatafeed/",
    project_urls={
        "Documentation": "https://github.com/rongardF/tvdatafeed/blob/main/README.md",
        "Source": "https://github.com/rongardF/tvdatafeed/",
        "Tracker": "https://github.com/rongardF/tvdatafeed/issues",
    },
    license="MIT",
    author="StreamAlpha, rongardF",
    author_email="",
    description="TradingView historical and live data downloader with advanced features",
    long_description=long_description,
    long_description_content_type="text/markdown",
    keywords=["tradingview", "trading", "data", "market-data", "finance", "stocks", "crypto", "forex"],
    python_requires=">=3.9",
    install_requires=[
        "pandas>=2.2.0",
        "websockets>=14.1",
        "requests>=2.32.0",
        "python-dateutil>=2.8.0",
    ],
    extras_require={
        "captcha": ["browser-cookie3>=0.19.1"],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Financial and Insurance Industry",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Office/Business :: Financial",
        "Topic :: Office/Business :: Financial :: Investment",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Operating System :: OS Independent",
    ],
    include_package_data=True,
)
