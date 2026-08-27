from setuptools import setup, find_packages

setup(
    name="datadeduplication",
    version="1.0.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "python-dotenv>=1.0.0",
        "sqlalchemy>=2.0.0",
        "pymysql>=1.1.0",
        "PyPDF2>=3.0.0",
        "python-docx>=1.0.0",
        "openpyxl>=3.1.0",
        "python-pptx>=0.6.21",
        "Pillow>=10.0.0",
        "mutagen>=1.47.0",
        "pandas>=2.0.0",
    ],
    python_requires=">=3.9",
)