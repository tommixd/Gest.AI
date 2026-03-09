import os
from setuptools import find_packages, setup
import sys
import subprocess

requirements = ['numpy==2.3.1', 'tqdm==4.66.1', 'pandas==2.3.0', 'ipykernel', 'ipywidgets', 
                'matplotlib>=3.10.5', 'jupyter==1.0.0', 'torch==2.7.0', 'tensorboard==2.13.0', 'scipy', 'wandb', 'huggingface_hub',             'transformers']
setup(
    name='llms',
    packages=find_packages(where=['llms']),
    python_requires='>=3.11, <4',
    install_requires=requirements,
    version='0.2.0',
    description='llms',
    author='the one',
    license='',
)
