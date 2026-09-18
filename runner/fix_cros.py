import boto3

# 1. Fill in your Backblaze details
B2_ENDPOINT = 'https://s3.us-east-005.backblazeb2.com' # Replace with your exact endpoint
B2_KEY_ID = '00541b98126411d0000000001'
B2_APPLICATION_KEY = 'K005MplQY2ZJauZAyTb7BZh+uGnwAXM'
BUCKET_NAME = 'video-buffer'

# 2. Connect to Backblaze S3 API
s3 = boto3.client('s3',
    endpoint_url=B2_ENDPOINT,
    aws_access_key_id=B2_KEY_ID,
    aws_secret_access_key=B2_APPLICATION_KEY
)

# 3. Define the Custom CORS Rule (Allows PUT/Uploads from any website)
cors_configuration = {
    'CORSRules': [{
        'AllowedHeaders': ['*'],
        'AllowedMethods': ['GET', 'PUT', 'POST', 'DELETE', 'HEAD'],
        'AllowedOrigins': ['*'], 
        'ExposeHeaders': ['ETag'],
        'MaxAgeSeconds': 3000
    }]
}

# 4. Inject the rule
s3.put_bucket_cors(Bucket=BUCKET_NAME, CORSConfiguration=cors_configuration)
print("Success! Backblaze CORS updated to allow browser uploads.")