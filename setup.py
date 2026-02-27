from pathlib import Path
from setuptools import setup, find_packages

here = Path(__file__).parent.resolve()
long_description = (here / 'README.md').read_text(encoding='utf-8')

setup(
    name='bmctools',
    version='0.1.2',
    packages=find_packages(where='src'),
    package_dir={'': 'src'},
    install_requires=[
        'requests',
    ],
    entry_points={
        'console_scripts': [
            'bmctools=bmctools.cli.main:main',
        ],
    },
    author='Jesse Butryn',
    author_email='jesse.butryn@example.com',
    description='A collection of tools for interacting with Baseboard Management Controllers (BMCs)',
    long_description=long_description,
    long_description_content_type='text/markdown',
    license='GPL-3.0-only',
    url='https://github.com/jessebutryn/bmctools',
    project_urls={
        'Bug Tracker': 'https://github.com/jessebutryn/bmctools/issues',
        'Source Code': 'https://github.com/jessebutryn/bmctools',
    },
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Topic :: System :: Hardware',
        'Topic :: System :: Systems Administration',
    ],
    python_requires='>=3.9',
)
