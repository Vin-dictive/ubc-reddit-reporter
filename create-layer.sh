#!/bin/bash

# Create directory structure for Lambda layer
mkdir -p layer/python

# Install all dependencies into the layer folder
pip install \
    numpy==1.27.5 \
    pandas==2.1.3 \
    pydantic==2.0.0 \
    langchain=0.2.0 \
    langchain-core=0.2.0 \
    langchain-community=0.2.0 \
    langchain-aws=0.1.0 \
    --target layer/python/ \
    --platform manylinux2014_x86_64 \
    --only-binary=:all: \
    --upgrade

# Navigate to layer folder
cd layer

# Create the zip file for the Lambda layer
zip -r pandas-numpy-langchain-layer.zip python/

# Deploy the layer to AWS Lambda (replace region as needed)
aws lambda publish-layer-version \
    --layer-name pandas-numpy-langchain-layer \
    --zip-file fileb://pandas-numpy-langchain-layer.zip \
    --compatible-runtimes python3.11 \
    --description "Pandas, NumPy, and LangChain dependencies for Lambda"

echo "Layer created. Add the ARN to your SAM template."