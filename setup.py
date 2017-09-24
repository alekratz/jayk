from io import open

from setuptools import find_packages, setup

with open('jayk/__init__.py', 'r') as f:
    for line in f:
        if line.startswith('__version__'):
            version = line.strip().split('=')[1].strip(' \'"')
            break
    else:
        version = '0.0.1'

with open('README.rst', 'r', encoding='utf-8') as f:
    readme = f.read()

REQUIRES = []

setup(
    name='jayk',
    version=version,
    description='An extensible chatbot client library',
    long_description=readme,
    author='Alek Ratzloff',
    author_email='alekratz <at> gmail <<dot>> com',
    url='https://github.com/alekratz/jayk',
    license='ISC',

    keywords=[
        'bot', 'chatbot', 'irc',
    ],

    classifiers=[
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy',
    ],

    install_requires=REQUIRES,
    tests_require=['coverage', 'pytest'],

    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'jayk = jayk.cli:jayk',
        ],
    },
)
