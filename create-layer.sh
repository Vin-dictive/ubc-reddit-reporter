#!/bin/bash

# Create pandas/numpy layer for Lambda
mkdir -p layer/python
cd layer

# Install pandas and numpy to the layer
pip install pandas numpy -t python/

# Create layer zip
zip -r pandas-numpy-layer.zip python/

# Deploy layer (replace region as needed)
aws lambda publish-layer-version \
    --layer-name pandas-numpy-layer \
    --zip-file fileb://pandas-numpy-layer.zip \
    --compatible-runtimes python3.11 \
    --description "Pandas and NumPy for Lambda"

echo "Layer created. Add the ARN to your SAM template."