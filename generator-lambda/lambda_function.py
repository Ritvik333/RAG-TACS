import boto3
import json
import re
from decimal import Decimal

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
sagemaker_runtime = boto3.client('sagemaker-runtime')
table = dynamodb.Table('DocumentEmbeddings')

def chunk_doc(text):
    # Split by each Problem: ... block
    pattern = r'(Problem:.*?)(?=Problem:|$)'
    return [chunk.strip() for chunk in re.findall(pattern, text, re.DOTALL)]

def get_embedding(text):
    payload = {"inputs": [text]}
    response = sagemaker_runtime.invoke_endpoint(
        EndpointName='sentence-transformer-endpoint-2025-05-30',
        ContentType='application/json',
        Body=json.dumps(payload)
    )
    result = json.loads(response['Body'].read().decode('utf-8'))
    print(f"Raw embedding response: {result}")  # Debug the full response
    if isinstance(result, list) and len(result) > 0 and isinstance(result[0], list):
        embedding = result[0]  # Expecting [384] list
    else:
        raise ValueError(f"Unexpected embedding format: {result}")
    return embedding

def lambda_handler(event, context):
    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']
        
        # Read the document from S3
        obj = s3.get_object(Bucket=bucket, Key=key)
        text = obj['Body'].read().decode('utf-8')
        
        # Chunk the document
        chunks = chunk_doc(text)
        
        # Generate and store embeddings for each chunk
        for i, chunk in enumerate(chunks):
            if chunk:  # Skip empty chunks
                embedding = get_embedding(chunk)
                if len(embedding) != 384:
                    print(f"Warning: Embedding for {key}_chunk_{i} has {len(embedding)} dimensions, expected 384")
                    continue
                embedding_decimal = [Decimal(str(val)) for val in embedding]
                item = {
                    "document_id": f"{base_name}_chunk_{i}",
                    "chunk_text": chunk,
                    "embedding": embedding_decimal
                }
                table.put_item(Item=item)
                print(f"Stored {key}_chunk_{i} with {len(embedding)} dimensions")
    
    return {
        'statusCode': 200,
        'body': json.dumps('Embedding generation complete')
    }