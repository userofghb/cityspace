from setuptools import setup, find_packages

setup(
    name="cityspace",  # 库的名字
    version="0.1.0",
    description="This is a code package for urban street space analysis. With this package, you can clean and simplify roads,
    analyze streets with information such as POI and street views, and predict urban street spaces using classifiers.",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",  # README格式
    author="userofghb",
    author_email="2746293150@qq.com",
    url="https://github.com/userofghb/cityspace",
    license="MIT",
    packages=find_packages(include=["cityspace", "cityspace.*"]),  # 自动找到包
    python_requires=">=3.9",
    install_requires=[  # 依赖
        "geopandas",
        "shapely",
        "networkx",
        "numpy",
        "pandas",
        "xgboost",
        "scikit-learn",
        "matplotlib",
        "cityseer",
    ],
    classifiers=[  # PyPI 分类
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: GIS",
    ],
    include_package_data=False, 
    zip_safe=False,
)
