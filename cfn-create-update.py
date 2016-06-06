#!/usr/bin/env python

import boto3
from botocore.client import Config

import json
import os
import sys
import tempfile
import time
import zipfile

def wait_for_stack(cfn_client, cfn_stack_name):
    
    failed_states = [
        'CREATE_FAILED',
        'ROLLBACK_IN_PROGRESS',
        'ROLLBACK_FAILED',
        'ROLLBACK_COMPLETE',
        'DELETE_IN_PROGRESS',
        'DELETE_FAILED',
        'UPDATE_ROLLBACK_IN_PROGRESS',
        'UPDATE_ROLLBACK_FAILED',
        'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS',
        'UPDATE_ROLLBACK_COMPLETE'        
    ]
    
    complete_states = [
        'CREATE_COMPLETE',
        'UPDATE_COMPLETE'
    ]
    
    
    while True:
        desc_stacks_result = cfn_client.describe_stacks(StackName = cfn_stack_name)
        stack = desc_stacks_result['Stacks'][0]
        if stack['StackStatus'] in failed_states:
            print "Stack %s in state: %s" % (cfn_stack_name, stack['StackStatus'])
            sys.exit(1)
        if stack['StackStatus'] in complete_states:
            return
        
        time.sleep(15)
        

# Get environment variables
CODEPIPELINE_ARTIFACT_CREDENTIALS = json.loads(os.environ['CODEPIPELINE_ARTIFACT_CREDENTIALS'])
CODEPIPELINE_USER_PARAMS          = json.loads(os.environ['CODEPIPELINE_USER_PARAMS'])
CODEPIPELINE_INPUT_ARTIFACTS      = json.loads(os.environ['CODEPIPELINE_INPUT_ARTIFACTS'])
CODEPIPELINE_OUTPUT_ARTIFACTS     = json.loads(os.environ['CODEPIPELINE_OUTPUT_ARTIFACTS'])

# Parse user parameters
user_params = dict()
pairs = CODEPIPELINE_USER_PARAMS.split(',')
for pair in pairs:
    kv = pair.split('=')
    user_params[ kv[0].strip() ] = kv[1].strip()

# Setup S3 client using CodePipeline provided credentials
cp_s3_client = boto3.client('s3',
                             config=Config(signature_version='s3v4'),
                             region_name=user_params['awsRegion'],
                             aws_access_key_id=CODEPIPELINE_ARTIFACT_CREDENTIALS['accessKeyId'],
                             aws_secret_access_key=CODEPIPELINE_ARTIFACT_CREDENTIALS['secretAccessKey'],
                             aws_session_token=CODEPIPELINE_ARTIFACT_CREDENTIALS['sessionToken'])

# Get input artifacts
sourceBundleArtifact = None
imageNameTagArtifact = None

for artifact in CODEPIPELINE_INPUT_ARTIFACTS:
    if artifact['name'] == 'SourceBundle':
        sourceBundleArtifact = artifact
    elif artifact['name'] == 'ImageNameTag':
        imageNameTagArtifact = artifact

if sourceBundleArtifact == None or imageNameTagArtifact == None:
    print "SourceBundle and ImageNameTag must be provided"
    sys.exit(1)

_, srcBundleFile = tempfile.mkstemp()
cp_s3_client.download_file(
                            sourceBundleArtifact['location']['s3Location']['bucketName'],
                            sourceBundleArtifact['location']['s3Location']['objectKey'],
                            srcBundleFile)

_, imageNameTagFile = tempfile.mkstemp()
cp_s3_client.download_file(
                            imageNameTagArtifact['location']['s3Location']['bucketName'],
                            imageNameTagArtifact['location']['s3Location']['objectKey'],
                            imageNameTagFile)

# Extract source bundle
src_bundle_dir = tempfile.mkdtemp()
zf = zipfile.ZipFile(srcBundleFile, 'r')
zf.extractall(src_bundle_dir)
zf.close()

cfn_template_file = src_bundle_dir + "/" + user_params['cfnStackTemplate']
print "cfn_template = %s" % cfn_template_file
with open(cfn_template_file, 'r') as cfn_template_file_ref:
    cfn_template_json = cfn_template_file_ref.read()

# Read image name tag
with open(imageNameTagFile, 'r') as image_name_tag_ref:
    image_name = image_name_tag_ref.read().replace('\n', '')

print "image_name = %s" % image_name

# Create CFN stack if it does not exist, otherwise update it
cfn_client = boto3.client('cloudformation',
                          region_name=user_params['awsRegion'])

# Check if stack exists.  An exception is thrown if it does not
try:
    cfn_client.describe_stacks(StackName = user_params['cfnStackName'])
    stack_exists = True
except:
    stack_exists = False

# Setup CFN Stack Parameters
cfn_stack_params = list()
for key in user_params.keys():
    if key.startswith("CFN_PARAM:"):
        param_key = key.split(":")[1]
        param_value = user_params.get(key)
        cfn_stack_params.append(
            {
                "ParameterKey" : param_key,
                "ParameterValue" : param_value
            }
        )

# Append ECR Image Name to use
cfn_stack_params.append(
    {
        "ParameterKey" : "DockerImageName",
        "ParameterValue" : image_name
    }
)

print "cfn_stack_params = %s" % cfn_stack_params

stack = None

if stack_exists:
    # Do stack update
    print "Doing stack update"
    
    stack = cfn_client.update_stack(
        StackName = user_params['cfnStackName'],
        TemplateBody=cfn_template_json,
        Parameters=cfn_stack_params,
        Capabilities=[
            'CAPABILITY_IAM'
        ]
    )
    
    wait_for_stack(cfn_client, user_params['cfnStackName'])
    
else:
    # Do stack create
    stack = cfn_client.create_stack(
        StackName = user_params['cfnStackName'],
        TemplateBody=cfn_template_json,
        Parameters=cfn_stack_params,
        Capabilities=[
            'CAPABILITY_IAM'
        ]
    )

print stack
    
# Wait for stack create/update to complete

print "-- CloudFormation Create/Update Task Complete --"