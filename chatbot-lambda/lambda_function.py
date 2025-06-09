import json
import boto3
import numpy as np
import logging
import decimal
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('DocumentEmbeddings')

EMBEDDING_ENDPOINT = 'sentence-transformer-endpoint-2025-05-30'

# Secrets Manager function to retrieve the SageMaker endpoint
def get_secret():
    secret_name = "ChatbotSecrets"
    region_name = "us-east-1"

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        logger.error(f"Error retrieving secret: {str(e)}", exc_info=True)
        raise e

    secret = get_secret_value_response['SecretString']
    return json.loads(secret)

# Retrieve the SageMaker endpoint from Secrets Manager
TEXT_GENERATION_ENDPOINT = get_secret()['SageMakerEndpoint']

def get_query_embedding(query):
    runtime = boto3.client('sagemaker-runtime')
    payload = {"inputs": [query]}
    response = runtime.invoke_endpoint(
        EndpointName=EMBEDDING_ENDPOINT,
        ContentType='application/json',
        Body=json.dumps(payload)
    )
    result = json.loads(response['Body'].read())
    logger.info(f"Raw endpoint output: {result}")

    if isinstance(result, list) and all(isinstance(x, float) for x in result):
        sentence_embedding = result
    elif isinstance(result, list) and isinstance(result[0], list):
        sentence_embedding = result[0]
    elif isinstance(result, dict) and 'embedding' in result:
        sentence_embedding = result['embedding']
    else:
        raise ValueError(f"Unexpected embedding format: {result}")

    logger.info(f"Query embedding: {sentence_embedding[:2]}... ({len(sentence_embedding)} dims)")
    return sentence_embedding

def cosine_similarity(vec1, vec2):
    a = np.array(vec1, dtype=np.float32)
    b = np.array(vec2, dtype=np.float32)
    if a.size != b.size:
        logger.error(f"Dimension mismatch: vec1 size {a.size}, vec2 size {b.size}")
        return 0.0
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def get_top_k_contexts(query_embedding, k=3):
    logger.info("Starting context retrieval from DynamoDB")
    try:
        response = table.scan()
        items = response.get('Items', [])
        logger.info(f"Retrieved {len(items)} items from DynamoDB")
        scored = []
        for item in items:
            embedding = item.get('embedding', [])
            doc_embedding = []
            if isinstance(embedding, list):
                if all(isinstance(x, decimal.Decimal) for x in embedding):
                    doc_embedding = [float(x) for x in embedding]
                elif all(isinstance(x, dict) and 'N' in x for x in embedding):
                    doc_embedding = [float(x['N']) for x in embedding]
            elif isinstance(embedding, decimal.Decimal):
                doc_embedding = [float(embedding)]
            elif isinstance(embedding, dict) and 'N' in embedding:
                doc_embedding = [float(embedding['N'])]
            else:
                logger.warning(f"Unknown embedding format for item {item.get('document_id')}: {embedding}")
                continue

            chunk_text = item.get('chunk_text', '')
            logger.info(f"doc_embedding length: {len(doc_embedding)} for {item.get('document_id')}")
            if doc_embedding and len(doc_embedding) == len(query_embedding) and chunk_text:
                logger.info("Calling cosine_similarity")
                similarity = cosine_similarity(query_embedding, doc_embedding)
                scored.append((similarity, chunk_text))
        if not scored:
            logger.warning("No valid embeddings found in DynamoDB")
            return []
        scored.sort(reverse=True)
        top_chunks = [text for _, text in scored[:k]]
        logger.info(f"Top {k} context chunks selected: {top_chunks}")
        return top_chunks
    except Exception as e:
        logger.error(f"Error retrieving context: {str(e)}", exc_info=True)
        return []

def format_context(context_chunks):
    if not context_chunks:
        return "No relevant context found."
    formatted = ""
    for i, chunk in enumerate(context_chunks, 1):
        formatted += f"Context {i}:\n{chunk.strip()}\n\n"
    return formatted

def lambda_handler(event, context):
    logger.info("Lambda function invoked")
    try:
        body = json.loads(event.get("body", "{}"))
        logger.info(f"Received body: {body}")
        query = body.get("query", "")
        if not query:
            logger.error("Query not provided")
            return {
                "statusCode": 400,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type",
                    "Access-Control-Allow-Methods": "POST,OPTIONS"
                },
                "body": json.dumps({"error": "Query not provided"})
            }

        logger.info(f"Processing query: {query}")

        # Use SageMaker endpoint to get query embedding
        query_embedding = get_query_embedding(query)
        context_chunks = get_top_k_contexts(query_embedding, k=3)
        formatted_context = format_context(context_chunks)
        logger.info(f"Formatted context: {formatted_context}")

        # Improved prompt for LLM
        prompt = (
            "You are an AWS support assistant. Use only the provided context to answer the user's question. "
            "If the answer is not in the context, say 'The answer is not available in the provided context.'\n\n"
            f"{formatted_context}"
            f"Question: {query}\n"
            "Answer:"
        )

        # Invoke SageMaker LLM endpoint
        runtime = boto3.client('sagemaker-runtime')
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_length": 100,
                "temperature": 0.7,
                "top_k": 50
            }
        }
        sagemaker_response = runtime.invoke_endpoint(
            EndpointName=TEXT_GENERATION_ENDPOINT,
            ContentType='application/json',
            Body=json.dumps(payload)
        )
        result = json.loads(sagemaker_response['Body'].read().decode())
        logger.info(f"Raw SageMaker response: {result}")

        # Parse response for gpt2-small-endpoint-2025-05-31 format
        if isinstance(result, list) and len(result) > 0 and 'generated_text' in result[0]:
            sagemaker_output = result[0]['generated_text']
        else:
            sagemaker_output = result.get('generated_text', 'No response from SageMaker')
        logger.info(f"SageMaker output: {sagemaker_output}")

        final_response = f"Context:\n{formatted_context}\nResponse: {sagemaker_output}"
        logger.info(f"Returning response: {final_response}")

        return {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "POST,OPTIONS"
            },
            "body": json.dumps({"response": final_response})
        }

    except Exception as e:
        logger.error(f"Error in Lambda: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "POST,OPTIONS"
            },
            "body": json.dumps({"error": f"Error processing request: {str(e)}"})
        }