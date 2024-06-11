from setuptools import find_packages, setup

setup(
    name="shared_lib",
    version="0.0.1",
    author="r06521541",
    author_email="r06521541@ntu.edu.tw",
    url="https://github.com/r06521541/NTUBTOB-management-system",
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    python_requires=">=3.10",
    install_requires=[
        "requests==2.26.0",
        "sqlalchemy==2.0.23",
        "cloud-sql-python-connector",
        "psycopg2",
        "google-api-python-client",
        "google-auth-httplib2",
        "google-auth-oauthlib",
    ],
)
