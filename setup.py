from setuptools import setup

setup(
    name='naumanni-ogp',
    version='0.1',
    author='Shin Adachi',
    author_email='shn@glucose.jp',
    license='AGPL',
    py_modules=['naumanni_ogp'],
    entry_points={
        'naumanni.plugins': [
            'ogp = naumanni_ogp:OGPPlugin',
        ]
    }
)
